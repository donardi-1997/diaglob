"""Shopify ID-token-only access after explicit, one-time DIAGLOB membership pairing.

Shopify JWT subjects are HMAC-digested (no raw subject at rest). Never infer a
DIAGLOB membership from a shop domain, installation, or Shopify JWT alone.
Every read revalidates shop, connection incarnation, user, membership, and
store assignment. No buyer data, access token or customer selectors in links.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection, MembershipStore, Organization, OrganizationMembership,
    ShopifyEmbeddedIdentityBinding, ShopifyEmbeddedLinkTicket, Store, User,
)

TICKET_LIFETIME = timedelta(minutes=5)


def _subject_digest(shop: str, subject: str) -> str:
    key = os.getenv("SHOPIFY_CLIENT_SECRET", "").strip()
    if not key or not isinstance(subject, str) or not subject or len(subject) > 255:
        raise HTTPException(status_code=401, detail="Invalid Shopify identity")
    return hmac.new(key.encode(), (shop + "\0" + subject).encode(), hashlib.sha256).hexdigest()


def _connected_shop(db: Session, shop: str) -> tuple[CommerceConnection, Store]:
    rows = (
        db.query(CommerceConnection, Store)
        .join(Store, Store.id == CommerceConnection.store_id)
        .join(Organization, Organization.id == Store.organization_id)
        .filter(
            CommerceConnection.provider == "shopify",
            CommerceConnection.external_store_url == shop,
            CommerceConnection.status == "connected",
            CommerceConnection.access_token_encrypted.isnot(None),
            CommerceConnection.organization_id == Store.organization_id,
            Store.active.is_(True), Store.deleted.is_(False),
            Organization.active.is_(True),
        )
        .limit(2).all()
    )
    if len(rows) != 1:
        raise HTTPException(status_code=403, detail="Shopify installation not linked")
    return rows[0]


def _membership_for_store(db: Session, membership_id: int, store: Store) -> OrganizationMembership:
    membership = (
        db.query(OrganizationMembership)
        .join(User, User.id == OrganizationMembership.user_id)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .filter(
            OrganizationMembership.id == membership_id,
            OrganizationMembership.organization_id == store.organization_id,
            OrganizationMembership.active.is_(True),
            User.active.is_(True),
            Organization.active.is_(True),
        )
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="Merchant access revoked")
    if not membership.all_stores:
        allowed = db.query(MembershipStore).filter(
            MembershipStore.membership_id == membership.id,
            MembershipStore.store_id == store.id,
        ).first()
        if allowed is None:
            raise HTTPException(status_code=403, detail="Merchant store access revoked")
    return membership


def issue_link_code(db: Session, *, membership_id: int, store_id: int) -> dict:
    """Called only from Cognito-authenticated, path/store-authorized endpoint."""
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.active.is_(True), Store.deleted.is_(False),
    ).first()
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    _membership_for_store(db, membership_id, store)
    connections = db.query(CommerceConnection).filter(
        CommerceConnection.store_id == store.id,
        CommerceConnection.organization_id == store.organization_id,
        CommerceConnection.provider == "shopify",
        CommerceConnection.status == "connected",
        CommerceConnection.access_token_encrypted.isnot(None),
    ).limit(2).all()
    if len(connections) != 1:
        raise HTTPException(status_code=409, detail="Shopify store not connected")
    connection = connections[0]
    verified, _ = _connected_shop(db, connection.external_store_url)
    if verified.id != connection.id:
        raise HTTPException(status_code=403, detail="Shopify installation ambiguous")

    code = secrets.token_urlsafe(32)
    db.add(ShopifyEmbeddedLinkTicket(
        token_digest=hashlib.sha256(code.encode()).hexdigest(),
        shop_domain=connection.external_store_url,
        organization_id=store.organization_id,
        store_id=store.id,
        membership_id=membership_id,
        connection_id=connection.id,
        connected_at=connection.connected_at,
        expires_at=datetime.utcnow() + TICKET_LIFETIME,
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"link_code": code, "expires_in_seconds": 300}


def redeem_link_code(db: Session, *, identity: dict, code: str) -> dict:
    """Bind a verified Shopify Admin user only after a DIAGLOB member issues code."""
    shop, subject = identity["shop"], identity["subject"]
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", code):
        raise HTTPException(status_code=404, detail="Invalid or expired link code")
    ticket_hash = hashlib.sha256(code.encode()).hexdigest()
    now = datetime.utcnow()
    ticket = db.query(ShopifyEmbeddedLinkTicket).filter(
        ShopifyEmbeddedLinkTicket.token_digest == ticket_hash,
        ShopifyEmbeddedLinkTicket.shop_domain == shop,
        ShopifyEmbeddedLinkTicket.expires_at > now,
        ShopifyEmbeddedLinkTicket.consumed_at.is_(None),
    ).first()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Invalid or expired link code")
    connection, store = _connected_shop(db, shop)
    if (
        ticket.connection_id != connection.id or ticket.store_id != store.id
        or ticket.organization_id != store.organization_id
        or ticket.connected_at != connection.connected_at
    ):
        raise HTTPException(status_code=403, detail="Installation changed; relink required")
    _membership_for_store(db, ticket.membership_id, store)
    digest = _subject_digest(shop, subject)
    previous = db.query(ShopifyEmbeddedIdentityBinding).filter(
        ShopifyEmbeddedIdentityBinding.shop_domain == shop,
        ShopifyEmbeddedIdentityBinding.subject_digest == digest,
    ).first()
    if previous is not None and previous.revoked_at is None and previous.membership_id != ticket.membership_id:
        raise HTTPException(status_code=409, detail="Shopify user already linked to another member")
    # Atomic replay protection even when multiple app workers handle same code.
    claimed = db.query(ShopifyEmbeddedLinkTicket).filter(
        ShopifyEmbeddedLinkTicket.id == ticket.id,
        ShopifyEmbeddedLinkTicket.consumed_at.is_(None),
        ShopifyEmbeddedLinkTicket.expires_at > datetime.utcnow(),
    ).update({ShopifyEmbeddedLinkTicket.consumed_at: datetime.utcnow()}, synchronize_session=False)
    if claimed != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Link code already used")
    if previous is None:
        db.add(ShopifyEmbeddedIdentityBinding(
            shop_domain=shop, subject_digest=digest,
            organization_id=store.organization_id, store_id=store.id,
            membership_id=ticket.membership_id, connection_id=connection.id,
            connected_at=connection.connected_at, created_at=datetime.utcnow(),
        ))
    else:
        previous.organization_id = store.organization_id
        previous.store_id = store.id
        previous.membership_id = ticket.membership_id
        previous.connection_id = connection.id
        previous.connected_at = connection.connected_at
        previous.revoked_at = None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Shopify user link conflict") from exc
    return {"linked": True}


def authorize_embedded_identity(db: Session, identity: dict) -> dict:
    shop, subject = identity["shop"], identity["subject"]
    digest = _subject_digest(shop, subject)
    connection, store = _connected_shop(db, shop)
    rows = db.query(ShopifyEmbeddedIdentityBinding).filter(
        ShopifyEmbeddedIdentityBinding.shop_domain == shop,
        ShopifyEmbeddedIdentityBinding.subject_digest == digest,
        ShopifyEmbeddedIdentityBinding.revoked_at.is_(None),
    ).limit(2).all()
    if len(rows) != 1:
        raise HTTPException(status_code=403, detail="Shopify account link required")
    link = rows[0]
    if (
        link.connection_id != connection.id or link.connected_at != connection.connected_at
        or link.store_id != store.id or link.organization_id != store.organization_id
    ):
        raise HTTPException(status_code=403, detail="Shopify installation changed")
    member = _membership_for_store(db, link.membership_id, store)
    return {
        "authorized": True,
        "shop": shop,
        "store_id": store.id,
        "organization_id": member.organization_id,
        "role": member.role,
    }


def revoke_member_links(db: Session, *, membership_id: int, store_id: int) -> int:
    count = db.query(ShopifyEmbeddedIdentityBinding).filter(
        ShopifyEmbeddedIdentityBinding.membership_id == membership_id,
        ShopifyEmbeddedIdentityBinding.store_id == store_id,
        ShopifyEmbeddedIdentityBinding.revoked_at.is_(None),
    ).update({ShopifyEmbeddedIdentityBinding.revoked_at: datetime.utcnow()},
             synchronize_session=False)
    # Revocation also invalidates outstanding pairing codes for this member.
    db.query(ShopifyEmbeddedLinkTicket).filter(
        ShopifyEmbeddedLinkTicket.membership_id == membership_id,
        ShopifyEmbeddedLinkTicket.store_id == store_id,
        ShopifyEmbeddedLinkTicket.consumed_at.is_(None),
    ).update({ShopifyEmbeddedLinkTicket.consumed_at: datetime.utcnow()},
             synchronize_session=False)
    db.commit()
    return count
