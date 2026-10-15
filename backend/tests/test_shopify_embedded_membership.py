"""Real SQLite boundary tests for Shopify-to-DIAGLOB per-user binding.

Uses only synthetic shop/admin IDs. No Shopify API calls or customer records.
"""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    CommerceConnection, MembershipStore, Organization, OrganizationMembership,
    ShopifyEmbeddedIdentityBinding, ShopifyEmbeddedLinkTicket, Store, User,
)
from app.services.shopify_embedded_membership import (
    authorize_embedded_identity, issue_link_code, redeem_link_code, revoke_member_links,
)

SHOP = "diaglob-poc.myshopify.com"
IDENTITY = {"shop": SHOP, "subject": "synthetic-shopify-staff-42"}


@pytest.fixture
def sandbox(monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "synthetic-HMAC-key-not-used-with-real-shop")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(id=201, name="Organization 1", slug="shopify-binding-org")
        store = Store(
            id=301, organization_id=201, name="Synthetic store",
            slug="shopify-binding-store", country_code="CO", currency="COP",
            timezone="America/Bogota", default_language="es",
            active=True, deleted=False, shopify_domain=SHOP,
        )
        user = User(id=401, name="Synthetic reviewer", email="reviewer-shopify@example.invalid", active=True)
        member = OrganizationMembership(
            id=501, organization_id=201, user_id=401, role="admin",
            all_stores=True, active=True,
        )
        connection = CommerceConnection(
            id=601, organization_id=201, store_id=301, provider="shopify",
            external_store_url=SHOP, access_token_encrypted="synthetic-ciphertext",
            status="connected", connected_at=datetime(2026, 10, 15, 1, 0, 0),
        )
        db.add_all([org, store, user, member, connection])
        db.commit()
        yield db, member, connection, store
    engine.dispose()


def _linked(db, member, store):
    code = issue_link_code(db, membership_id=member.id, store_id=store.id)["link_code"]
    result = redeem_link_code(db, identity=IDENTITY, code=code)
    assert result == {"linked": True}
    return code


def test_one_time_claim_and_future_shopify_id_token_only(sandbox):
    db, member, connection, store = sandbox
    code = issue_link_code(db, membership_id=member.id, store_id=store.id)["link_code"]
    ticket = db.query(ShopifyEmbeddedLinkTicket).one()
    assert len(ticket.token_digest) == 64
    assert code != ticket.token_digest
    assert code not in str(ticket.__dict__)
    with pytest.raises(HTTPException) as exc:
        authorize_embedded_identity(db, IDENTITY)
    assert exc.value.status_code == 403
    assert redeem_link_code(db, identity=IDENTITY, code=code) == {"linked": True}
    grant = authorize_embedded_identity(db, IDENTITY)
    assert grant == {
        "authorized": True, "shop": SHOP, "store_id": store.id,
        "organization_id": 201, "role": "admin",
    }
    binding = db.query(ShopifyEmbeddedIdentityBinding).one()
    assert IDENTITY["subject"] not in str(binding.__dict__)
    with pytest.raises(HTTPException) as exc:
        redeem_link_code(db, identity=IDENTITY, code=code)
    assert exc.value.status_code == 404


def test_shop_token_cannot_claim_code_from_another_store(sandbox):
    db, member, connection, store = sandbox
    code = issue_link_code(db, membership_id=member.id, store_id=store.id)["link_code"]
    with pytest.raises(HTTPException) as exc:
        redeem_link_code(db, identity={"shop": "other.myshopify.com", "subject": IDENTITY["subject"]}, code=code)
    assert exc.value.status_code == 404
    # A failed attempt did not consume the real owner's code.
    assert redeem_link_code(db, identity=IDENTITY, code=code)["linked"] is True


def test_no_privileges_from_signed_shopify_token_without_binding(sandbox):
    db, member, connection, store = sandbox
    _linked(db, member, store)
    with pytest.raises(HTTPException) as exc:
        authorize_embedded_identity(db, {"shop": SHOP, "subject": "other-staff"})
    assert exc.value.status_code == 403


def test_removed_membership_or_store_scope_revokes_access(sandbox):
    db, member, connection, store = sandbox
    _linked(db, member, store)
    member.active = False
    db.commit()
    with pytest.raises(HTTPException) as exc:
        authorize_embedded_identity(db, IDENTITY)
    assert exc.value.status_code == 403
    member.active = True
    member.all_stores = False
    db.commit()
    with pytest.raises(HTTPException) as exc:
        authorize_embedded_identity(db, IDENTITY)
    assert exc.value.status_code == 403
    db.add(MembershipStore(membership_id=member.id, store_id=store.id))
    db.commit()
    assert authorize_embedded_identity(db, IDENTITY)["authorized"] is True


def test_uninstall_reinstall_change_and_revocation_fail_closed(sandbox):
    db, member, connection, store = sandbox
    _linked(db, member, store)
    connection.status = "revoked"
    connection.access_token_encrypted = None
    db.commit()
    with pytest.raises(HTTPException) as exc:
        authorize_embedded_identity(db, IDENTITY)
    assert exc.value.status_code == 403
    connection.status = "connected"
    connection.access_token_encrypted = "new-synthetic-token"
    connection.connected_at += timedelta(days=1)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        authorize_embedded_identity(db, IDENTITY)
    assert exc.value.status_code == 403
    # Same member can explicitly re-link after a new installation.
    _linked(db, member, store)
    assert authorize_embedded_identity(db, IDENTITY)["authorized"] is True
    assert revoke_member_links(db, membership_id=member.id, store_id=store.id) == 1
    with pytest.raises(HTTPException) as exc:
        authorize_embedded_identity(db, IDENTITY)
    assert exc.value.status_code == 403


def test_expired_code_never_claims(sandbox):
    db, member, connection, store = sandbox
    code = issue_link_code(db, membership_id=member.id, store_id=store.id)["link_code"]
    ticket = db.query(ShopifyEmbeddedLinkTicket).one()
    ticket.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        redeem_link_code(db, identity=IDENTITY, code=code)
    assert exc.value.status_code == 404


def test_bound_shopify_subject_cannot_be_hijacked_by_another_member(sandbox):
    db, member, connection, store = sandbox
    _linked(db, member, store)
    user2 = User(id=402, name="Other", email="other-shopify@example.invalid", active=True)
    member2 = OrganizationMembership(
        id=502, organization_id=member.organization_id,
        user_id=402, role="operator", all_stores=True, active=True,
    )
    db.add_all([user2, member2])
    db.commit()
    code2 = issue_link_code(db, membership_id=member2.id, store_id=store.id)["link_code"]
    with pytest.raises(HTTPException) as exc:
        redeem_link_code(db, identity=IDENTITY, code=code2)
    assert exc.value.status_code == 409
    assert authorize_embedded_identity(db, IDENTITY)["role"] == "admin"


def test_ticket_cannot_issue_for_other_org_membership(sandbox):
    db, member, connection, store = sandbox
    other_org = Organization(id=202, name="Other org", slug="shopify-binding-other")
    other_user = User(id=403, name="Other", email="shopify-outsider@example.invalid")
    other_member = OrganizationMembership(id=503, organization_id=202, user_id=403, active=True)
    db.add_all([other_org, other_user, other_member])
    db.commit()
    with pytest.raises(HTTPException) as exc:
        issue_link_code(db, membership_id=other_member.id, store_id=store.id)
    assert exc.value.status_code == 403
