"""Privacy intake canonicalization and checkout pilot safety regression matrix.

Pure synthetic inputs only: never trigger real export, erasure or Shopify actions.
"""
import pytest

from app.services.shopify_compliance_webhooks import (
    _bounded_selector_text, _event_key, _is_shopify_numeric_id,
    _minimal_selectors, _receipt_lookup_keys,
)
from app import shopify_chat_checkout_rollout_audit as rollout


@pytest.mark.parametrize("value", [
    1, 42, "1", "0001", "9" * 32,
])
def test_shopify_ids_accept_only_positive_bounded_decimal_values(value):
    assert _is_shopify_numeric_id(value) is True


@pytest.mark.parametrize("value", [
    None, False, True, 0, -1, 1.0, 0.2,
    "", "0", "-42", "+42", "42.0", "42e1",
    " 42", "42 ", "42\n", "４２", "٤٢", "9" * 33, [], {},
])
def test_shopify_ids_reject_ambiguous_non_numeric_values(value):
    assert _is_shopify_numeric_id(value) is False


def test_minimal_privacy_payload_persists_only_allowlisted_synthetic_selectors():
    payload = {
        "shop_id": 4321,
        "shop_domain": "synthetic.myshopify.com",
        "customer": {
            "id": "42", "email": "buyer@example.invalid",
            "phone": "+570000000000", "address": "do-not-store-address",
            "first_name": "do-not-store-name",
        },
        "orders_to_redact": [11, "12"],
        "orders_requested": [],
        "data_request": {"id": 123, "message": "do-not-store-message"},
        "provider_payload": {"raw": "do-not-store-processor-payload"},
    }
    result = _minimal_selectors(payload)
    assert result == {
        "customer": {
            "id": "42", "email": "buyer@example.invalid",
            "phone": "+570000000000",
        },
        "orders_to_redact": [11, "12"],
        "orders_requested": [],
        "data_request_id": 123,
    }
    assert "address" not in str(result)
    assert "first_name" not in str(result)
    assert "provider_payload" not in str(result)
    assert _minimal_selectors({}) == {"customer": {}}


@pytest.mark.parametrize("payload,code", [
    ({"customer": []}, "INVALID_CUSTOMER"),
    ({"customer": "person@example.invalid"}, "INVALID_CUSTOMER"),
    ({"customer": {"id": False}}, "INVALID_CUSTOMER_ID"),
    ({"customer": {"id": 0}}, "INVALID_CUSTOMER_ID"),
    ({"customer": {"id": "9" * 33}}, "INVALID_CUSTOMER_ID"),
    ({"customer": {"email": ["list"]}}, "INVALID_CUSTOMER_EMAIL"),
    ({"customer": {"email": "a" * 321}}, "INVALID_CUSTOMER_EMAIL"),
    ({"customer": {"email": "synthetic@example.invalid\n"}}, "INVALID_CUSTOMER_EMAIL"),
    ({"customer": {"phone": 57}}, "INVALID_CUSTOMER_PHONE"),
    ({"customer": {"phone": "1" * 51}}, "INVALID_CUSTOMER_PHONE"),
    ({"customer": {"phone": "123\t456"}}, "INVALID_CUSTOMER_PHONE"),
    ({"orders_to_redact": "12"}, "INVALID_ORDER_SELECTORS"),
    ({"orders_requested": [False]}, "INVALID_ORDER_SELECTORS"),
    ({"orders_requested": [-2]}, "INVALID_ORDER_SELECTORS"),
    ({"orders_requested": ["٤٢"]}, "INVALID_ORDER_SELECTORS"),
    ({"orders_requested": list(range(1, 502))}, "INVALID_ORDER_SELECTORS"),
    ({"data_request": []}, "INVALID_DATA_REQUEST"),
    ({"data_request": {"id": 0}}, "INVALID_DATA_REQUEST_ID"),
    ({"data_request": {"id": {"nested": 1}}}, "INVALID_DATA_REQUEST_ID"),
])
def test_invalid_privacy_selectors_are_rejected_with_machine_codes(payload, code):
    with pytest.raises(ValueError, match="^" + code + "$"):
        _minimal_selectors(payload)


def test_privacy_selector_boundaries_allow_exact_configured_limits():
    assert _bounded_selector_text("x" * 320, maximum=320)
    assert not _bounded_selector_text("x" * 321, maximum=320)
    assert not _bounded_selector_text("x\r", maximum=320)
    assert _minimal_selectors({
        "customer": {"email": "x" * 320, "phone": "7" * 50},
        "orders_requested": [1] * 500,
    })["orders_requested"] == [1] * 500


def test_privacy_webhook_id_deduplicates_same_delivery_across_topic_and_shop():
    first = _event_key("customers/redact", {"shop_id": 1}, webhook_id="synthetic-delivery")
    changed_shop = _event_key("shop/redact", {"shop_id": 2}, webhook_id="synthetic-delivery")
    assert first == changed_shop
    assert _event_key("customers/redact", {"shop_id": 1}, webhook_id="different") != first


def test_legacy_unidentified_deliveries_are_order_and_topic_sensitive():
    payload = {"shop_id": 1, "customer": {"id": 42}}
    assert _event_key("customers/redact", payload) == _event_key(
        "customers/redact", {"customer": {"id": 42}, "shop_id": 1}
    )
    assert _event_key("shop/redact", payload) != _event_key("customers/redact", payload)
    keys = _receipt_lookup_keys("customers/redact", payload, "synthetic-delivery")
    assert len(keys) in (1, 2)
    assert keys[0] == _event_key(
        "customers/redact", payload, webhook_id="synthetic-delivery"
    )


@pytest.mark.parametrize("webhook_id", [
    "", " ", "\n", "id with space", "id\nX-Header: forged",
    "x" * 256, "añadido", 42, False, [],
])
def test_invalid_delivery_identifiers_fail_closed(webhook_id):
    with pytest.raises(ValueError, match="INVALID_WEBHOOK_ID"):
        _event_key("shop/redact", {"shop_id": 1}, webhook_id=webhook_id)


def test_missing_shop_id_does_not_produce_a_receipt_key():
    for shop_id in [None, "", 0, False]:
        with pytest.raises(ValueError, match="SHOP_ID_REQUIRED"):
            _event_key("customers/data_request", {"shop_id": shop_id})


@pytest.mark.parametrize("flag", [None, "", "false", "0", "off", "no"])
def test_pilot_disabled_never_opens_a_database_session(monkeypatch, flag):
    monkeypatch.delenv("SHOPIFY_CHAT_CHECKOUT_VIA_DRAFT", raising=False)
    if flag is not None:
        monkeypatch.setenv("SHOPIFY_CHAT_CHECKOUT_VIA_DRAFT", flag)
    monkeypatch.setattr(
        rollout, "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("DB must not be queried")),
    )
    assert rollout.effective_pilot_status() == "disabled"


@pytest.mark.parametrize("org_id,store_id", [
    ("", ""), ("0", "1"), ("1", "0"), ("-1", "1"),
    ("1.5", "1"), ("1", "2e3"), ("nan", "1"),
    ("١", "1"), ("1", "２"), ("  ", "1"),
])
def test_unscoped_pilot_never_opens_a_database_session(monkeypatch, org_id, store_id):
    monkeypatch.setenv("SHOPIFY_CHAT_CHECKOUT_VIA_DRAFT", "true")
    monkeypatch.setenv("SHOPIFY_CHAT_CHECKOUT_POC_ORGANIZATION_ID", org_id)
    monkeypatch.setenv("SHOPIFY_CHAT_CHECKOUT_POC_STORE_ID", store_id)
    monkeypatch.setattr(
        rollout, "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("DB must not be queried")),
    )
    assert rollout.effective_pilot_status() == "blocked_missing_scope"


class SyntheticSession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def _configured_pilot(monkeypatch, connection_or_exception):
    monkeypatch.setenv("SHOPIFY_CHAT_CHECKOUT_VIA_DRAFT", "true")
    monkeypatch.setenv("SHOPIFY_CHAT_CHECKOUT_POC_ORGANIZATION_ID", "42")
    monkeypatch.setenv("SHOPIFY_CHAT_CHECKOUT_POC_STORE_ID", "23")
    monkeypatch.setattr(rollout, "SessionLocal", SyntheticSession)
    queried = []

    def fake_connection(db, checkout):
        queried.append((checkout.organization_id, checkout.store_id))
        if isinstance(connection_or_exception, Exception):
            raise connection_or_exception
        return connection_or_exception

    monkeypatch.setattr(rollout, "_poc_checkout_connection", fake_connection)
    return queried


def test_pilot_ready_requires_a_connection_for_the_exact_shop_scope(monkeypatch):
    queried = _configured_pilot(monkeypatch, object())
    assert rollout.effective_pilot_status() == "scoped_poc_ready"
    assert queried == [(42, 23)]


def test_pilot_without_verified_connection_stays_blocked(monkeypatch):
    queried = _configured_pilot(monkeypatch, None)
    assert rollout.effective_pilot_status() == "blocked"
    assert queried == [(42, 23)]


def test_pilot_query_error_returns_safe_status_without_secret_details(monkeypatch):
    _configured_pilot(monkeypatch, RuntimeError("private-shop-domain and token"))
    status = rollout.effective_pilot_status()
    assert status == "blocked_unverified_connection"
    assert "token" not in status
    assert "private" not in status
