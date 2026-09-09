"""Regression tests for local payment method market restrictions."""
from app.payments.market_policy import (
    get_payment_methods_for_market,
    payment_method_available,
)


def test_nequi_only_colombia_cop():
    assert payment_method_available("nequi_push", "CO", "COP")
    assert not payment_method_available("nequi_push", "BR", "BRL")
    assert not payment_method_available("nequi_push", "US", "USD")
    assert not payment_method_available("nequi_push", "CO", "USD")


def test_pix_only_brazil_brl():
    assert payment_method_available("pix", "BR", "BRL")
    assert not payment_method_available("pix", "CO", "COP")
    assert not payment_method_available("pix", "US", "USD")
    assert not payment_method_available("pix", "BR", "USD")


def test_market_listing_is_country_specific():
    assert get_payment_methods_for_market("CO", "COP") == [
        {"code": "nequi_push", "name": "Nequi"}
    ]
    assert get_payment_methods_for_market("BR", "BRL") == [
        {"code": "pix", "name": "PIX"}
    ]
    assert get_payment_methods_for_market("US", "USD") == []


def test_market_codes_are_case_insensitive():
    assert payment_method_available("PIX", "br", "brl")
    assert payment_method_available("NEQUI_PUSH", "co", "cop")
