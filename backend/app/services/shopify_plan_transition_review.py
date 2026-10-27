"""Transactionally stage, never apply, a Shopify-managed plan transition.

A signed Shopify app installation, approved contract terms and current Partner
subscription are still required for actual entitlements. This module does NOT
write Organization.plan, billing_subscription_id, or subscription_status.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection,
    Organization,
    ShopifyBillingVerification,
    ShopifyPlanTransitionReview,
    Store,
)
from .billing_channel_policy import paddle_migration_cancellation_verified
from .shopify_app_pricing import SHOPIFY_APP_STORE_PLANS

REVIEW_TTL = timedelta(minutes=10)
_VALID_TARGET_PLANS = frozenset(SHOPIFY_APP_STORE_PLANS)


class ShopifyTransitionReviewError(ValueError):
    """Safe operational failure code, never untrusted Shopify text."""


def _safe_summary(item: ShopifyPlanTransitionReview, *, now: datetime) -> dict:
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "verification_id": item.verification_id,
        "store_id": item.store_id,
        "baseline_plan": item.baseline_plan,
        "target_plan": item.target_plan,
        "target_billing_period_months": item.target_period_months,
        "status": (
            "stale" if item.status == "pending_review" and
            item.expires_at <= now else item.status
        ),
        "expires_at": item.expires_at.isoformat(),
        "requires_review": True,
        "applied": False,
    }


def prepare_shopify_plan_transition(
    db: Session, *, organization_id: int, verification_id: int
) -> dict:
    """Stage a fresh, single-shop review exactly once in a DB transaction.

    The organization row is the transaction lock on PostgreSQL. A unique
    verification constraint and partial unique pending-org index provide
    second-line replay/concurrency enforcement at the database level.
    """
    if (
        type(organization_id) is not int or organization_id <= 0
        or type(verification_id) is not int or verification_id <= 0
    ):
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_INVALID_ID")

    now = datetime.utcnow()
    db.expire_all()
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .first()
    )
    verification = (
        db.query(ShopifyBillingVerification)
        .filter(
            ShopifyBillingVerification.id == verification_id,
            ShopifyBillingVerification.organization_id == organization_id,
        )
        .first()
    )
    if organization is None or verification is None:
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_NOT_FOUND")

    previous = (
        db.query(ShopifyPlanTransitionReview)
        .filter(
            ShopifyPlanTransitionReview.organization_id == organization_id,
            ShopifyPlanTransitionReview.verification_id == verification_id,
        )
        .first()
    )
    if previous is not None:
        # Retry the exact same proposal without creating another candidate.
        # Expired proposals cannot be treated as approval-ready.
        return _safe_summary(previous, now=now)

    latest = (
        db.query(ShopifyBillingVerification.id)
        .filter(ShopifyBillingVerification.organization_id == organization_id)
        .order_by(
            ShopifyBillingVerification.observed_at.desc(),
            ShopifyBillingVerification.id.desc(),
        )
        .first()
    )
    if (
        verification.status != "plan_transition_requires_review"
        or verification.target_plan not in _VALID_TARGET_PLANS
        or (
            verification.target_plan == verification.current_plan
            and organization.billing_period_months == verification.target_period_months
        )
        or verification.target_period_months not in {1, 12}
        or latest is None or latest[0] != verification_id
        or verification.observed_at > now + timedelta(minutes=1)
        or now - verification.observed_at >= REVIEW_TTL
    ):
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_STALE_VERIFICATION")

    pending = (
        db.query(ShopifyPlanTransitionReview)
        .filter(
            ShopifyPlanTransitionReview.organization_id == organization_id,
            ShopifyPlanTransitionReview.status == "pending_review",
        )
        .with_for_update()
        .all()
    )
    for item in pending:
        if item.expires_at <= now:
            item.status = "stale"
        else:
            raise ShopifyTransitionReviewError(
                "SHOPIFY_TRANSITION_REVIEW_ALREADY_PENDING"
            )
    db.flush()

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.id == verification.connection_id,
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == verification.store_id,
            CommerceConnection.provider == "shopify",
        )
        .with_for_update()
        .first()
    )
    store = (
        db.query(Store)
        .filter(
            Store.id == verification.store_id,
            Store.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )
    bindings = (
        db.query(CommerceConnection.id)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "shopify",
        )
        .limit(2)
        .all()
    )
    if (
        not organization.active
        or (organization.billing_provider or "").strip().lower() not in {"shopify", "paddle"}
        or (organization.plan or "none").strip().lower() != verification.current_plan
        or (organization.billing_provider == "paddle" and not paddle_migration_cancellation_verified(db, organization))
        or (organization.billing_provider == "shopify" and (
            organization.billing_subscription_id or organization.billing_customer_id
        ))
        or connection is None
        or connection.status != "connected"
        or connection.connected_at != verification.installation_connected_at
        or store is None or not store.active or store.deleted
        or len(bindings) != 1 or bindings[0][0] != connection.id
    ):
        raise ShopifyTransitionReviewError(
            "SHOPIFY_TRANSITION_INSTALLATION_OR_PLAN_CHANGED"
        )

    proposal = ShopifyPlanTransitionReview(
        organization_id=organization_id,
        verification_id=verification_id,
        store_id=verification.store_id,
        connection_id=verification.connection_id,
        installation_connected_at=verification.installation_connected_at,
        baseline_plan=verification.current_plan,
        target_plan=verification.target_plan,
        target_period_months=verification.target_period_months,
        status="pending_review",
        created_at=now,
        expires_at=verification.observed_at + REVIEW_TTL,
    )
    db.add(proposal)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # A simultaneous caller may have claimed the same verification or
        # the organization's single pending slot. Never grant either caller.
        raise ShopifyTransitionReviewError(
            "SHOPIFY_TRANSITION_CONCURRENT_REVIEW"
        ) from exc
    db.refresh(proposal)
    return _safe_summary(proposal, now=now)


def list_shopify_plan_transition_reviews(
    db: Session, *, organization_id: int, limit: int = 20
) -> list[dict]:
    if (
        type(organization_id) is not int or organization_id <= 0
        or type(limit) is not int or not 1 <= limit <= 50
    ):
        raise ShopifyTransitionReviewError("SHOPIFY_TRANSITION_HISTORY_INVALID")
    now = datetime.utcnow()
    records = (
        db.query(ShopifyPlanTransitionReview)
        .filter(ShopifyPlanTransitionReview.organization_id == organization_id)
        .order_by(ShopifyPlanTransitionReview.id.desc())
        .limit(limit)
        .all()
    )
    return [_safe_summary(item, now=now) for item in records]


def activate_shopify_plan_transition(*, review_id: int) -> None:
    """Deliberate hard stop: staged reviews are NEVER payment authorizations.

    There is no production activation route or feature flag. Implement a
    separate verified recheck + approved transactional grant when commercial
    agreements, customer data policies and multistore rules are finalized.
    """
    raise ShopifyTransitionReviewError("SHOPIFY_ENTITLEMENT_ACTIVATION_DISABLED")
