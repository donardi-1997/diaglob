"""Read-only reconciliation preview for an explicitly Shopify-managed organization.

This service never creates charges, changes organization entitlements, marks
subscriptions active, or updates Paddle contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .shopify_app_pricing import (
    SHOPIFY_APP_PRICING_INTERVAL_TO_MONTHS,
    SHOPIFY_APP_STORE_TRIAL_DAYS,
    ShopifyAppPricingError,
    get_active_shopify_subscription,
    get_shopify_trial_evidence,
    is_trusted_partner_development_shop,
    resolve_trusted_shop_gid,
    resolve_verified_shopify_plan,
    subscription_has_no_charge_effective_price,
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
    trial_ends_at: str | None = None
    has_pending_update: bool = False
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
    migration = (getattr(organization, "billing_provider", None) or "").strip().lower() == "paddle"
    if (getattr(organization, "billing_provider", None) or "").strip().lower() != "shopify" and not migration:
        raise ShopifyAppPricingError("SHOPIFY_BILLING_PROVENANCE_REQUIRED")
    if migration and (
        getattr(organization, "subscription_status", None) != "canceled"
        or getattr(organization, "auto_renew_enabled", True)
    ):
        raise ShopifyAppPricingError("PADDLE_MIGRATION_CANCELLATION_REQUIRED")
    if migration and not getattr(organization, "billing_subscription_id", None):
        raise ShopifyAppPricingError("PADDLE_MIGRATION_SUBSCRIPTION_MISSING")
    if (
        getattr(connection, "organization_id", None) != organization_id
        or getattr(connection, "provider", None) != "shopify"
    ):
        raise ShopifyAppPricingError("SHOPIFY_CONNECTION_TENANT_MISMATCH")
    if getattr(connection, "status", None) != "connected":
        raise ShopifyAppPricingError("SHOPIFY_CONNECTION_NOT_ACTIVE")
    if (
        type(connected_shopify_store_count) is not int
        or connected_shopify_store_count != 1
    ):
        raise ShopifyAppPricingError("SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED")
    if getattr(organization, "billing_subscription_id", None) and not migration:
        raise ShopifyAppPricingError("EXISTING_SUBSCRIPTION_REVIEW_REQUIRED")
    if getattr(organization, "billing_customer_id", None) and not migration:
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
            trial_ends_at=None,
            has_pending_update=False,
        )

    allow_no_charge_testing = False
    if subscription_has_no_charge_effective_price(subscription):
        allow_no_charge_testing = is_trusted_partner_development_shop(
            connection,
            expected_shop_gid=shop_gid,
        )

    verified = resolve_verified_shopify_plan(
        subscription,
        handle_catalog=handle_catalog,
        allow_no_charge_testing=allow_no_charge_testing,
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
        trial_ends_at=subscription.trial_ends_at,
        has_pending_update=subscription.has_pending_update,
    )


def verify_shopify_trial_contract(
    organization: Any,
    connection: Any,
    *,
    connected_shopify_store_count: int,
    handle_catalog: dict[str, Any] | None = None,
) -> dict:
    """Compare the current plan's Partner event trial setting with DIAGLOB's contract."""
    preview = preview_shopify_entitlement_reconciliation(
        organization,
        connection,
        connected_shopify_store_count=connected_shopify_store_count,
        handle_catalog=handle_catalog,
    )
    if (
        preview.target_plan is None
        or preview.target_billing_period_months is None
        or preview.verified_handle is None
    ):
        raise ShopifyAppPricingError("SHOPIFY_TRIAL_EVIDENCE_NO_ACTIVE_PLAN")

    interval = next(
        (
            key
            for key, months in SHOPIFY_APP_PRICING_INTERVAL_TO_MONTHS.items()
            if months == preview.target_billing_period_months
        ),
        None,
    )
    if interval is None:
        raise ShopifyAppPricingError("SHOPIFY_TRIAL_EVIDENCE_INVALID")

    evidence = get_shopify_trial_evidence(
        preview.shop_gid,
        current_handle=preview.verified_handle,
        current_billing_period=interval,
    )
    return {
        "organization_id": preview.organization_id,
        "plan": preview.target_plan,
        "billing_period_months": preview.target_billing_period_months,
        "expected_trial_days": SHOPIFY_APP_STORE_TRIAL_DAYS,
        "observed_trial_days": evidence.trial_days,
        "trial_days_remaining": evidence.trial_days_remaining,
        "trial_ends_at": preview.trial_ends_at,
        "matches_expected": evidence.trial_days == SHOPIFY_APP_STORE_TRIAL_DAYS,
        "verified_against_shopify": True,
        "applied": False,
    }
