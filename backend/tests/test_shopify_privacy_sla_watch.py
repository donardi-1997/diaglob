"""Synthetic-only SLA watch tests: no privacy payload disclosure or mutation."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest, ShopifyPrivacyWorkItem,
)
from app.shopify_privacy_sla_watch import audit_shopify_privacy_sla

NOW = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
ENV = {
    "SHOPIFY_CLIENT_SECRET": "synthetic-hmac-key",
    "SHOPIFY_TOKEN_ENCRYPTION_KEY": "synthetic-fernet-key",
}


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def receipt(db, n, *, days=1, org=5, store=8,
            status="pending_policy_review", topic="customers/data_request",
            signed=True, prepared=True, work_items=10):
    rid = f"{n:064x}"
    timestamp = (NOW - timedelta(days=days)).replace(tzinfo=None)
    db.add(ShopifyPrivacyRequest(
        request_id=rid, topic=topic,
        shop_id="PRIVATE_SHOP_ID", shop_domain="private.myshopify.com",
        organization_id=org, store_id=store,
        selector_encrypted="PRIVATE_PERSON_PII",
        status=status, created_at=timestamp, updated_at=timestamp,
    ))
    if signed:
        db.add(ShopifyPrivacyAuditEvent(
            request_id=rid, event_type="received",
            from_status=None, to_status=status, reason_code="signed",
            actor_type="shopify_hmac_verified", created_at=timestamp,
        ))
    if prepared:
        db.add(ShopifyPrivacyAuditEvent(
            request_id=rid, event_type="processing_prepared",
            from_status=None, to_status=status, reason_code="staged",
            actor_type="internal_privacy_processor", created_at=timestamp,
        ))
    for idx in range(work_items):
        db.add(ShopifyPrivacyWorkItem(
            request_id=rid, area=f"privacy_area_{idx}",
            action="review", status="blocked",
            created_at=timestamp, updated_at=timestamp,
        ))
    db.commit()


def test_watch_empty_or_valid_recent_backlog_is_not_privacy_release_pass(db):
    report = audit_shopify_privacy_sla(db, now=NOW, environment=ENV)
    assert report["state"] == "normal"
    assert report["attention_required"] is False
    assert report["privacy_release_ready"] is False
    assert not report["fulfillment_complete"]
    receipt(db, 1)
    report = audit_shopify_privacy_sla(db, now=NOW, environment=ENV)
    assert report["receipt_total"] == 1
    assert report["state"] == "normal"
    assert report["counts"]["signed_receipt_evidence_missing"] == 0
    assert report["counts"]["incomplete_work_item_queue"] == 0
    assert report["fulfillment_authorized"] is False


def test_watch_warns_at_day23_and_critical_at_day30_inclusive(db):
    receipt(db, 1, days=22)
    receipt(db, 2, days=23)
    report = audit_shopify_privacy_sla(db, now=NOW, environment=ENV)
    assert report["state"] == "warning"
    assert report["counts"]["approaching_30_day_target"] == 1
    assert report["counts"]["at_or_past_30_day_target"] == 0
    receipt(db, 3, days=30, status="completed")
    report = audit_shopify_privacy_sla(db, now=NOW, environment=ENV)
    assert report["state"] == "critical"
    assert report["counts"]["approaching_30_day_target"] == 2
    # An unproven status='completed' NEVER suppresses the escalation.
    assert report["counts"]["at_or_past_30_day_target"] == 1


def test_watch_detects_missing_evidence_and_store_with_sanitized_counts(db):
    receipt(db, 1, days=1, org=None, signed=False, prepared=False, work_items=0)
    receipt(db, 2, days=2, topic="SENSITIVE_SUBJECT_EMAIL@example.com")
    out = audit_shopify_privacy_sla(db, now=NOW, environment=ENV)
    assert out["state"] == "critical"
    assert out["counts"]["tenant_store_unresolved"] == 1
    assert out["counts"]["signed_receipt_evidence_missing"] == 1
    assert out["counts"]["processing_queue_evidence_missing"] == 1
    assert out["counts"]["incomplete_work_item_queue"] == 1
    assert out["counts"]["unsupported_topic"] == 1
    dumped = json.dumps(out)
    for secret in (
        "PRIVATE_PERSON_PII", "PRIVATE_SHOP_ID",
        "private.myshopify.com", "SENSITIVE_SUBJECT_EMAIL",
        f"{1:064x}", f"{2:064x}",
    ):
        assert secret not in dumped


def test_watch_sees_future_receipts_missing_secrets_and_unverified_tasks(db):
    receipt(db, 1, days=-1)
    db.query(ShopifyPrivacyWorkItem).filter(
        ShopifyPrivacyWorkItem.request_id == f"{1:064x}"
    ).first().status = "completed"
    db.commit()
    report = audit_shopify_privacy_sla(db, now=NOW, environment={})
    assert report["state"] == "critical"
    assert report["counts"]["future_or_missing_received_timestamp"] == 1
    assert report["counts"]["unverified_work_item_completion"] == 1
    assert report["hmac_secret_present"] is False
    assert report["selector_encryption_key_present"] is False


def test_watch_has_no_database_side_effects(db):
    receipt(db, 1, days=31, status="completed")
    before_request = db.query(ShopifyPrivacyRequest).one().status
    before_items = [
        (item.status, item.blocker_code)
        for item in db.query(ShopifyPrivacyWorkItem).all()
    ]
    report = audit_shopify_privacy_sla(db, now=NOW, environment=ENV)
    assert report["attention_required"]
    db.expire_all()
    assert db.query(ShopifyPrivacyRequest).one().status == before_request
    assert [
        (item.status, item.blocker_code)
        for item in db.query(ShopifyPrivacyWorkItem).all()
    ] == before_items


def test_watch_rejects_naive_now(db):
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED"):
        audit_shopify_privacy_sla(
            db, now=datetime(2026, 10, 23, 18, 0), environment=ENV,
        )
