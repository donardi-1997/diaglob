"""Fail-closed lookup of Shopify installation state for an embedded session.

A Shopify ID token proves the merchant-side shop identity but not membership
in any DIAGLOB organization. Return no private tenant identifiers.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import CommerceConnection, Organization, ShopifyPendingInstall, Store


def installed_shop_status(db: Session, shop: str) -> str:
    matches = (
        db.query(CommerceConnection)
        .join(Store, CommerceConnection.store_id == Store.id)
        .join(Organization, CommerceConnection.organization_id == Organization.id)
        .filter(
            CommerceConnection.provider == "shopify",
            CommerceConnection.external_store_url == shop,
            CommerceConnection.status == "connected",
            CommerceConnection.access_token_encrypted.isnot(None),
            CommerceConnection.organization_id == Store.organization_id,
            Store.active.is_(True),
            Store.deleted.is_(False),
            Organization.active.is_(True),
        )
        .limit(2)
        .all()
    )
    # Never permit a conflicting/ambiguous binding to authenticate any tenant.
    if len(matches) == 1:
        return "connected"
    if matches:
        return "needs_link"

    # This is only an onboarding hint. The browser still has to present the
    # HttpOnly claim cookie on the first-party DIAGLOB origin, and a DIAGLOB
    # member must explicitly bind the grant to an authorized store.
    pending = db.query(ShopifyPendingInstall.id).filter(
        ShopifyPendingInstall.shop_domain == shop,
        ShopifyPendingInstall.claimed_at.is_(None),
        ShopifyPendingInstall.claim_hash.isnot(None),
        ShopifyPendingInstall.claim_expires_at > datetime.utcnow(),
        ShopifyPendingInstall.token_encrypted.isnot(None),
    ).first()
    return "oauth_pending" if pending is not None else "needs_link"
