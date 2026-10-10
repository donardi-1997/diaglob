"""No-charge, read-only Shopify App Pricing reconciliation tests."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.shopify_app_pricing import (
    ShopifyAppPricingError,
    ShopifySubscriptionSnapshot,
)
from app.services.shopify_app_pricing_reconciliation import (
    preview_shopify_entitlement_reconciliation,
)


CATALOG = {
    "shopify-starter-monthly": {
        "plan": "starter",
        "interval": "EVERY_30_DAYS",
    },
}


def _org(**kwargs):
    values = dict(
        id=17, billing_provider="shopify",
        billing_subscription_id=None, billing_customer_id=None,
        plan="none", billing_period_months=1,
    )
    values.update(kwargs)
    return SimpleNamespace(**values)


def _connection(**kwargs):
    values = dict(organization_id=17, provider="shopify", status="connected")
    values.update(kwargs)
    return SimpleNamespace(**values)


def _subscription(active=True):
    if not active:
        return ShopifySubscriptionSnapshot(active=False)
    return ShopifySubscriptionSnapshot(
        active=True,
        billing_period="EVERY_30_DAYS",
        item_handles=("shopify-starter-monthly",),
        eligible_handles=("shopify-starter-monthly",),
    )


def test_verified_shopify_plan_can_be_previewed_without_granting_entitlements():
    org = _org()
    with patch(
        "app.services.shopify_app_pricing_reconciliation.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/100",
    ) as identity, patch(
        "app.services.shopify_app_pricing_reconciliation.get_active_shopify_subscription",
        return_value=_subscription(),
    ) as partner:
        result = preview_shopify_entitlement_reconciliation(
            org,
            _connection(),
            connected_shopify_store_count=1,
            handle_catalog=CATALOG,
        )

    assert result.status == "plan_transition_requires_review"
    assert result.target_plan == "starter"
    assert result.target_billing_period_months == 1
    assert result.requires_review is True
    assert org.plan == "none"
    assert org.billing_provider == "shopify"
    assert org.billing_subscription_id is None
    identity.assert_called_once()
    partner.assert_called_once_with("gid://shopify/Shop/100")


def test_matching_shopify_plan_still_requires_explicit_review():
    org = _org(plan="starter", billing_period_months=1)
    with patch(
        "app.services.shopify_app_pricing_reconciliation.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/100",
    ), patch(
        "app.services.shopify_app_pricing_reconciliation.get_active_shopify_subscription",
        return_value=_subscription(),
    ):
        result = preview_shopify_entitlement_reconciliation(
            org, _connection(),
            connected_shopify_store_count=1, handle_catalog=CATALOG,
        )
    assert result.status == "plan_verified_no_change"
    assert result.requires_review is True


def test_inactive_shopify_subscription_does_not_deactivate_customer():
    org = _org(plan="pro")
    with patch(
        "app.services.shopify_app_pricing_reconciliation.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/100",
    ), patch(
        "app.services.shopify_app_pricing_reconciliation.get_active_shopify_subscription",
        return_value=_subscription(active=False),
    ):
        result = preview_shopify_entitlement_reconciliation(
            org, _connection(),
            connected_shopify_store_count=1, handle_catalog=CATALOG,
        )
    assert result.status == "subscription_inactive_requires_review"
    assert result.target_plan is None
    assert org.plan == "pro"


@pytest.mark.parametrize(
    "organization,connection,count,error",
    [
        (_org(billing_provider=None), _connection(), 1, "PROVENANCE_REQUIRED"),
        (_org(billing_provider="paddle"), _connection(), 1, "PROVENANCE_REQUIRED"),
        (_org(), _connection(organization_id=99), 1, "TENANT_MISMATCH"),
        (_org(), _connection(provider="woocommerce"), 1, "TENANT_MISMATCH"),
        (_org(), _connection(), 2, "MULTISTORE"),
        (_org(), _connection(), 0, "MULTISTORE"),
        (_org(), _connection(), True, "MULTISTORE"),
        (_org(billing_subscription_id="sub_legacy"), _connection(), 1, "EXISTING_SUBSCRIPTION"),
        (_org(billing_customer_id="ctm_legacy"), _connection(), 1, "EXISTING_CUSTOMER"),
    ],
)
def test_unverified_provenance_and_paddle_contracts_fail_before_provider_calls(
    organization, connection, count, error
):
    with patch(
        "app.services.shopify_app_pricing_reconciliation.resolve_trusted_shop_gid"
    ) as identity, patch(
        "app.services.shopify_app_pricing_reconciliation.get_active_shopify_subscription"
    ) as partner:
        with pytest.raises(ShopifyAppPricingError, match=error):
            preview_shopify_entitlement_reconciliation(
                organization, connection,
                connected_shopify_store_count=count,
                handle_catalog=CATALOG,
            )
        identity.assert_not_called()
        partner.assert_not_called()


def test_unknown_provider_handle_does_not_grant_plan():
    with patch(
        "app.services.shopify_app_pricing_reconciliation.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/100",
    ), patch(
        "app.services.shopify_app_pricing_reconciliation.get_active_shopify_subscription",
        return_value=_subscription(),
    ):
        with pytest.raises(ShopifyAppPricingError, match="HANDLE_UNKNOWN"):
            preview_shopify_entitlement_reconciliation(
                _org(), _connection(), connected_shopify_store_count=1,
                handle_catalog={"unknown": {"plan": "starter", "interval": "EVERY_30_DAYS"}},
            )
