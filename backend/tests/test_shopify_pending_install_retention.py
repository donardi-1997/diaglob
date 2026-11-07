"""Retention and signed-uninstall tests for unclaimed OAuth grants."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    ShopifyPendingInstall,
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
)
from app.services.shopify_pending_install_retention import (
    PURGE_AUDIT_EVENT,
    ShopifyPendingInstallRetentionError,
    preview_expired_unclaimed_pending_installs,
    preview_pending_installs_for_privacy_receipt,
    purge_expired_unclaimed_pending_installs,
    purge_pending_installs_for_privacy_receipt,
)
from app.services.shopify_uninstall import process_shopify_uninstall

NOW = datetime(2026, 11, 7, 12, 0, 0)
DOMAIN = "hidden-test.myshopify.com"
OTHER_DOMAIN = "other-test.myshopify.com"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_receipt(
    db: Session,
    *,
    request_id: str | None = None,
    organization_id: int | None = None,
    store_id: int | None = None,
    signed: bool = True,
    domain: str = DOMAIN,
) -> str:
    rid = request_id or secrets.token_hex(32)
    created = NOW - timedelta(days=1)
    db.add(ShopifyPrivacyRequest(
        request_id=rid,
        topic="shop/redact",
        shop_id="102777389346",
        shop_domain=domain,
        organization_id=organization_id,
        store_id=store_id,
        selector_encrypted="synthetic-encrypted-selector",
        status="pending_policy_review",
        created_at=created,
        updated_at=created,
    ))
    if signed:
        db.add(ShopifyPrivacyAuditEvent(
            request_id=rid,
            event_type="received",
            from_status=None,
            to_status="pending_policy_review",
            reason_code="signed",
            actor_type="shopify_hmac_verified",
            created_at=created,
        ))
    db.commit()
    return rid


def add_pending(
    db: Session,
    *,
    now: datetime = NOW,
    expires_in_hours: int = -2,
    created_hours_ago: int = 3,
    claimed: bool = False,
    domain: str = DOMAIN,
) -> None:
    db.add(ShopifyPendingInstall(
        state=secrets.token_urlsafe(24),
        shop_domain=domain,
        expires_at=now + timedelta(hours=expires_in_hours),
        state_used=True,
        token_encrypted="synthetic-encrypted-access",
        refresh_token_encrypted="synthetic-encrypted-refresh",
        claim_expires_at=now + timedelta(hours=expires_in_hours),
        claimed_at=(now - timedelta(hours=1)) if claimed else None,
        created_at=now - timedelta(hours=created_hours_ago),
    ))
    db.commit()


def test_receipt_preview_is_read_only_and_leaks_no_domain(db):
    rid = add_receipt(db)
    add_pending(db)
    report = preview_pending_installs_for_privacy_receipt(
        db, request_id=rid, now=NOW,
    )
    assert report["pending_unclaimed"] == 1
    assert report["pending_purgeable"] == 1
    assert "shop_domain" not in report
    assert db.query(ShopifyPendingInstall).count() == 1


def test_receipt_purge_deletes_only_unclaimed_same_domain_grants(db):
    rid = add_receipt(db)
    add_pending(db)
    add_pending(db)
    add_pending(db, claimed=True)
    add_pending(db, domain=OTHER_DOMAIN)

    result = purge_pending_installs_for_privacy_receipt(
        db, request_id=rid, now=NOW, commit=True,
    )

    assert result["pending_before"] == 2
    assert result["pending_purged"] == 2
    assert result["pending_after"] == 0
    remaining = db.query(ShopifyPendingInstall).all()
    assert len(remaining) == 2
    audit = db.query(ShopifyPrivacyAuditEvent).filter(
        ShopifyPrivacyAuditEvent.event_type == PURGE_AUDIT_EVENT,
    ).all()
    assert len(audit) == 1
    assert audit[0].reason_code == "shop_redact_unclaimed_oauth_grants_purged"


def test_receipt_purge_keeps_unexpired_grant_for_a_possible_reinstall(db):
    rid = add_receipt(db)
    add_pending(db, expires_in_hours=4)

    report = preview_pending_installs_for_privacy_receipt(
        db, request_id=rid, now=NOW,
    )
    assert report["pending_unclaimed"] == 1
    assert report["pending_purgeable"] == 0

    result = purge_pending_installs_for_privacy_receipt(
        db, request_id=rid, now=NOW, commit=True,
    )
    assert result["pending_purged"] == 0
    assert db.query(ShopifyPendingInstall).count() == 1
    assert db.query(ShopifyPrivacyAuditEvent).filter(
        ShopifyPrivacyAuditEvent.event_type == PURGE_AUDIT_EVENT,
    ).count() == 0


def test_receipt_purge_refuses_resolved_tenant(db):
    rid = add_receipt(db, organization_id=5, store_id=8)
    with pytest.raises(
        ShopifyPendingInstallRetentionError,
        match="TENANT_ALREADY_RESOLVED",
    ):
        purge_pending_installs_for_privacy_receipt(db, request_id=rid, now=NOW)


def test_receipt_purge_requires_signed_intake(db):
    rid = add_receipt(db, signed=False)
    with pytest.raises(
        ShopifyPendingInstallRetentionError,
        match="SIGNED_INTAKE_EVIDENCE_MISSING",
    ):
        purge_pending_installs_for_privacy_receipt(db, request_id=rid, now=NOW)


def test_expired_cleanup_respects_grace_and_claims(db):
    add_pending(db, expires_in_hours=-2)
    add_pending(db, expires_in_hours=-30)
    add_pending(db, expires_in_hours=-30, claimed=True)

    preview = preview_expired_unclaimed_pending_installs(db, now=NOW)
    assert preview["pending_purged_candidate"] == 1

    result = purge_expired_unclaimed_pending_installs(db, now=NOW, commit=True)
    assert result["pending_purged"] == 1
    assert db.query(ShopifyPendingInstall).count() == 2


def test_signed_uninstall_purges_unbound_pending_install(db):
    now = datetime.utcnow()
    add_pending(db, now=now, created_hours_ago=3)

    result = process_shopify_uninstall(
        db,
        topic="app/uninstalled",
        header_shop_domain=DOMAIN,
        triggered_at=now.replace(microsecond=0).isoformat() + "Z",
        payload={"id": "102777389346", "myshopify_domain": DOMAIN},
    )

    assert result == {"ok": True, "action": "unknown_shop"}
    assert db.query(ShopifyPendingInstall).count() == 0


def test_signed_uninstall_keeps_grant_created_after_the_event(db):
    now = datetime.utcnow()
    add_pending(db, now=now, created_hours_ago=1)

    result = process_shopify_uninstall(
        db,
        topic="app/uninstalled",
        header_shop_domain=DOMAIN,
        triggered_at=(now - timedelta(hours=2)).replace(
            microsecond=0,
        ).isoformat() + "Z",
        payload={"id": "102777389346", "myshopify_domain": DOMAIN},
    )

    assert result == {"ok": True, "action": "unknown_shop"}
    assert db.query(ShopifyPendingInstall).count() == 1
