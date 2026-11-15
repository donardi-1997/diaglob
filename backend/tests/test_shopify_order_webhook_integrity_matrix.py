"""Shopify order webhook integrity and parsing matrix (synthetic data only)."""
import base64
from datetime import datetime
from decimal import Decimal
import hashlib
import hmac

import pytest

from app.services.shopify_webhook_service import (
    _currency, _int_value, _lifecycle_status, _money,
    _normalize_payment_status, _parse_datetime, _shipping_address,
    verify_shopify_webhook_hmac,
)


@pytest.fixture
def signed_body(monkeypatch):
    secret = "synthetic-webhook-signing-secret"
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", secret)
    body = b'{"id":42,"total_price":"100.00","customer":null}'
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return body, base64.b64encode(digest).decode("ascii")


def test_shopify_signature_covers_exact_raw_body_bytes(signed_body):
    body, signature = signed_body
    assert verify_shopify_webhook_hmac(body, signature) is True
    assert verify_shopify_webhook_hmac(body, " " + signature + " ") is True
    assert verify_shopify_webhook_hmac(body + b" ", signature) is False
    assert verify_shopify_webhook_hmac(
        body.replace(b'"id":42', b'"id":43'), signature,
    ) is False
    assert verify_shopify_webhook_hmac(body, base64.b64encode(b"0" * 32).decode()) is False


@pytest.mark.parametrize("body,signature", [
    (b"", "not-a-signature"), (b"{}", None), (b"{}", ""),
    (b"{}", "invalid!"), (b"{}", "0" * 44),
])
def test_unsigned_or_invalid_shopify_webhooks_are_rejected(
    signed_body, body, signature,
):
    assert verify_shopify_webhook_hmac(body, signature) is False


def test_missing_shopify_signature_secret_fails_closed(monkeypatch, signed_body):
    body, signature = signed_body
    monkeypatch.delenv("SHOPIFY_CLIENT_SECRET", raising=False)
    assert verify_shopify_webhook_hmac(body, signature) is False


@pytest.mark.parametrize("amount,expected", [
    ("0", "0"), ("0.00", "0.00"), ("19.95", "19.95"),
    ("0.001", "0.001"), ("5000000.00", "5000000.00"),
    (None, "0"), ("", "0"), ("invalid", "0"),
    ({}, "0"), (["1"], "0"),
])
def test_shopify_money_parser_is_precise_and_handles_invalid_inputs(amount, expected):
    assert _money(amount) == Decimal(expected)


@pytest.mark.parametrize("amount", [
    "NaN", "nan", "sNaN", "Infinity", "-Infinity",
    float("inf"), float("-inf"), float("nan"),
])
def test_non_finite_shopify_prices_never_enter_order_data(amount):
    assert _money(amount) == Decimal("0")


@pytest.mark.parametrize("quantity,expected", [
    (1, 1), ("3", 3), (0, 1), (-2, 1),
    ("0", 1), ("invalid", 1), (None, 1),
])
def test_order_line_quantities_preserve_minimum_and_default(quantity, expected):
    assert _int_value(quantity, minimum=1, default=1) == expected


@pytest.mark.parametrize("topic,payload,expected", [
    ("orders/create", {}, "open"),
    ("orders/updated", {"financial_status": "paid"}, "paid"),
    ("orders/updated", {"financial_status": "refunded"}, "refunded"),
    ("orders/updated", {"financial_status": "voided"}, "voided"),
    ("orders/updated", {"fulfillment_status": "fulfilled"}, "fulfilled"),
    ("orders/updated", {"financial_status": "paid", "fulfillment_status": "fulfilled"}, "fulfilled"),
    ("orders/cancelled", {"financial_status": "paid"}, "cancelled"),
    ("orders/updated", {"cancelled_at": "2026-01-01T00:00:00Z"}, "cancelled"),
])
def test_order_lifecycle_priority_is_stable(topic, payload, expected):
    assert _lifecycle_status(payload, topic) == expected


@pytest.mark.parametrize("value,expected", [
    ("partially_paid", "partial"), ("partially_refunded", "partial_refund"),
    ("Paid", "paid"), (" authorized ", "authorized"),
    ("pending", "pending"), ("voided", "voided"),
    ("", None), (None, None),
])
def test_financial_status_aliases_are_normalized(value, expected):
    assert _normalize_payment_status(value) == expected


@pytest.mark.parametrize("value,expected", [
    ("2026-01-01T12:30:00Z", datetime(2026, 1, 1, 12, 30)),
    ("2026-01-01T07:30:00-05:00", datetime(2026, 1, 1, 12, 30)),
    ("2026-01-01T12:30:00+00:00", datetime(2026, 1, 1, 12, 30)),
    (None, None), ("", None), ("not-a-timestamp", None),
])
def test_webhook_timestamps_convert_to_utc_or_reject_invalid(value, expected):
    assert _parse_datetime(value) == expected


def test_webhook_shipping_address_only_includes_bounded_known_fields():
    assert _shipping_address({"shipping_address": []}) is None
    address = _shipping_address({
        "email": " synthetic@example.invalid ",
        "shipping_address": {
            "first_name": " Synthetic ", "last_name": " Customer ",
            "address1": "A" * 600, "phone": "9" * 60,
            "country_code": "co", "unknown_sensitive": "do not persist",
        },
    })
    assert address["customer_name"] == "Synthetic Customer"
    assert len(address["address1"]) == 500
    assert len(address["phone"]) == 50
    assert address["country_code"] == "CO"
    assert address["email"] == "synthetic@example.invalid"
    assert "unknown_sensitive" not in address


def test_currency_selection_preserves_merchant_code_and_fallback():
    assert _currency({"currency": "cop"}, "USD") == "COP"
    assert _currency({}, "COP") == "COP"
    assert _currency({}, "") == "USD"
