"""Record read-only Shopify Partner subscription checks without granting plans.

A check proves that a privileged DIAGLOB actor requested a provider-backed
preview at an instant. It is NOT a subscription, a payment, an entitlement, or
permission to alter organization billing. Shopify always remains authoritative.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection,
    Organization,
    ShopifyBillingVerification,
    Store,
)
from .shopify_app_pricing import SHOPIFY_APP_STORE_PLANS

_ALLOWED_STATUSES = frozenset({
    "plan_verified_no_change",
    "plan_transition_requires_review",
    "subscription_inactive_requires_review",
})
_ALLOWED_PLANS = frozenset({
    "none", "trial", "starter", "growth", "pro", "scale",
})


class ShopifyBillingEvidenceError(ValueError):
    """The remote check no longer matches a trustworthy tenant/installation."""


def record_shopify_billing_verification(
    db: Session,
    *,
    organization_id: int,
    connection_id: int,
    store_id: int,
    installation_connected_at: datetime,
    preview: dict,
) -> ShopifyBillingVerification:
    """Verify live DB state after Partner API returns, then append evidence.

    Locks organization, connection and store when supported by the database.
    A disconnect/reinstall, plan edit, store reassignment or second merchant
    introduced while the Partner request was in flight invalidates the check.
    It NEVER writes organization.plan, billing_provider or subscriptions.
    """
    if (
        type(organization_id) is not int
        or type(connection_id) is not int
        or type(store_id) is not int
        or not isinstance(installation_connected_at, datetime)
        or not isinstance(preview, dict)
        or preview.get("organization_id") != organization_id
        or preview.get("status") not in _ALLOWED_STATUSES
        or preview.get("current_plan") not in _ALLOWED_PLANS
        or preview.get("requires_review") is not True
        or preview.get("applied") is not False
    ):
        raise ShopifyBillingEvidenceError("SHOPIFY_BILLING_EVIDENCE_INVALID")

    target_plan = preview.get("target_plan")
    target_period = preview.get("target_billing_period_months")
    if target_plan is None:
        if preview["status"] != "subscription_inactive_requires_review" or target_period is not None:
            raise ShopifyBillingEvidenceError("SHOPIFY_BILLING_EVIDENCE_INVALID")
    elif (
        target_plan not in SHOPIFY_APP_STORE_PLANS
        or type(target_period) is not int
        or target_period not in {1, 12}
        or preview["status"] == "subscription_inactive_requires_review"
    ):
        raise ShopifyBillingEvidenceError("SHOPIFY_BILLING_EVIDENCE_INVALID")

    # Force a fresh DB read: an OAuth reinstall could have occurred while the
    # remote verifier was querying Shopify. A stale ORM identity map cannot be
    # treated as authority. No provider calls are made under these row locks.
    db.expire_all()
    org = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .first()
    )
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.id == connection_id,
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == store_id,
            CommerceConnection.provider == "shopify",
        )
        .with_for_update()
        .first()
    )
    store = (
        db.query(Store)
        .filter(Store.id == store_id, Store.organization_id == organization_id)
        .with_for_update()
        .first()
    )
    other_shopify = (
        db.query(CommerceConnection.id)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "shopify",
        )
        .limit(2)
        .all()
    )
    if (
        org is None
        or (org.billing_provider or "").lower() != "shopify"
        or (org.plan or "none").lower() != preview["current_plan"]
        or connection is None
        or connection.status != "connected"
        or connection.connected_at != installation_connected_at
        or store is None
        or not store.active
        or store.deleted
        or len(other_shopify) != 1
        or other_shopify[0][0] != connection_id
    ):
        raise ShopifyBillingEvidenceError("SHOPIFY_BILLING_STATE_CHANGED")

    receipt = ShopifyBillingVerification(
        organization_id=organization_id,
        store_id=store_id,
        connection_id=connection_id,
        installation_connected_at=installation_connected_at,
        status=preview["status"],
        current_plan=preview["current_plan"],
        target_plan=target_plan,
        target_period_months=target_period,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt


def list_shopify_billing_verifications(
    db: Session, *, organization_id: int, limit: int = 20
) -> list[dict]:
    if (
        type(organization_id) is not int
        or organization_id < 1
        or type(limit) is not int
        or not 1 <= limit <= 50
    ):
        raise ShopifyBillingEvidenceError("SHOPIFY_BILLING_HISTORY_INVALID")
    records = (
        db.query(ShopifyBillingVerification)
        .filter(ShopifyBillingVerification.organization_id == organization_id)
        .order_by(
            ShopifyBillingVerification.observed_at.desc(),
            ShopifyBillingVerification.id.desc(),
        )
        .limit(limit)
        .all()
    )
    return [
        {
            "id": item.id,
            "organization_id": item.organization_id,
            "store_id": item.store_id,
            "status": item.status,
            "current_plan": item.current_plan,
            "target_plan": item.target_plan,
            "target_billing_period_months": item.target_period_months,
            "observed_at": item.observed_at.isoformat(),
            "requires_review": True,
            "applied": False,
        }
        for item in records
    ]
