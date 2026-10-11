"""Separate a registration *hint* from the verified Shopify billing channel.

Shopify App Store install URLs are unauthenticated and cannot choose a paid
channel. Only a successfully signed OAuth callback may promote a deliberately
Shopify-pending, never-paid organization. Direct signups use Paddle.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import CommerceConnection, Organization, Store


def registration_billing_channel(origin: str) -> tuple[str, str | None]:
    """Only these explicitly supported self-service signup origins may register."""
    if origin == "direct":
        return ("direct", "paddle")
    if origin == "shopify_install":
        return ("shopify_install", None)
    raise ValueError("INVALID_REGISTRATION_BILLING_ORIGIN")


def confirm_shopify_install_billing(
    db: Session,
    *,
    organization_id: int,
    connection_id: int,
) -> bool:
    """Upgrade pending onboarding to Shopify after OAuth: no paid-plan write.

    Does not infer provenance from a shop URL, request header, or store type.
    Fail closed on existing Paddle references, paid plans or multi-merchant
    tenants. A successful OAuth callback is a necessary, not sufficient,
    condition for future billing entitlements.
    """
    db.expire_all()
    org = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .first()
    )
    if (
        org is None
        or not org.active
        or org.billing_onboarding_channel != "shopify_install"
        or org.billing_provider is not None
        or (org.plan or "none").lower() != "none"
        or org.billing_customer_id
        or org.billing_subscription_id
        or org.billing_price_id
        or org.pending_plan
    ):
        return False

    connections = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "shopify",
        )
        .limit(2)
        .all()
    )
    if len(connections) != 1:
        return False
    connection = connections[0]
    if connection.id != connection_id or connection.status != "connected":
        return False
    store = (
        db.query(Store)
        .filter(
            Store.id == connection.store_id,
            Store.organization_id == organization_id,
            Store.active.is_(True),
            Store.deleted.is_(False),
        )
        .first()
    )
    if store is None:
        return False
    org.billing_provider = "shopify"
    db.commit()
    return True
