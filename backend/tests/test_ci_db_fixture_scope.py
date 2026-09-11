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
    assert schema_fixture in {arg.arg for arg in cleanup.args.args}


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


def test_automations_schema_setup_is_only_requested_by_db_fixture():
    _assert_db_schema_is_opt_in(
        ROOT / "test_automations.py",
        "setup_db",
    )


def test_shopify_schema_is_created_once_and_data_cleanup_has_no_ddl():
    functions = _fixture_functions(ROOT / "test_shopify.py")
    schema = functions["setup_db"]
    cleanup = functions["cleanup_db"]

    assert _calls_schema_ddl(schema)
    assert _fixture_scope(schema) == "module"
    assert _is_autouse_fixture(schema)

    assert _is_autouse_fixture(cleanup)
    assert not _calls_schema_ddl(cleanup)
