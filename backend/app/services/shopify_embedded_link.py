"""Fail-closed lookup of an existing, OAuth-authorized Shopify installation.

A Shopify ID token proves the merchant-side shop identity but not membership
in any DIAGLOB organization. Return no private tenant identifiers.
"""
from sqlalchemy.orm import Session

from ..models import CommerceConnection, Organization, Store


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
    return "connected" if len(matches) == 1 else "needs_link"
