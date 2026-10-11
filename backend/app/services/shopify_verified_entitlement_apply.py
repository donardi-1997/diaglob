"""Apply a *newly* verified Shopify App Pricing contract under DB locks.

This code never creates subscriptions or charges. Default OFF for production.
An owner must explicitly request the application of a previously staged review
after Shopify-hosted merchant approval. Never trust redirect plan_handle/shop.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection,
    Organization,
    ShopifyBillingVerification,
    ShopifyPlanTransitionReview,
    Store,
)
from .shopify_app_pricing import (
    ShopifyAppPricingError,
    get_active_shopify_subscription,
    resolve_trusted_shop_gid,
    resolve_verified_shopify_plan,
)
from .shopify_plan_transition_review import REVIEW_TTL, ShopifyTransitionReviewError
from .shopify_transition_assessment import assess_shopify_transition_review


def apply_verified_shopify_transition(
    db: Session, *, organization_id: int, review_id: int,
) -> dict:
    """Reconfirm the real active subscription, then compare-and-apply once.

    The Partner/Admin API calls happen before the locked transaction. Every
    field involved in authorization is independently checked again while the
    organization, review, connection and store rows are locked.
    """
    if (
        os.getenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "").lower() != "true"
    ):
        raise ShopifyTransitionReviewError("SHOPIFY_ENTITLEMENT_ACTIVATION_DISABLED")
    if type(organization_id) is not int or organization_id < 1 or type(review_id) is not int or review_id < 1:
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_INVALID_ID")

    existing = (
        db.query(ShopifyPlanTransitionReview)
        .filter(
            ShopifyPlanTransitionReview.id == review_id,
            ShopifyPlanTransitionReview.organization_id == organization_id,
        )
        .first()
    )
    if existing is None:
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_NOT_FOUND")
    if existing.status == "applied":
        org = db.get(Organization, organization_id)
        if (
            org is None or org.billing_provider != "shopify"
            or org.plan != existing.target_plan
            or org.billing_period_months != existing.target_period_months
            or org.subscription_status != "active"
        ):
            raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_ALREADY_APPLIED_STATE_CHANGED")
        return {
            "review_id": review_id, "organization_id": organization_id,
            "applied": False, "already_applied": True,
            "plan": org.plan, "billing_period_months": org.billing_period_months,
        }

    assessment = assess_shopify_transition_review(
        db, organization_id=organization_id, review_id=review_id
    )
    if not assessment["ready_for_manual_review"]:
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_REVIEW_NOT_READY")

    # Capture the exact installed connection epoch BEFORE network calls.
    db.expire_all()
    review = db.get(ShopifyPlanTransitionReview, review_id)
    bound_connection_id = review.connection_id
    bound_store_id = review.store_id
    epoch = review.installation_connected_at
    baseline = review.baseline_plan
    target = review.target_plan
    months = review.target_period_months
    original_verification = review.verification_id
    connection = db.query(CommerceConnection).filter(
        CommerceConnection.id == bound_connection_id,
        CommerceConnection.organization_id == organization_id,
        CommerceConnection.store_id == bound_store_id,
        CommerceConnection.provider == "shopify",
        CommerceConnection.status == "connected",
    ).first()
    if connection is None:
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_INSTALLATION_CHANGED")

    # Fresh Shopify Admin + Partner identity and contract verification.
    try:
        shop_gid = resolve_trusted_shop_gid(connection)
        snapshot = get_active_shopify_subscription(shop_gid)
        if not snapshot.active:
            raise ShopifyAppPricingError("SHOPIFY_NO_ACTIVE_SUBSCRIPTION")
        if snapshot.cancel_at_end_of_cycle:
            raise ShopifyAppPricingError("SHOPIFY_SUBSCRIPTION_CANCELLATION_SCHEDULED")
        confirmed = resolve_verified_shopify_plan(snapshot)
    except ShopifyAppPricingError as exc:
        raise ShopifyTransitionReviewError(str(exc)) from exc
    if confirmed.plan != target or confirmed.billing_period_months != months:
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_PROVIDER_MISMATCH")

    # The first check is not permission. Re-read every binding and baseline
    # under PostgreSQL locks; SQLite is covered by replay/uniqueness tests.
    db.expire_all()
    org = db.query(Organization).filter(
        Organization.id == organization_id
    ).with_for_update().first()
    locked_review = db.query(ShopifyPlanTransitionReview).filter(
        ShopifyPlanTransitionReview.id == review_id,
        ShopifyPlanTransitionReview.organization_id == organization_id,
    ).with_for_update().first()
    conn = db.query(CommerceConnection).filter(
        CommerceConnection.id == bound_connection_id,
        CommerceConnection.organization_id == organization_id,
        CommerceConnection.store_id == bound_store_id,
        CommerceConnection.provider == "shopify",
    ).with_for_update().first()
    store = db.query(Store).filter(
        Store.id == bound_store_id,
        Store.organization_id == organization_id,
    ).with_for_update().first()
    verification = db.query(ShopifyBillingVerification).filter(
        ShopifyBillingVerification.id == original_verification,
        ShopifyBillingVerification.organization_id == organization_id,
    ).first()
    latest = db.query(ShopifyBillingVerification.id).filter(
        ShopifyBillingVerification.organization_id == organization_id,
    ).order_by(
        ShopifyBillingVerification.observed_at.desc(),
        ShopifyBillingVerification.id.desc(),
    ).first()
    bindings = db.query(CommerceConnection.id).filter(
        CommerceConnection.organization_id == organization_id,
        CommerceConnection.provider == "shopify",
    ).limit(2).all()

    now = datetime.utcnow()
    safe = (
        org is not None and org.active
        and (org.billing_provider or "").lower() == "shopify"
        and org.plan == baseline
        and (target != baseline or org.billing_period_months != months)
        and not org.billing_customer_id and not org.billing_subscription_id
        and not org.billing_price_id
        and not org.pending_plan
        and locked_review is not None
        and locked_review.status == "pending_review"
        and locked_review.expires_at > now
        and locked_review.created_at <= now + timedelta(minutes=1)
        and locked_review.verification_id == original_verification
        and locked_review.baseline_plan == baseline
        and locked_review.target_plan == target
        and locked_review.target_period_months == months
        and locked_review.connection_id == bound_connection_id
        and locked_review.store_id == bound_store_id
        and locked_review.installation_connected_at == epoch
        and conn is not None and conn.status == "connected"
        and conn.connected_at == epoch
        and store is not None and store.active and not store.deleted
        and len(bindings) == 1 and bindings[0][0] == bound_connection_id
        and verification is not None
        and verification.status == "plan_transition_requires_review"
        and verification.current_plan == baseline
        and verification.target_plan == target
        and verification.target_period_months == months
        and verification.connection_id == bound_connection_id
        and verification.store_id == bound_store_id
        and verification.installation_connected_at == epoch
        and verification.observed_at <= now + timedelta(minutes=1)
        and now - verification.observed_at < REVIEW_TTL
        and latest is not None and latest[0] == original_verification
    )
    if not safe:
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_STATE_CHANGED")

    org.plan = target
    org.billing_period_months = months
    org.subscription_status = "active"
    locked_review.status = "applied"
    db.commit()
    return {
        "review_id": review_id, "organization_id": organization_id,
        "applied": True, "already_applied": False,
        "plan": target, "billing_period_months": months,
    }
