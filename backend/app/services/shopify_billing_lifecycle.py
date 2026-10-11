"""Refresh a Shopify App Pricing entitlement after changes without redirects.

Shopify App Pricing does not send subscription webhooks. This function can be
called by the authenticated merchant or a separately scheduled backend task.
Provider failures never fabricate an inactive contract; a confirmed absent or
unexpected contract removes PAID privileges through subscription_status.
"""
from __future__ import annotations

import os
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection, Organization, ShopifyBillingVerification, Store,
)
from .shopify_app_pricing import ShopifyAppPricingError
from .shopify_app_pricing_reconciliation import (
    preview_shopify_entitlement_reconciliation,
)
from .shopify_plan_transition_review import ShopifyTransitionReviewError

_PAID = frozenset({"starter", "growth", "pro", "scale"})


def refresh_shopify_billing_status(db: Session, *, organization_id: int) -> dict:
    """Re-query Partner API and suspend stale/inactive paid plan access.

    This only changes subscription_status, never creates/destroys a
    subscription, edits prices or touches the Paddle billing channel.
    """
    if os.getenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "").lower() != "true":
        raise ShopifyTransitionReviewError("SHOPIFY_ENTITLEMENT_ACTIVATION_DISABLED")
    if type(organization_id) is not int or organization_id < 1:
        raise ShopifyTransitionReviewError("SHOPIFY_BILLING_INVALID_ORGANIZATION")

    org = db.get(Organization, organization_id)
    if org is None or not org.active or (org.billing_provider or "").lower() != "shopify":
        raise ShopifyTransitionReviewError("SHOPIFY_BILLING_PROVENANCE_REQUIRED")
    if org.plan not in _PAID:
        raise ShopifyTransitionReviewError("SHOPIFY_BILLING_NO_MANAGED_PAID_PLAN")
    if org.billing_customer_id or org.billing_subscription_id or org.billing_price_id:
        raise ShopifyTransitionReviewError("SHOPIFY_LEGACY_BILLING_REVIEW_REQUIRED")

    connections = db.query(CommerceConnection).filter(
        CommerceConnection.organization_id == organization_id,
        CommerceConnection.provider == "shopify",
    ).limit(2).all()
    if len(connections) != 1 or connections[0].status != "connected":
        raise ShopifyTransitionReviewError("SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED")
    conn = connections[0]
    store = db.query(Store).filter(
        Store.id == conn.store_id, Store.organization_id == organization_id,
        Store.active.is_(True), Store.deleted.is_(False),
    ).first()
    if store is None:
        raise ShopifyTransitionReviewError("SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED")

    baseline_plan = org.plan
    baseline_period = org.billing_period_months
    installation_epoch = conn.connected_at
    connection_id = conn.id
    store_id = store.id

    # Network calls always happen before row locks.
    try:
        preview = preview_shopify_entitlement_reconciliation(
            org, conn, connected_shopify_store_count=1,
        )
    except ShopifyAppPricingError as exc:
        # Only an actual provider-confirmed *contract mismatch* can revoke
        # stale paid privileges. Connectivity/configuration failures must not
        # be mistaken for a cancellation.
        if str(exc) in {
            "SHOPIFY_PLAN_HANDLE_UNKNOWN",
            "SHOPIFY_PLAN_PRICE_MISMATCH",
            "SHOPIFY_PLAN_PRICE_UNVERIFIED",
            "SHOPIFY_PLAN_ITEMS_UNRECOGNIZED",
            "SHOPIFY_PLAN_INTERVAL_MISMATCH",
        }:
            preview = SimpleNamespace(
                organization_id=organization_id,
                current_plan=baseline_plan,
                target_plan=None,
                target_billing_period_months=None,
                status="subscription_unrecognized_requires_review",
            )
        else:
            raise ShopifyTransitionReviewError(str(exc)) from exc
    if preview.organization_id != organization_id or preview.current_plan != baseline_plan:
        raise ShopifyTransitionReviewError("SHOPIFY_BILLING_STATE_CHANGED")
    if preview.status not in {
        "plan_verified_no_change",
        "plan_transition_requires_review",
        "subscription_inactive_requires_review",
        "subscription_unrecognized_requires_review",
    }:
        raise ShopifyTransitionReviewError("SHOPIFY_BILLING_INVALID_VERIFICATION")

    # Partner API is authoritative; no active contract or an unexpected plan
    # makes previously paid access unavailable until the owner resolves it.
    new_state = {
        "plan_verified_no_change": "active",
        "plan_transition_requires_review": "review_required",
        "subscription_inactive_requires_review": "inactive",
        "subscription_unrecognized_requires_review": "review_required",
    }[preview.status]
    db.expire_all()
    org = db.query(Organization).filter(
        Organization.id == organization_id
    ).with_for_update().first()
    conn = db.query(CommerceConnection).filter(
        CommerceConnection.id == connection_id,
        CommerceConnection.organization_id == organization_id,
        CommerceConnection.store_id == store_id,
        CommerceConnection.provider == "shopify",
    ).with_for_update().first()
    store = db.query(Store).filter(
        Store.id == store_id, Store.organization_id == organization_id,
    ).with_for_update().first()
    bindings = db.query(CommerceConnection.id).filter(
        CommerceConnection.organization_id == organization_id,
        CommerceConnection.provider == "shopify",
    ).limit(2).all()
    if not (
        org and org.active and org.billing_provider == "shopify"
        and org.plan == baseline_plan
        and org.billing_period_months == baseline_period
        and not org.billing_customer_id and not org.billing_subscription_id
        and not org.billing_price_id
        and conn and conn.status == "connected"
        and conn.connected_at == installation_epoch
        and store and store.active and not store.deleted
        and len(bindings) == 1 and bindings[0][0] == connection_id
    ):
        raise ShopifyTransitionReviewError("SHOPIFY_BILLING_STATE_CHANGED")

    changed = org.subscription_status != new_state
    org.subscription_status = new_state
    record = ShopifyBillingVerification(
        organization_id=organization_id,
        store_id=store_id, connection_id=connection_id,
        installation_connected_at=installation_epoch,
        status=preview.status,
        current_plan=baseline_plan,
        target_plan=preview.target_plan,
        target_period_months=preview.target_billing_period_months,
        observed_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    return {
        "organization_id": organization_id,
        "subscription_status": new_state,
        "changed": changed,
        "verified_against_shopify": True,
        "verification_id": record.id,
        "plan": baseline_plan,
        "applied": changed,
    }
