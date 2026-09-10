"""Focused hardening regressions for conversational COD checkout."""

from app.services.conversational_checkout_service import normalize_delivery_address


def test_calle_80_alone_is_not_a_deliverable_colombian_address():
    normalized, score = normalize_delivery_address("Calle 80", "CO")

    assert normalized is None
    assert score == 0


def test_complete_colombian_shorthand_remains_supported():
    normalized, score = normalize_delivery_address("calle 80 15 24", "CO")

    assert normalized == "Calle 80 # 15-24"
    assert score >= 60
