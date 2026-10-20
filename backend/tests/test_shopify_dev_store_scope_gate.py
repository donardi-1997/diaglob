"""Read-only DIAGLOB dev-store scope-gate tests; never call Shopify."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from app.shopify_oauth import SHOPIFY_SCOPES
from tools import shopify_dev_store_scope_gate as gate


APP_KEY = "c5fc9aed710462d41767477fa9e595c0"
SHOP = "diaglob-poc.myshopify.com"
REQUIRED = set(SHOPIFY_SCOPES.split(","))
LEGACY = {
    "read_customers", "read_inventory", "read_orders",
    "read_products", "write_orders", "write_products",
}


def _payload(requested=None, granted=None, optional=()):
    if requested is None:
        requested = REQUIRED
    if granted is None:
        granted = REQUIRED
    return {
        "shop": {"myshopifyDomain": SHOP},
        "appByKey": {
            "apiKey": APP_KEY,
            "requestedAccessScopes": [
                {"handle": name} for name in sorted(requested)
            ],
            "optionalAccessScopes": [
                {"handle": name} for name in sorted(optional)
            ],
            "installation": {
                "accessScopes": [
                    {"handle": name} for name in sorted(granted)
                ]
            },
        },
    }


def _inspect(payload, **changes):
    return gate.inspect_shopify_dev_store_scopes(
        payload, expected_shop=changes.get("shop", SHOP),
        app_key=changes.get("app_key", APP_KEY),
        source_scopes=changes.get("source_scopes", SHOPIFY_SCOPES),
        toml_scopes=changes.get("toml_scopes", SHOPIFY_SCOPES),
    )


def test_remote_query_identifies_exact_app_without_protected_fields():
    assert "appByKey(apiKey:" in gate.QUERY
    assert "requestedAccessScopes" in gate.QUERY
    assert "optionalAccessScopes" in gate.QUERY
    assert "installation" in gate.QUERY
    assert "accessScopes" in gate.QUERY
    assert "myshopifyDomain" in gate.QUERY
    for forbidden in ("customer {", "customers(", "orders(", "email", "phone", "address"):
        assert forbidden not in gate.QUERY.lower()


def test_matching_source_shopify_requested_and_granted_passes_only_scope_gate():
    report = _inspect(_payload())
    assert report["scope_gate_passed"] is True
    assert report["remote_requested_parity"] is True
    assert report["remote_granted_parity"] is True
    assert report["protected_customer_data_approval_verified"] is False
    assert report["shopify_app_version_verified"] is False
    assert report["merchant_installation_e2e_verified"] is False


def test_real_observed_legacy_grants_are_blocked():
    """Synthetic reconstruction of 2026-10-20 Shopify API metadata."""
    report = _inspect(_payload(requested=LEGACY, granted=LEGACY))
    assert report["app_found_by_key"] is True
    assert report["installed"] is True
    assert report["source_toml_parity"] is True
    assert report["remote_requested_parity"] is False
    assert report["remote_granted_parity"] is False
    assert report["scope_gate_passed"] is False
    assert report["requested_extra"] == ["read_customers", "write_products"]
    assert report["granted_extra"] == ["read_customers", "write_products"]
    expected_missing = sorted({
        "write_draft_orders",
        "read_merchant_managed_fulfillment_orders",
        "write_merchant_managed_fulfillment_orders",
    })
    assert report["requested_missing"] == expected_missing
    assert report["granted_missing"] == expected_missing
    assert "token" not in str(report).lower()


def test_source_and_toml_mismatch_blocks_even_when_remote_grants_match():
    report = _inspect(
        _payload(),
        toml_scopes=SHOPIFY_SCOPES + ",read_customers",
    )
    assert report["source_toml_parity"] is False
    assert report["scope_gate_passed"] is False


def test_requested_granted_drift_blocks_even_if_grants_match_source():
    report = _inspect(_payload(requested=LEGACY, granted=REQUIRED))
    assert report["remote_granted_parity"] is True
    assert report["remote_requested_parity"] is False
    assert report["scope_gate_passed"] is False


def test_revoked_or_missing_grant_blocks():
    report = _inspect(_payload(granted=REQUIRED - {"read_orders"}))
    assert report["granted_missing"] == ["read_orders"]
    assert report["scope_gate_passed"] is False


def test_optional_scopes_trigger_review_even_if_required_exact():
    report = _inspect(_payload(optional={"read_customers"}))
    assert report["shopify_optional_scopes"] == ["read_customers"]
    assert report["scope_gate_passed"] is False


def test_app_not_installed_never_reports_parity():
    payload = _payload()
    payload["appByKey"]["installation"] = None
    report = _inspect(payload)
    assert report["installed"] is False
    assert report["scope_gate_passed"] is False
    assert report["remote_granted_parity"] is False


def test_missing_app_is_distinct_from_missing_grants():
    report = _inspect({"shop": {"myshopifyDomain": SHOP}, "appByKey": None})
    assert report["app_found_by_key"] is False
    assert report["installed"] is False
    assert report["scope_gate_passed"] is False


@pytest.mark.parametrize("broken", [
    None,
    {},
    {"shop": None, "appByKey": None},
    {"shop": {"myshopifyDomain": "wrong.myshopify.com"}, "appByKey": None},
])
def test_invalid_response_or_wrong_shop_fails_closed(broken):
    with pytest.raises(ValueError, match="SHOPIFY_SCOPE_GATE_"):
        _inspect(broken)


def test_wrong_client_id_is_rejected():
    payload = _payload()
    payload["appByKey"]["apiKey"] = "a" * 32
    with pytest.raises(ValueError, match="SHOPIFY_SCOPE_GATE_WRONG_APP"):
        _inspect(payload)


@pytest.mark.parametrize("field", [
    "requestedAccessScopes", "optionalAccessScopes",
])
def test_missing_remote_scope_arrays_fail_closed(field):
    payload = _payload()
    payload["appByKey"].pop(field)
    with pytest.raises(ValueError, match="SHOPIFY_SCOPE_GATE_INVALID_REMOTE_RESPONSE"):
        _inspect(payload)


def test_invalid_grants_are_not_silently_treated_as_empty():
    payload = _payload()
    payload["appByKey"]["installation"]["accessScopes"] = [{"handle": ""}]
    with pytest.raises(ValueError, match="SHOPIFY_SCOPE_GATE_INVALID_REMOTE_RESPONSE"):
        _inspect(payload)


def test_duplicate_grants_fail_closed():
    payload = _payload()
    payload["appByKey"]["installation"]["accessScopes"].append({"handle": "read_orders"})
    with pytest.raises(ValueError, match="SHOPIFY_SCOPE_GATE_INVALID_REMOTE_RESPONSE"):
        _inspect(payload)


def test_main_never_prints_remote_token(monkeypatch, capsys):
    token = "synthetic_token_do_not_echo_12345"
    monkeypatch.setenv("SHOPIFY_AUDIT_SHOP", SHOP)
    monkeypatch.setenv("SHOPIFY_AUDIT_ACCESS_TOKEN", token)
    monkeypatch.setattr(gate, "read_source_config", lambda: (APP_KEY, SHOPIFY_SCOPES))
    client = Mock()
    client.query.return_value = _payload(requested=LEGACY, granted=LEGACY)
    monkeypatch.setattr(gate, "ShopifyGraphQLClient", lambda shop, secret: client)
    assert gate.main() == 2
    printed = capsys.readouterr().out
    assert token not in printed
    assert "scope_gate_passed" in printed
    client.query.assert_called_once()
