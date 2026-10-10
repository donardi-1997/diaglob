"""Synthetic-only, no-PII audit and privacy review state machine regressions."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest
from app.services.shopify_privacy_review_workflow import (
    ShopifyPrivacyReviewError,
    record_synthetic_privacy_review,
)


@pytest.fixture
def sandbox(monkeypatch):
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        receipt = ShopifyPrivacyRequest(
            request_id="a" * 64,
            topic="customers/redact",
            shop_id="10",
            shop_domain="shop.myshopify.com",
            organization_id=7,
            store_id=8,
            selector_encrypted="encrypted-synthetic-selector",
            status="pending_policy_review",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(receipt)
        db.commit()
        yield db, receipt
    engine.dispose()


def test_review_status_and_audit_are_committed_together(sandbox):
    db, receipt = sandbox
    result = record_synthetic_privacy_review(
        db,
        request_id=receipt.request_id,
        expected_status="pending_policy_review",
        next_status="scope_reviewed",
        reason_code="scope_verified",
    )
    assert result.changed is True
    assert result.status == "scope_reviewed"
    assert receipt.status == "scope_reviewed"
    events = db.query(ShopifyPrivacyAuditEvent).all()
    assert len(events) == 1
    assert events[0].request_id == receipt.request_id
    assert events[0].from_status == "pending_policy_review"
    assert events[0].to_status == "scope_reviewed"
    assert events[0].reason_code == "scope_verified"
    assert events[0].actor_type == "synthetic_review"
    assert "shop.myshopify.com" not in repr(events[0].__dict__)


def test_duplicate_review_retry_is_idempotent(sandbox):
    db, receipt = sandbox
    kwargs = {
        "request_id": receipt.request_id,
        "expected_status": "pending_policy_review",
        "next_status": "manual_review_required",
        "reason_code": "retention_policy_pending",
    }
    assert record_synthetic_privacy_review(db, **kwargs).changed
    assert not record_synthetic_privacy_review(db, **kwargs).changed
    assert db.query(ShopifyPrivacyAuditEvent).count() == 1


def test_stale_status_cannot_override_review(sandbox):
    db, receipt = sandbox
    record_synthetic_privacy_review(
        db, request_id=receipt.request_id,
        expected_status="pending_policy_review",
        next_status="scope_reviewed", reason_code="scope_verified",
    )
    with pytest.raises(ShopifyPrivacyReviewError, match="STALE_REVIEW_STATUS"):
        record_synthetic_privacy_review(
            db, request_id=receipt.request_id,
            expected_status="pending_policy_review",
            next_status="manual_review_required",
            reason_code="legal_hold_pending",
        )
    assert db.query(ShopifyPrivacyAuditEvent).count() == 1


@pytest.mark.parametrize("next_status", [
    "completed", "exported", "redacted", "executing", "approved", "fulfilled",
])
def test_no_transition_can_mark_real_request_complete(sandbox, next_status):
    db, receipt = sandbox
    with pytest.raises(ShopifyPrivacyReviewError, match="TRANSITION_NOT_ALLOWED"):
        record_synthetic_privacy_review(
            db, request_id=receipt.request_id,
            expected_status="pending_policy_review",
            next_status=next_status,
            reason_code="scope_verified",
        )
    assert receipt.status == "pending_policy_review"
    assert db.query(ShopifyPrivacyAuditEvent).count() == 0


def test_arbitrary_reason_text_is_rejected_without_logging_pii(sandbox):
    db, receipt = sandbox
    with pytest.raises(ShopifyPrivacyReviewError, match="REASON_CODE_NOT_ALLOWED"):
        record_synthetic_privacy_review(
            db, request_id=receipt.request_id,
            expected_status="pending_policy_review",
            next_status="manual_review_required",
            reason_code="user email person@example.com",
        )
    assert db.query(ShopifyPrivacyAuditEvent).count() == 0


def test_scope_review_refuses_unknown_tenant(sandbox):
    db, receipt = sandbox
    receipt.organization_id = None
    db.commit()
    with pytest.raises(ShopifyPrivacyReviewError, match="TENANT_UNRESOLVED"):
        record_synthetic_privacy_review(
            db, request_id=receipt.request_id,
            expected_status="pending_policy_review",
            next_status="scope_reviewed",
            reason_code="scope_verified",
        )
    assert db.query(ShopifyPrivacyAuditEvent).count() == 0


def test_status_change_fails_closed_without_synthetic_flag(sandbox, monkeypatch):
    db, receipt = sandbox
    monkeypatch.delenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS")
    with pytest.raises(ShopifyPrivacyReviewError, match="SYNTHETIC_TEST_ONLY"):
        record_synthetic_privacy_review(
            db, request_id=receipt.request_id,
            expected_status="pending_policy_review",
            next_status="manual_review_required",
            reason_code="tenant_unresolved",
        )
    assert receipt.status == "pending_policy_review"
    assert db.query(ShopifyPrivacyAuditEvent).count() == 0


def test_audit_model_contains_no_payload_or_customer_identifiers(sandbox):
    db, _ = sandbox
    columns = {c["name"] for c in inspect(db.get_bind()).get_columns(
        "shopify_privacy_audit_events"
    )}
    assert columns == {
        "id", "request_id", "event_type", "from_status", "to_status",
        "reason_code", "actor_type", "created_at",
    }
