"""Security and read-only tests for the owner-only Shopify billing preview."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.billing import preview_shopify_billing_reconciliation, router
from app.services.shopify_app_pricing import ShopifyAppPricingError
from app.services.shopify_app_pricing_reconciliation import ShopifyEntitlementPreview


def _membership(*, role="owner", provider="shopify"):
    organization = SimpleNamespace(
        id=17,
        plan="none",
        billing_provider=provider,
        billing_subscription_id=None,
        billing_customer_id=None,
    )
    return SimpleNamespace(
        role=role, organization_id=17, organization=organization
    )


def _db(*connections):
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = list(
        connections
    )
    return db


def _connection():
    return SimpleNamespace(
        organization_id=17,
        store_id=23,
        provider="shopify",
        status="connected",
    )


def test_preview_route_exists_and_uses_get():
    assert any(
        route.path == "/api/billing/shopify/reconciliation-preview"
        and "GET" in route.methods
        for route in router.routes
    )


@pytest.mark.parametrize("role", ["operator", "analyst", "viewer"])
def test_non_billing_roles_cannot_preview_or_query_provider(role):
    db = _db(_connection())
    with patch("app.api.billing.preview_shopify_entitlement_reconciliation") as upstream:
        with pytest.raises(HTTPException) as exc:
            preview_shopify_billing_reconciliation(
                membership=_membership(role=role),
                db=db,
            )
        assert exc.value.status_code == 403
        db.query.assert_not_called()
        upstream.assert_not_called()


@pytest.mark.parametrize("provider", [None, "paddle", ""])
def test_non_shopify_organization_cannot_invoke_partner_api(provider):
    db = _db(_connection())
    with patch("app.api.billing.preview_shopify_entitlement_reconciliation") as upstream:
        with pytest.raises(HTTPException) as exc:
            preview_shopify_billing_reconciliation(
                membership=_membership(provider=provider),
                db=db,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SHOPIFY_BILLING_PROVENANCE_REQUIRED"
        db.query.assert_not_called()
        upstream.assert_not_called()


@pytest.mark.parametrize("count", [0, 2])
def test_unresolved_or_multiple_stores_fail_before_partner_api(count):
    db = _db(*[_connection() for _ in range(count)])
    with patch("app.api.billing.preview_shopify_entitlement_reconciliation") as upstream:
        with pytest.raises(HTTPException) as exc:
            preview_shopify_billing_reconciliation(
                membership=_membership(),
                db=db,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED"
        upstream.assert_not_called()
        db.commit.assert_not_called()


def test_verified_plan_is_review_only_without_secrets_or_mutations():
    membership = _membership()
    connection = _connection()
    db = _db(connection)
    result = ShopifyEntitlementPreview(
        organization_id=17,
        shop_gid="gid://shopify/Shop/999",
        current_plan="none",
        target_plan="growth",
        target_billing_period_months=12,
        verified_handle="private-plan-handle",
        status="plan_transition_requires_review",
    )
    with patch(
        "app.api.billing.preview_shopify_entitlement_reconciliation",
        return_value=result,
    ) as service:
        response = preview_shopify_billing_reconciliation(
            membership=membership,
            db=db,
        )
    service.assert_called_once_with(
        membership.organization,
        connection,
        connected_shopify_store_count=1,
    )
    assert response == {
        "status": "plan_transition_requires_review",
        "requires_review": True,
        "current_plan": "none",
        "target_plan": "growth",
        "target_billing_period_months": 12,
        "organization_id": 17,
        "applied": False,
    }
    assert "private-plan-handle" not in str(response)
    assert "gid://shopify/Shop/999" not in str(response)
    db.commit.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.parametrize(
    "error,status",
    [
        ("SHOPIFY_PARTNER_API_NOT_CONFIGURED", 503),
        ("SHOPIFY_PARTNER_API_UNAVAILABLE", 503),
        ("SHOPIFY_PLAN_HANDLE_UNKNOWN", 409),
        ("SHOPIFY_SUBSCRIPTION_SHOP_MISMATCH", 409),
    ],
)
def test_provider_failures_are_explicit_and_never_grant_entitlements(error, status):
    db = _db(_connection())
    with patch(
        "app.api.billing.preview_shopify_entitlement_reconciliation",
        side_effect=ShopifyAppPricingError(error),
    ):
        with pytest.raises(HTTPException) as exc:
            preview_shopify_billing_reconciliation(
                membership=_membership(),
                db=db,
            )
    assert exc.value.status_code == status
    assert exc.value.detail == {"code": error}
    db.commit.assert_not_called()


def test_untrusted_provider_error_is_not_reflected_to_client():
    db = _db(_connection())
    with patch(
        "app.api.billing.preview_shopify_entitlement_reconciliation",
        side_effect=ShopifyAppPricingError("provider failure: secret=private-value"),
    ):
        with pytest.raises(HTTPException) as exc:
            preview_shopify_billing_reconciliation(
                membership=_membership(),
                db=db,
            )
    assert exc.value.status_code == 503
    assert exc.value.detail == {"code": "SHOPIFY_RECONCILIATION_UNAVAILABLE"}
    db.commit.assert_not_called()


def test_manager_role_can_review_verified_plan():
    membership = _membership(role="manager")
    connection = _connection()
    db = _db(connection)
    verified = ShopifyEntitlementPreview(
        organization_id=17,
        shop_gid="gid://shopify/Shop/100",
        current_plan="starter",
        target_plan="starter",
        target_billing_period_months=1,
        verified_handle="verified-handle",
        status="plan_verified_no_change",
    )
    with patch(
        "app.api.billing.preview_shopify_entitlement_reconciliation",
        return_value=verified,
    ) as service:
        response = preview_shopify_billing_reconciliation(
            membership=membership,
            db=db,
        )
    assert response["requires_review"] is True
    assert response["applied"] is False
    assert response["status"] == "plan_verified_no_change"
    service.assert_called_once()
    db.commit.assert_not_called()
