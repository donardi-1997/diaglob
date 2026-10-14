"""Explicit dual-identity authorization for the Shopify embedded surface.

Never exchange Shopify ID tokens for Diaglob sessions. A valid Cognito user
MUST already have an active organization membership and store scope.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..auth import verify_cognito_access_token
from ..models import CommerceConnection, MembershipStore, Organization, OrganizationMembership, Store, User


def authorize_embedded_store(
    db: Session,
    shop: str,
    cognito_access_token: str,
) -> dict:
    payload = verify_cognito_access_token(cognito_access_token)
    sub = payload["sub"]
    matches = (
        db.query(CommerceConnection, Store, OrganizationMembership)
        .join(Store, Store.id == CommerceConnection.store_id)
        .join(Organization, Organization.id == CommerceConnection.organization_id)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .join(User, User.id == OrganizationMembership.user_id)
        .filter(
            User.external_auth_id == sub,
            User.active.is_(True),
            OrganizationMembership.active.is_(True),
            Organization.active.is_(True),
            Store.organization_id == Organization.id,
            Store.active.is_(True),
            Store.deleted.is_(False),
            CommerceConnection.provider == "shopify",
            CommerceConnection.external_store_url == shop,
            CommerceConnection.status == "connected",
            CommerceConnection.access_token_encrypted.isnot(None),
        )
        .limit(2)
        .all()
    )
    if len(matches) != 1:
        raise HTTPException(status_code=403, detail="Shopify store access not authorized")
    connection, store, membership = matches[0]
    if not membership.all_stores:
        scoped = (
            db.query(MembershipStore)
            .filter(
                MembershipStore.membership_id == membership.id,
                MembershipStore.store_id == store.id,
            )
            .first()
        )
        if scoped is None:
            raise HTTPException(status_code=403, detail="Shopify store access not authorized")
    return {
        "authorized": True,
        "shop": shop,
        "store_id": store.id,
        "organization_id": membership.organization_id,
        "role": membership.role,
    }
