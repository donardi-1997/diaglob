"""Synthetic evidence report: 3 Shopify topics, 10 controls, no false closure."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest, ShopifyPrivacyWorkItem
from app.services.shopify_privacy_case_evidence import (
    ShopifyPrivacyCaseEvidenceError,
    expected_areas,
    summarize_shopify_privacy_case_evidence,
)
from app.services.shopify_privacy_no_data import NO_DATA_EVENT, NO_DATA_STATUS
from app.services.shopify_privacy_processing import stage_shopify_privacy_receipt_work_items

REQUEST_ID = "a" * 64
SENSITIVE_DOMAIN = "sensitive-synthetic-shop.myshopify.com"
SENSITIVE_SELECTOR = "SENSITIVE-ENCRYPTED-SELECTOR-NOT-REAL"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def add_receipt(db, topic):
    receipt = ShopifyPrivacyRequest(
        request_id=REQUEST_ID, topic=topic,
        shop_id="SENSITIVE_SHOP_ID", shop_domain=SENSITIVE_DOMAIN,
        organization_id=None, store_id=None,
        selector_encrypted=SENSITIVE_SELECTOR, status="pending_policy_review",
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(receipt)
    db.add(ShopifyPrivacyAuditEvent(
        request_id=REQUEST_ID, event_type="received", actor_type="shopify_hmac_verified",
        reason_code="signed", to_status="pending_policy_review",
        created_at=datetime.utcnow(),
    ))
    db.flush()
    stage_shopify_privacy_receipt_work_items(db, receipt)
    db.commit()
    return receipt


@pytest.mark.parametrize("topic,terminal", [
    ("customers/data_request", "merchant_delivery"),
    ("customers/redact", "reimport_suppression"),
    ("shop/redact", "reimport_suppression"),
])
def test_three_topics_have_exact_ten_gates_no_pii_and_no_false_completion(db, topic, terminal):
    add_receipt(db, topic)
    before = db.query(ShopifyPrivacyAuditEvent).count()
    report = summarize_shopify_privacy_case_evidence(db, request_id=REQUEST_ID)
    assert report["ten_item_queue_integrity"] is True
    assert report["signed_intake_recorded"] is True
    assert report["work_item_count"] == 10
    assert len(report["areas"]) == 10
    assert {x["area"] for x in report["areas"]} == set(expected_areas(topic))
    assert report["areas"][-1]["area"] == terminal
    assert all(x["independently_verified_for_closure"] is False for x in report["areas"])
    assert report["fulfillment_complete"] is False
    assert report["privacy_compliance_certified"] is False
    assert db.query(ShopifyPrivacyAuditEvent).count() == before
    assert db.query(ShopifyPrivacyRequest).one().completed_at is None
    result = str(report)
    for secret in ("SENSITIVE", SENSITIVE_DOMAIN, "SENSITIVE_SHOP_ID", SENSITIVE_SELECTOR):
        assert secret not in result


def test_local_success_claims_never_certify_full_delivery_or_deletion(db):
    receipt = add_receipt(db, "customers/data_request")
    db.add(ShopifyPrivacyAuditEvent(
        request_id=REQUEST_ID, event_type="local_export_downloaded",
        actor_type="authenticated_privacy_owner", reason_code="partial",
        to_status=receipt.status,
    ))
    db.commit()
    report = summarize_shopify_privacy_case_evidence(db, request_id=REQUEST_ID)
    assert report["local_export_partial_only"] is True
    assert "FULL_CONSOLIDATED_EXPORT_AND_MERCHANT_DELIVERY_UNVERIFIED" in report["blockers"]
    assert report["fulfillment_complete"] is False


def test_shop_redact_requires_knowledge_erasure_after_local_sql(db):
    receipt = add_receipt(db, "shop/redact")
    db.add(ShopifyPrivacyAuditEvent(
        request_id=REQUEST_ID, event_type="local_redaction_executed",
        actor_type="independently_permitted_worker", reason_code="synthetic",
        to_status=receipt.status,
    ))
    db.commit()
    result = summarize_shopify_privacy_case_evidence(db, request_id=REQUEST_ID)
    assert "KNOWLEDGE_ERASURE_REQUIRED_AFTER_SQL" in result["blockers"]
    assert result["fulfillment_complete"] is False


def test_interrupted_shop_knowledge_erasure_shows_explicit_case_blocker(db):
    receipt = add_receipt(db, "shop/redact")
    for event in ("local_redaction_executed", "automation_redaction_executed",
                  "knowledge_erasure_started"):
        db.add(ShopifyPrivacyAuditEvent(
            request_id=REQUEST_ID, event_type=event,
            actor_type="independently_permitted_worker", reason_code="b" * 64,
            to_status=receipt.status,
        ))
    db.commit()
    report = summarize_shopify_privacy_case_evidence(db, request_id=REQUEST_ID)
    assert report["shop_knowledge_erasure_started"] is True
    assert report["shop_knowledge_erasure_recorded"] is False
    assert report["automation_redaction_recorded"] is True
    assert "KNOWLEDGE_ERASURE_INTERRUPTED_RECONCILIATION_REQUIRED" in report["blockers"]
    assert "AUTOMATION_REDACTION_EVIDENCE_MISSING" not in report["blockers"]
    assert report["fulfillment_complete"] is False
    assert "SENSITIVE" not in str(report)


def test_redaction_without_automation_scrub_cannot_pass_as_full_coverage(db):
    receipt = add_receipt(db, "customers/redact")
    db.add(ShopifyPrivacyAuditEvent(
        request_id=REQUEST_ID, event_type="local_redaction_executed",
        actor_type="independently_permitted_worker",
        reason_code="b" * 64, to_status=receipt.status,
    ))
    db.commit()
    result = summarize_shopify_privacy_case_evidence(db, request_id=REQUEST_ID)
    assert result["local_redaction_recorded"] is True
    assert result["automation_redaction_recorded"] is False
    assert "AUTOMATION_REDACTION_EVIDENCE_MISSING" in result["blockers"]
    assert result["fulfillment_complete"] is False


def test_no_data_determination_is_not_a_customer_erasure(db):
    receipt = add_receipt(db, "shop/redact")
    receipt.status = NO_DATA_STATUS
    for item in db.query(ShopifyPrivacyWorkItem).all():
        item.status = "not_applicable"
        item.blocker_code = None
    db.add(ShopifyPrivacyAuditEvent(
        request_id=REQUEST_ID, event_type=NO_DATA_EVENT,
        actor_type="internal_privacy_operator", reason_code="NO_TENANT_DATA_ATTRIBUTABLE",
        to_status=NO_DATA_STATUS,
    ))
    db.commit()
    result = summarize_shopify_privacy_case_evidence(db, request_id=REQUEST_ID)
    assert result["no_data_determination_recorded"] is True
    assert result["no_data_is_not_erasure"] is True
    assert result["fulfillment_complete"] is False
    assert db.query(ShopifyPrivacyRequest).one().completed_at is None


def test_tampering_queue_or_completion_never_passes(db):
    receipt = add_receipt(db, "customers/redact")
    db.query(ShopifyPrivacyWorkItem).filter_by(area="external_processors").delete()
    receipt.status = "completed"
    db.commit()
    result = summarize_shopify_privacy_case_evidence(db, request_id=REQUEST_ID)
    assert result["ten_item_queue_integrity"] is False
    assert "TEN_WORK_ITEM_INTEGRITY_FAILURE" in result["blockers"]
    assert "UNAUTHORIZED_COMPLETION_STATE" in result["blockers"]
    assert result["fulfillment_complete"] is False


@pytest.mark.parametrize("invalid", ["", "abc", "Z" * 64, "a" * 63])
def test_rejects_invalid_request_ids(db, invalid):
    with pytest.raises(ShopifyPrivacyCaseEvidenceError, match="INVALID_PRIVACY_REQUEST_ID"):
        summarize_shopify_privacy_case_evidence(db, request_id=invalid)


def test_internal_route_auth_before_query_and_no_pii(db, monkeypatch):
    add_receipt(db, "shop/redact")
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-review-secret")
    original = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        route = f"/api/internal/shopify/privacy/cases/{REQUEST_ID}/evidence-summary"
        assert client.get(route).status_code == 401
        assert client.get(route, headers={"X-Internal-Secret": "invalid"}).status_code == 401
        response = client.get(route, headers={"X-Internal-Secret": "synthetic-review-secret"})
        assert response.status_code == 200
        assert response.json()["work_item_count"] == 10
        assert SENSITIVE_DOMAIN not in response.text
        assert SENSITIVE_SELECTOR not in response.text
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)
