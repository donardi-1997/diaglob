"""Read-only reconciliation preview for an explicitly Shopify-managed organization.

This service never creates charges, changes organization entitlements, marks
subscriptions active, or updates Paddle contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .shopify_app_pricing import (
    ShopifyAppPricingError,
    get_active_shopify_subscription,
    resolve_trusted_shop_gid,
    resolve_verified_shopify_plan,
)


@dataclass(frozen=True)
class ShopifyEntitlementPreview:
    organization_id: int
    shop_gid: str
    current_plan: str
    target_plan: str | None
    target_billing_period_months: int | None
    verified_handle: str | None
    status: str
    requires_review: bool = True
    # Deliberately no database writes or automatic grants.


def preview_shopify_entitlement_reconciliation(
    organization: Any,
    connection: Any,
    *,
    connected_shopify_store_count: int,
    handle_catalog: dict[str, Any] | None = None,
) -> ShopifyEntitlementPreview:
    """Inspect a single trusted Shopify installation without mutating billing.

    Multi-shop Shopify organizations cannot be reconciled into the legacy
    organization-level single-subscription record until multi-shop policy is
    explicit. The shop count MUST come from a trusted tenant-scoped DB query.
    """
    organization_id = getattr(organization, "id", None)
    if not isinstance(organization_id, int) or isinstance(
        organization_id, bool
    ):
        raise ShopifyAppPricingError("ORGANIZATION_ID_REQUIRED")
    if (getattr(organization, "billing_provider", None) or "").strip().lower() != "shopify":
        raise ShopifyAppPricingError("SHOPIFY_BILLING_PROVENANCE_REQUIRED")
    if (
        getattr(connection, "organization_id", None) != organization_id
        or getattr(connection, "provider", None) != "shopify"
    ):
        raise ShopifyAppPricingError("SHOPIFY_CONNECTION_TENANT_MISMATCH")
    if (
        type(connected_shopify_store_count) is not int
        or connected_shopify_store_count != 1
    ):
        raise ShopifyAppPricingError("SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED")
    if getattr(organization, "billing_subscription_id", None):
        raise ShopifyAppPricingError("EXISTING_SUBSCRIPTION_REVIEW_REQUIRED")
    if getattr(organization, "billing_customer_id", None):
        raise ShopifyAppPricingError("EXISTING_CUSTOMER_BILLING_REVIEW_REQUIRED")

    # Authenticated Admin API identity is always verified before Partner API.
    shop_gid = resolve_trusted_shop_gid(connection)
    subscription = get_active_shopify_subscription(shop_gid)
    current_plan = str(getattr(organization, "plan", None) or "none").lower()

    if not subscription.active:
        # Do not silently deactivate any existing subscription/entitlements.
        return ShopifyEntitlementPreview(
            organization_id=organization_id,
            shop_gid=shop_gid,
            current_plan=current_plan,
            target_plan=None,
            target_billing_period_months=None,
            verified_handle=None,
            status="subscription_inactive_requires_review",
        )

    verified = resolve_verified_shopify_plan(
        subscription,
        handle_catalog=handle_catalog,
    )
    current_months = getattr(organization, "billing_period_months", None)
    same_plan = (
        current_plan == verified.plan
        and current_months == verified.billing_period_months
    )
    return ShopifyEntitlementPreview(
        organization_id=organization_id,
        shop_gid=shop_gid,
        current_plan=current_plan,
        target_plan=verified.plan,
        target_billing_period_months=verified.billing_period_months,
        verified_handle=verified.handle,
        status=(
            "plan_verified_no_change" if same_plan else "plan_transition_requires_review"
        ),
    )
