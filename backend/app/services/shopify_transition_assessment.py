"""Read-only Shopify transition proposal assessment.

This is a UX/operational preflight, not proof of payment, eligibility to
activate a plan, or an entitlement authorization. The remote Shopify provider
MUST be verified again before any future change to organization billing.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection,
    Organization,
    ShopifyBillingVerification,
    ShopifyPlanTransitionReview,
    Store,
)
from .billing_channel_policy import paddle_migration_cancellation_verified
from .shopify_plan_transition_review import (
    REVIEW_TTL,
    ShopifyTransitionReviewError,
)

_MAX_CLOCK_SKEW = timedelta(minutes=1)


def assess_shopify_transition_review(
    db: Session,
    *,
    organization_id: int,
    review_id: int,
    now: datetime | None = None,
) -> dict:
    """Return current DB blockers for a previously staged plan review.

    One read-only snapshot for operational guidance. Even a completely clear
    preflight is NOT an authorization: it does not contact Shopify Partner,
    lock rows, approve a payment, or write organization entitlements.
    """
    if (
        type(organization_id) is not int
        or organization_id <= 0
        or type(review_id) is not int
        or review_id <= 0
    ):
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_INVALID_ID")
    checked_at = now if now is not None else datetime.utcnow()
    if not isinstance(checked_at, datetime) or checked_at.tzinfo is not None:
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_INVALID_TIME")

    db.expire_all()
    review = (
        db.query(ShopifyPlanTransitionReview)
        .filter(
            ShopifyPlanTransitionReview.id == review_id,
            ShopifyPlanTransitionReview.organization_id == organization_id,
        )
        .first()
    )
    if review is None:
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_NOT_FOUND")

    blockers: list[str] = []

    def block(code: str) -> None:
        if code not in blockers:
            blockers.append(code)

    if review.status != "pending_review":
        block("REVIEW_NOT_PENDING")
    if review.expires_at <= checked_at or review.created_at > checked_at + _MAX_CLOCK_SKEW:
        block("REVIEW_EXPIRED")

    verification = (
        db.query(ShopifyBillingVerification)
        .filter(
            ShopifyBillingVerification.id == review.verification_id,
            ShopifyBillingVerification.organization_id == organization_id,
        )
        .first()
    )
    latest = (
        db.query(ShopifyBillingVerification.id)
        .filter(ShopifyBillingVerification.organization_id == organization_id)
        .order_by(
            ShopifyBillingVerification.observed_at.desc(),
            ShopifyBillingVerification.id.desc(),
        )
        .first()
    )
    if verification is None:
        block("VERIFICATION_MISSING")
    else:
        if latest is None or latest[0] != verification.id:
            block("NEWER_VERIFICATION_EXISTS")
        if (
            verification.observed_at > checked_at + _MAX_CLOCK_SKEW
            or checked_at - verification.observed_at >= REVIEW_TTL
        ):
            block("VERIFICATION_EXPIRED")
        if (
            verification.status != "plan_transition_requires_review"
            or verification.current_plan != review.baseline_plan
            or verification.target_plan != review.target_plan
            or verification.target_period_months != review.target_period_months
            or verification.store_id != review.store_id
            or verification.connection_id != review.connection_id
            or verification.installation_connected_at != review.installation_connected_at
        ):
            block("VERIFICATION_MISMATCH")

    organization = db.query(Organization).filter(
        Organization.id == organization_id
    ).first()
    if organization is None or not organization.active:
        block("ORGANIZATION_INACTIVE")
    else:
        if (organization.billing_provider or "").strip().lower() not in {"shopify", "paddle"}:
            block("BILLING_CHANNEL_CHANGED")
        if (organization.plan or "none").strip().lower() != review.baseline_plan:
            block("BASELINE_PLAN_CHANGED")
        if organization.billing_provider == "paddle" and not paddle_migration_cancellation_verified(db, organization):
            block("BILLING_CHANNEL_CHANGED")
            block("PADDLE_CANCELLATION_REQUIRED")
        elif organization.billing_provider == "shopify" and (
            organization.billing_customer_id or organization.billing_subscription_id
        ):
            block("LEGACY_BILLING_REFERENCES")

    connections = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "shopify",
        )
        .limit(2)
        .all()
    )
    if len(connections) != 1 or connections[0].id != review.connection_id:
        block("SHOPIFY_BINDINGS_CHANGED")
    connection = next((c for c in connections if c.id == review.connection_id), None)
    if (
        connection is None
        or connection.store_id != review.store_id
        or connection.status != "connected"
        or connection.connected_at != review.installation_connected_at
    ):
        block("SHOPIFY_INSTALLATION_CHANGED")

    store = (
        db.query(Store)
        .filter(
            Store.id == review.store_id,
            Store.organization_id == organization_id,
        )
        .first()
    )
    if store is None or not store.active or store.deleted:
        block("STORE_UNAVAILABLE")

    blockers.sort()
    clear = not blockers
    return {
        "review_id": review.id,
        "organization_id": organization_id,
        "status": "ready_for_manual_review" if clear else "blocked",
        "ready_for_manual_review": clear,
        "blockers": blockers,
        "checked_at": checked_at.isoformat(),
        "expires_at": review.expires_at.isoformat(),
        "requires_new_shopify_verification_before_activation": True,
        "shopify_reverified_now": False,
        "activation_allowed": False,
        "applied": False,
    }
