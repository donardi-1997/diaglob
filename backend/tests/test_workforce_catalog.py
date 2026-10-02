from app.workforce_catalog import (
    get_workforce_catalog,
    get_workforce_role,
    resolve_role_instruction,
)


def test_workforce_catalog_has_expected_operational_roles():
    role_ids = {item["id"] for item in get_workforce_catalog()}
    assert {
        "sales",
        "support",
        "logistics",
        "retention",
        "analyst",
        "post_sales",
    }.issubset(role_ids)


def test_internal_analyst_role_is_not_customer_facing():
    analyst = get_workforce_role("analyst")
    assert analyst is not None
    assert analyst["customer_facing"] is False


def test_canonical_role_resolves_to_behavioral_instruction():
    instruction = resolve_role_instruction("support")
    assert "tracking" in instruction.lower()
    assert instruction != "support"


def test_unknown_legacy_role_is_preserved():
    assert resolve_role_instruction("Especialista de catálogo") == "Especialista de catálogo"
