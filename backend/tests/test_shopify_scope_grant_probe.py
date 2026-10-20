"""No network requests or real tokens: verification of grant probe contracts."""
import pytest

from app.shopify_oauth import SHOPIFY_SCOPES
from tools.shopify_scope_grant_probe import inspect_granted_scopes, SCOPE_QUERY


def test_probe_queries_current_installation_without_customer_details():
    assert "currentAppInstallation" in SCOPE_QUERY
    assert "accessScopes" in SCOPE_QUERY
    assert "handle" in SCOPE_QUERY
    assert "customers(" not in SCOPE_QUERY
    assert "email" not in SCOPE_QUERY


def test_probe_requires_seven_scopes_but_does_not_claim_pcd_approval():
    required = set(SHOPIFY_SCOPES.split(","))
    report = inspect_granted_scopes({
        "currentAppInstallation": {
            "accessScopes": [{"handle": handle} for handle in sorted(required)]
        }
    })
    assert report["grant_parity"] is True
    assert report["missing_from_current_grant"] == []
    assert report["protected_customer_data_approval_verified"] is False


def test_probe_reports_legacy_customer_scope_as_extra_grant():
    required = set(SHOPIFY_SCOPES.split(","))
    report = inspect_granted_scopes({
        "currentAppInstallation": {
            "accessScopes": [
                {"handle": handle}
                for handle in sorted(required | {"read_customers"})
            ]
        }
    })
    assert report["grant_parity"] is True
    assert report["additional_existing_grants"] == ["read_customers"]


def test_probe_fails_closed_on_missing_permission():
    required = set(SHOPIFY_SCOPES.split(","))
    report = inspect_granted_scopes({
        "currentAppInstallation": {
            "accessScopes": [
                {"handle": handle} for handle in sorted(required - {"read_orders"})
            ]
        }
    })
    assert report["grant_parity"] is False
    assert report["missing_from_current_grant"] == ["read_orders"]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"currentAppInstallation": None},
        {"currentAppInstallation": {"accessScopes": None}},
        {"currentAppInstallation": {"accessScopes": [{}]}},
        {"currentAppInstallation": {"accessScopes": [{"handle": ""}]}},
    ],
)
def test_probe_rejects_malformed_or_partial_data(payload):
    with pytest.raises(ValueError, match="SHOPIFY_SCOPE_AUDIT_INVALID_RESPONSE"):
        inspect_granted_scopes(payload)
