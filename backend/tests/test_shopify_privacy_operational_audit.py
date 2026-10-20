"""Synthetic-only checks for the read-only Shopify privacy production audit."""
import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    ShopifyPrivacySuppression,
    ShopifyPrivacyWorkItem,
)
from app.shopify_privacy_operational_audit import (
    summarize_shopify_privacy_operations,
)


def test_empty_backlog_does_not_claim_live_shopify_subscription():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            report = summarize_shopify_privacy_operations(db, environment={
                "SHOPIFY_CLIENT_SECRET": "synthetic",
                "SHOPIFY_TOKEN_ENCRYPTION_KEY": "synthetic",
            })
        assert report["receipt_total"] == 0
        assert set(report["topic_receipts"]) == {
            "customers/data_request", "customers/redact", "shop/redact",
        }
        assert all(value == 0 for value in report["topic_receipts"].values())
        assert report["review_required"] is False
        assert report["released_shopify_subscription_verified"] is False
        assert report["valid_live_shopify_delivery_verified"] is False
        assert report["data_export_or_erasure_fulfilled"] is False
        # An empty operational inbox is NOT a Shopify/privacy release PASS.
        assert report["privacy_fulfillment_release_ready"] is False
        assert "LIVE_CUSTOMER_AND_SHOP_REDACTION_NOT_ENABLED" in (
            report["privacy_fulfillment_release_blockers"]
        )
        assert "LIVE_CUSTOMER_EXPORT_NOT_ENABLED" in (
            report["privacy_fulfillment_release_blockers"]
        )
    finally:
        engine.dispose()


def test_aggregate_reports_incomplete_queue_without_exposing_subject_data():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.utcnow()
    try:
        with Session(engine) as db:
            for index, topic in enumerate((
                "customers/data_request", "customers/redact", "shop/redact",
            ), 1):
                digest = str(index) * 64
                db.add(ShopifyPrivacyRequest(
                    request_id=digest,
                    topic=topic,
                    shop_id="SENSITIVE_SHOP_ID",
                    shop_domain="SENSITIVE_SHOP.myshopify.com",
                    selector_encrypted="SENSITIVE_ENCRYPTED_PAYLOAD",
                    status="pending_policy_review",
                    created_at=now, updated_at=now, attempts=0,
                ))
                if index == 1:
                    db.add(ShopifyPrivacyAuditEvent(
                        request_id=digest, event_type="received",
                        from_status=None, to_status="pending_policy_review",
                        reason_code="tenant_unresolved",
                        actor_type="shopify_hmac_verified", created_at=now,
                    ))
                    db.add(ShopifyPrivacyAuditEvent(
                        request_id=digest, event_type="processing_prepared",
                        from_status=None, to_status="pending_policy_review",
                        reason_code="source_tasks_initialized",
                        actor_type="internal_privacy_processor", created_at=now,
                    ))
                    for n in range(10):
                        db.add(ShopifyPrivacyWorkItem(
                            request_id=digest, area=f"review_area_{n}",
                            action="review", status="blocked",
                            created_at=now, updated_at=now,
                        ))
            db.commit()
            report = summarize_shopify_privacy_operations(db, environment={})
        assert report["receipt_total"] == 3
        assert all(value == 1 for value in report["topic_receipts"].values())
        assert report["distinct_signed_received_audits"] == 1
        assert report["distinct_processing_prepared_audits"] == 1
        assert report["receipts_missing_complete_ten_item_queue"] == 2
        assert report["review_required"] is True
        text = json.dumps(report)
        for secret in (
            "SENSITIVE_SHOP_ID", "SENSITIVE_ENCRYPTED_PAYLOAD",
            "SENSITIVE_SHOP.myshopify.com", "111111111111",
        ):
            assert secret not in text
    finally:
        engine.dispose()


def test_read_only_audit_does_not_activate_staged_suppressions():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.utcnow()
    try:
        with Session(engine) as db:
            db.add(ShopifyPrivacySuppression(
                organization_id=1, store_id=1, request_id="a" * 64,
                kind="shop", selector_digest="b" * 64,
                key_fingerprint="c" * 64, domain_fingerprint="d" * 64,
                status="staged", created_at=now,
            ))
            db.commit()
            report = summarize_shopify_privacy_operations(db, environment={
                "SHOPIFY_CLIENT_SECRET": "synthetic",
                "SHOPIFY_TOKEN_ENCRYPTION_KEY": "synthetic",
            })
            assert report["staged_suppressions"] == 1
            assert report["active_suppressions"] == 0
            db.expire_all()
            assert db.query(ShopifyPrivacySuppression).one().status == "staged"
    finally:
        engine.dispose()


def test_unverified_completed_task_forces_review_even_with_ten_rows():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.utcnow()
    try:
        with Session(engine) as db:
            request_id = "b" * 64
            db.add(ShopifyPrivacyRequest(
                request_id=request_id,
                topic="shop/redact",
                shop_id="PRIVATE_SHOP_ID",
                shop_domain="private.myshopify.com",
                selector_encrypted="ENCRYPTED_PRIVATE",
                status="pending_policy_review",
                created_at=now,
                updated_at=now,
                attempts=0,
            ))
            db.add(ShopifyPrivacyAuditEvent(
                request_id=request_id, event_type="received",
                from_status=None, to_status="pending_policy_review",
                reason_code="tenant_unresolved", actor_type="shopify_hmac_verified",
                created_at=now,
            ))
            db.add(ShopifyPrivacyAuditEvent(
                request_id=request_id, event_type="processing_prepared",
                from_status=None, to_status="pending_policy_review",
                reason_code="signed_receipt_tasks_staged_without_data_access",
                actor_type="internal_privacy_processor",
                created_at=now,
            ))
            for index in range(10):
                db.add(ShopifyPrivacyWorkItem(
                    request_id=request_id, area=f"area_{index}",
                    action="review", status="completed" if index == 0 else "blocked",
                    created_at=now, updated_at=now,
                ))
            db.commit()
            report = summarize_shopify_privacy_operations(db, environment={
                "SHOPIFY_CLIENT_SECRET": "synthetic",
                "SHOPIFY_TOKEN_ENCRYPTION_KEY": "synthetic",
            })
        assert report["receipt_total"] == 1
        assert report["distinct_signed_received_audits"] == 1
        assert report["distinct_processing_prepared_audits"] == 1
        assert report["receipts_missing_complete_ten_item_queue"] == 0
        assert report["work_items_with_unverified_completion_state"] == 1
        assert report["review_required"] is True
        assert report["privacy_fulfillment_release_ready"] is False
        assert "PRIVATE_SHOP_ID" not in json.dumps(report)
        assert "ENCRYPTED_PRIVATE" not in json.dumps(report)
    finally:
        engine.dispose()
