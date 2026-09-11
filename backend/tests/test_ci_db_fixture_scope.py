from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _fixture_functions(path: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def _fixture_keyword(function: ast.FunctionDef, keyword_name: str):
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if not (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "pytest"
            and func.attr == "fixture"
        ):
            continue
        for keyword in decorator.keywords:
            if keyword.arg == keyword_name and isinstance(keyword.value, ast.Constant):
                return keyword.value.value
    return None


def _is_autouse_fixture(function: ast.FunctionDef) -> bool:
    return _fixture_keyword(function, "autouse") is True


def _fixture_scope(function: ast.FunctionDef) -> str | None:
    value = _fixture_keyword(function, "scope")
    return value if isinstance(value, str) else None


def _calls_schema_ddl(function: ast.FunctionDef) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in {"create_all", "drop_all"}:
            return True
    return False


def _calls_row_delete(function: ast.FunctionDef) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "delete":
            return True
    return False


def _calls_named_function(function: ast.FunctionDef, function_name: str) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == function_name:
                return True
    return False


def _assert_db_schema_is_opt_in(path: Path, schema_fixture: str) -> None:
    functions = _fixture_functions(path)
    schema = functions[schema_fixture]
    db = functions["db"]

    assert _calls_schema_ddl(schema)
    assert not _is_autouse_fixture(schema)
    assert schema_fixture in {arg.arg for arg in db.args.args}

    for function in functions.values():
        if _is_autouse_fixture(function):
            assert not _calls_schema_ddl(function), (
                f"autouse fixture {function.name} must not create/drop the DB schema"
            )


def _assert_schema_once_with_cleanup(path: Path, schema_fixture: str) -> None:
    functions = _fixture_functions(path)
    schema = functions[schema_fixture]
    cleanup = functions["cleanup_db"]

    assert _calls_schema_ddl(schema)
    assert _fixture_scope(schema) == "module"
    assert _is_autouse_fixture(schema)

    assert _is_autouse_fixture(cleanup)
    assert not _calls_schema_ddl(cleanup)


def _assert_opt_in_schema_once_with_db_cleanup(path: Path, schema_fixture: str) -> None:
    functions = _fixture_functions(path)
    schema = functions[schema_fixture]
    db = functions["db"]

    assert _calls_schema_ddl(schema)
    assert _fixture_scope(schema) == "module"
    assert not _is_autouse_fixture(schema)
    assert schema_fixture in {arg.arg for arg in db.args.args}

    assert not _calls_schema_ddl(db)
    assert _calls_row_delete(db)

    for function in functions.values():
        if _is_autouse_fixture(function):
            assert not _calls_schema_ddl(function), (
                f"autouse fixture {function.name} must not create/drop the DB schema"
            )


def _assert_shared_module_engine_with_row_cleanup(path: Path) -> None:
    functions = _fixture_functions(path)
    engine_fixture = functions["campaign_engine"]
    clear_rows = functions["_clear_db_rows"]

    assert _calls_schema_ddl(engine_fixture)
    assert _fixture_scope(engine_fixture) == "module"
    assert not _is_autouse_fixture(engine_fixture)
    assert _calls_row_delete(clear_rows)

    for fixture_name in ("db", "endpoint_db"):
        fixture = functions[fixture_name]
        assert "campaign_engine" in {arg.arg for arg in fixture.args.args}
        assert not _calls_schema_ddl(fixture)
        assert _calls_named_function(fixture, "_clear_db_rows")


def test_bedrock_schema_is_created_once_and_data_cleanup_has_no_ddl():
    _assert_schema_once_with_cleanup(
        ROOT / "test_bedrock_knowledge_base.py",
        "setup_database",
    )


def test_google_sheets_schema_is_created_once_and_data_cleanup_has_no_ddl():
    _assert_schema_once_with_cleanup(
        ROOT / "test_google_sheets.py",
        "setup_db",
    )


def test_automations_schema_is_opt_in_created_once_and_db_cleans_rows():
    _assert_opt_in_schema_once_with_db_cleanup(
        ROOT / "test_automations.py",
        "setup_db",
    )


def test_shopify_schema_is_created_once_and_data_cleanup_has_no_ddl():
    _assert_schema_once_with_cleanup(ROOT / "test_shopify.py", "setup_db")


def test_payments_schema_is_created_once_and_data_cleanup_has_no_ddl():
    _assert_schema_once_with_cleanup(ROOT / "test_payments.py", "setup_db")


def test_whatsapp_schema_is_created_once_and_data_cleanup_has_no_ddl():
    _assert_schema_once_with_cleanup(ROOT / "test_whatsapp.py", "setup_db")


def test_analytics_schema_is_created_once_and_data_cleanup_has_no_ddl():
    _assert_schema_once_with_cleanup(ROOT / "test_analytics.py", "setup_db")


def test_billing_preview_schema_is_created_once_and_data_cleanup_has_no_ddl():
    _assert_schema_once_with_cleanup(ROOT / "test_billing_preview.py", "setup_db")


def test_automation_campaigns_share_module_engine_and_clean_rows_per_test():
    _assert_shared_module_engine_with_row_cleanup(ROOT / "test_automation_campaigns.py")


def test_automation_flows_share_module_engine_and_clean_rows_per_test():
    functions = _fixture_functions(ROOT / "test_automation_flows.py")
    engine_fixture = functions["flow_engine"]
    clear_rows = functions["_clear_flow_db_rows"]
    db = functions["db"]

    assert _calls_schema_ddl(engine_fixture)
    assert _fixture_scope(engine_fixture) == "module"
    assert not _is_autouse_fixture(engine_fixture)
    assert _calls_row_delete(clear_rows)

    assert "flow_engine" in {arg.arg for arg in db.args.args}
    assert not _calls_schema_ddl(db)
    assert _calls_named_function(db, "_clear_flow_db_rows")
