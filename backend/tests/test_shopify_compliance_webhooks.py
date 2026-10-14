import base64
import hashlib
import hmac
import json
import os
from types import SimpleNamespace

from cryptography.fernet import Fernet
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.shopify import router
from app.db import Base, get_db
from app.main import app
from app.models import ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest, ShopifyPrivacyWorkItem
from app.shopify_security import decrypt_shopify_secret
from app.services.shopify_compliance_webhooks import (
    process_shopify_compliance_webhook,
)
from app.services.shopify_webhook_service import verify_shopify_webhook_hmac
from app.shopify_privacy_operational_audit import summarize_shopify_privacy_operations


TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TEST_SESSION = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


@pytest.fixture()
def client():
    Base.metadata.create_all(bind=TEST_ENGINE)
    db = TEST_SESSION()

    def _override_get_db():
        yield db

    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _override_get_db
    app.include_router(router)
    try:
        with patch.dict(os.environ, {
            "SHOPIFY_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }):
            with TestClient(app) as test_client:
                yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original_overrides)
        db.close()
        Base.metadata.drop_all(bind=TEST_ENGINE)

def _signed_headers(body: bytes, topic: str) -> tuple[str, dict[str, str]]:
    secret = "test-shopify-secret"
    signature = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    return secret, {
        "X-Shopify-Hmac-Sha256": signature,
        "X-Shopify-Topic": topic,
        "Content-Type": "application/json",
    }


class TestShopifyComplianceWebhooks:
    def test_invalid_hmac_is_rejected(self, client):
        response = client.post(
            "/api/webhooks/shopify/compliance",
            content=b'{"shop_id":1,"shop_domain":"test.myshopify.com"}',
            headers={
                "X-Shopify-Hmac-Sha256": "invalid",
                "X-Shopify-Topic": "shop/redact",
            },
        )
        assert response.status_code == 401

    def test_missing_hmac_is_rejected(self, client):
        response = client.post(
            "/api/webhooks/shopify/compliance",
            content=b'{"shop_id":123,"shop_domain":"test.myshopify.com"}',
            headers={
                "X-Shopify-Topic": "customers/redact",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401

    def test_customer_data_request_is_acknowledged_without_pii_in_receipt(self, client):
        body = json.dumps(
            {
                "shop_id": 123,
                "shop_domain": "test-store.myshopify.com",
                "customer": {"id": 456, "email": "customer@example.com"},
            }
        ).encode()
        secret, headers = _signed_headers(body, "customers/data_request")

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            first = client.post("/api/webhooks/shopify/compliance", content=body, headers=headers)
            second = client.post("/api/webhooks/shopify/compliance", content=body, headers=headers)

        assert first.status_code == second.status_code == 200
        assert first.json()["request_id"] == second.json()["request_id"]
        assert "customer@example.com" not in first.text
        assert first.json()["redaction_status"] == "data_request_recorded"
        assert first.json()["processing_tasks_prepared"] is True

    def test_redaction_request_is_recorded_not_deleted_pending_policy(self, client):
        body = json.dumps(
            {
                "shop_id": 123,
                "shop_domain": "test-store.myshopify.com",
                "customer": {"id": 456},
                "orders_to_redact": [789],
            }
        ).encode()
        secret, headers = _signed_headers(body, "customers/redact")

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            response = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers
            )

        assert response.status_code == 200
        assert response.json()["redaction_status"] == "pending_policy_review"

    def test_missing_shop_id_is_rejected(self, client):
        body = json.dumps({"shop_domain": "test-store.myshopify.com"}).encode()
        secret, headers = _signed_headers(body, "shop/redact")

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False):
            response = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers
            )

        assert response.status_code == 400

    def test_receipt_is_durable_encrypted_and_deduplicated(self, client):
        body = json.dumps({
            "shop_id": 123,
            "shop_domain": "test-store.myshopify.com",
            "customer": {"id": 456, "email": "private@example.com"},
        }).encode()
        secret, headers = _signed_headers(body, "customers/data_request")
        headers["X-Shopify-Webhook-Id"] = "event-abc"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            first = client.post("/api/webhooks/shopify/compliance", content=body, headers=headers)
            again = client.post("/api/webhooks/shopify/compliance", content=body, headers=headers)

        assert first.status_code == again.status_code == 200
        assert first.json()["action"] == "recorded"
        assert again.json()["action"] == "duplicate"
        assert first.json()["request_id"] == again.json()["request_id"]
        with TEST_SESSION() as session:
            records = session.query(ShopifyPrivacyRequest).all()
            assert len(records) == 1
            record = records[0]
            assert record.organization_id is None
            assert record.store_id is None
            assert record.status == "pending_policy_review"
            assert record.attempts == 0
            assert "private@example.com" not in record.selector_encrypted
            decoded = json.loads(decrypt_shopify_secret(record.selector_encrypted))
            assert decoded["customer"]["email"] == "private@example.com"
            audits = session.query(ShopifyPrivacyAuditEvent).all()
            assert len(audits) == 2
            received = next(row for row in audits if row.event_type == "received")
            prepared = next(row for row in audits if row.event_type == "processing_prepared")
            assert received.request_id == record.request_id
            assert received.to_status == "pending_policy_review"
            assert received.actor_type == "shopify_hmac_verified"
            assert prepared.actor_type == "internal_privacy_processor"
            assert "private@example.com" not in str(received.__dict__)
            work_items = session.query(ShopifyPrivacyWorkItem).all()
            assert len(work_items) == 10
            assert all(item.status != "completed" for item in work_items)
            assert {item.area for item in work_items} >= {"signed_receipt", "merchant_delivery"}

    def test_distinct_shopify_webhook_ids_do_not_collapse_requests(self, client):
        body = json.dumps({
            "shop_id": 123,
            "shop_domain": "test-store.myshopify.com",
            "customer": {"id": 456},
        }).encode()
        secret, headers = _signed_headers(body, "customers/data_request")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            headers["X-Shopify-Webhook-Id"] = "first-delivery"
            first = client.post("/api/webhooks/shopify/compliance", content=body, headers=headers)
            headers["X-Shopify-Webhook-Id"] = "second-delivery"
            second = client.post("/api/webhooks/shopify/compliance", content=body, headers=headers)
        assert first.status_code == second.status_code == 200
        assert first.json()["request_id"] != second.json()["request_id"]
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 2

    def test_reject_shop_domain_header_mismatch_without_creating_receipt(self, client):
        body = json.dumps({
            "shop_id": 123,
            "shop_domain": "shop-one.myshopify.com",
        }).encode()
        secret, headers = _signed_headers(body, "shop/redact")
        headers["X-Shopify-Shop-Domain"] = "shop-two.myshopify.com"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}):
            response = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers
            )
        assert response.status_code == 400
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 0

    def test_tenant_binding_uses_only_resolved_shopify_connection(self, client):
        body = json.dumps({
            "shop_id": 321,
            "shop_domain": "known.myshopify.com",
            "customer": {"id": 999},
        }).encode()
        secret, headers = _signed_headers(body, "customers/redact")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=SimpleNamespace(organization_id=19, store_id=47),
        ):
            response = client.post("/api/webhooks/shopify/compliance", content=body, headers=headers)
        assert response.status_code == 200
        with TEST_SESSION() as session:
            item = session.query(ShopifyPrivacyRequest).one()
            assert (item.organization_id, item.store_id) == (19, 47)
            assert item.topic == "customers/redact"

    def test_reject_invalid_signature_without_persisting_anything(self, client):
        body = b'{"shop_id":123,"shop_domain":"known.myshopify.com"}'
        response = client.post(
            "/api/webhooks/shopify/compliance",
            content=body,
            headers={"X-Shopify-Topic": "shop/redact", "X-Shopify-Hmac-Sha256": "fake"},
        )
        assert response.status_code == 401
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 0


    def test_oversized_signed_compliance_payload_is_rejected_without_receipt(self, client):
        # A signed payload must not bypass the bounded-body safety check.
        from app.api.shopify import MAX_COMPLIANCE_BODY_BYTES

        body = json.dumps({
            "shop_id": 123,
            "shop_domain": "known.myshopify.com",
            "unexpected": "x" * MAX_COMPLIANCE_BODY_BYTES,
        }).encode()
        assert len(body) > MAX_COMPLIANCE_BODY_BYTES
        secret, headers = _signed_headers(body, "customers/data_request")
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}):
            response = client.post(
                "/api/webhooks/shopify/compliance",
                content=body,
                headers=headers,
            )
        assert response.status_code == 413
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 0

    def test_oversized_unsigned_compliance_payload_is_rejected_without_receipt(self, client):
        from app.api.shopify import MAX_COMPLIANCE_BODY_BYTES

        response = client.post(
            "/api/webhooks/shopify/compliance",
            content=b"x" * (MAX_COMPLIANCE_BODY_BYTES + 1),
            headers={"X-Shopify-Topic": "shop/redact"},
        )
        assert response.status_code == 413
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 0


    @pytest.mark.parametrize("topic,extra,final_area", [
        ("customers/data_request", {
            "customer": {"id": 456, "email": "private@example.com"},
            "orders_requested": [1000],
            "data_request": {"id": 2},
        }, "merchant_delivery"),
        ("customers/redact", {
            "customer": {"id": 456, "phone": "+573001234567"},
            "orders_to_redact": [1000],
        }, "reimport_suppression"),
        ("shop/redact", {}, "reimport_suppression"),
    ])
    def test_all_three_topics_prepare_ten_safe_tasks_and_one_audit_on_retry(
        self, client, topic, extra, final_area,
    ):
        body = json.dumps({
            "shop_id": 1234,
            "shop_domain": "test-store.myshopify.com",
            **extra,
        }).encode()
        secret, headers = _signed_headers(body, topic)
        headers["X-Shopify-Webhook-Id"] = "realistic-shopify-webhook-id"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            received = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
            retry = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
        assert received.status_code == retry.status_code == 200
        assert received.json()["action"] == "recorded"
        assert retry.json()["action"] == "duplicate"
        assert received.json()["processing_tasks_prepared"] is True
        assert retry.json()["processing_tasks_prepared"] is True
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 1
            tasks = session.query(ShopifyPrivacyWorkItem).all()
            assert len(tasks) == 10
            assert final_area in {task.area for task in tasks}
            assert all(task.status != "completed" for task in tasks)
            audits = session.query(ShopifyPrivacyAuditEvent).all()
            assert sorted(x.event_type for x in audits) == [
                "processing_prepared", "received",
            ]

    def test_atomic_queue_failure_returns_500_without_partial_receipt(
        self, client,
    ):
        body = json.dumps({
            "shop_id": 1234,
            "shop_domain": "test-store.myshopify.com",
            "customer": {"id": 456, "email": "private@example.com"},
        }).encode()
        secret, headers = _signed_headers(body, "customers/data_request")
        headers["X-Shopify-Webhook-Id"] = "retry-after-queue-error"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ), patch(
            "app.services.shopify_compliance_webhooks.stage_shopify_privacy_receipt_work_items",
            side_effect=RuntimeError("synthetic transient transaction failure"),
        ):
            first = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
        assert first.status_code == 500
        assert "private@example.com" not in first.text
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 0
            assert session.query(ShopifyPrivacyWorkItem).count() == 0
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            recovered = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
        assert recovered.status_code == 200
        assert recovered.json()["action"] == "recorded"
        assert recovered.json()["processing_tasks_prepared"] is True
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 1
            assert session.query(ShopifyPrivacyWorkItem).count() == 10
            assert session.query(ShopifyPrivacyAuditEvent).count() == 2

    def test_retry_repairs_legacy_signed_receipt_without_review_tasks(
        self, client,
    ):
        body = json.dumps({
            "shop_id": 1234,
            "shop_domain": "test-store.myshopify.com",
            "customer": {"id": 456, "phone": "555-0123"},
        }).encode()
        secret, headers = _signed_headers(body, "customers/redact")
        headers["X-Shopify-Webhook-Id"] = "legacy-queue-repair"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            first = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
            assert first.status_code == 200
            # Simulate an older signed receipt that has no processing rows.
            with TEST_SESSION() as session:
                session.query(ShopifyPrivacyWorkItem).delete()
                session.commit()
            repaired = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
        assert repaired.status_code == 200
        assert repaired.json()["action"] == "duplicate"
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 1
            assert session.query(ShopifyPrivacyWorkItem).count() == 10

    def test_bad_hmac_does_not_create_case_or_work_queue(self, client):
        body = json.dumps({
            "shop_id": 900,
            "shop_domain": "test-store.myshopify.com",
        }).encode()
        response = client.post(
            "/api/webhooks/shopify/compliance",
            content=body,
            headers={
                "X-Shopify-Topic": "shop/redact",
                "X-Shopify-Hmac-Sha256": "not-valid",
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 401
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 0
            assert session.query(ShopifyPrivacyWorkItem).count() == 0


    def test_complete_synthetic_signed_three_topic_delivery_and_idempotent_retries(
        self, client,
    ):
        """End-to-end HTTP->HMAC->encrypted receipt->10 review tasks on isolated SQLite.

        THIS IS A SYNTHETIC TEST, not evidence of delivery from Shopify to a
        released production app. No GDPR real-data fulfillment is performed.
        """
        cases = [
            ("customers/data_request", {
                "customer": {"id": 456, "email": "sensitive-private@example.invalid"},
                "orders_requested": [101, 102],
                "data_request": {"id": 9999},
            }),
            ("customers/redact", {
                "customer": {"id": 456, "phone": "+573000000001"},
                "orders_to_redact": [101],
            }),
            ("shop/redact", {}),
        ]
        received_ids = []
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": "test-shopify-secret"}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            for topic, selectors in cases:
                body = json.dumps({
                    "shop_id": 123,
                    "shop_domain": "test-store.myshopify.com",
                    **selectors,
                }, separators=(",", ":")).encode("utf-8")
                secret, headers = _signed_headers(body, topic)
                assert secret == "test-shopify-secret"
                headers["X-Shopify-Webhook-Id"] = "synthetic-" + topic.replace("/", "-")
                headers["X-Shopify-Shop-Domain"] = "test-store.myshopify.com"
                good = client.post(
                    "/api/webhooks/shopify/compliance",
                    content=body, headers=headers,
                )
                retry = client.post(
                    "/api/webhooks/shopify/compliance",
                    content=body, headers=headers,
                )
                assert good.status_code == retry.status_code == 200
                assert good.json()["action"] == "recorded"
                assert retry.json()["action"] == "duplicate"
                assert good.json()["processing_tasks_prepared"] is True
                assert retry.json()["processing_tasks_prepared"] is True
                assert good.json()["request_id"] == retry.json()["request_id"]
                assert topic == good.json()["topic"]
                assert "sensitive-private@example.invalid" not in good.text
                assert "+573000000001" not in good.text
                received_ids.append(good.json()["request_id"])

                forged_headers = dict(headers)
                forged_headers["X-Shopify-Hmac-Sha256"] = "forged"
                forged = client.post(
                    "/api/webhooks/shopify/compliance",
                    content=body, headers=forged_headers,
                )
                assert forged.status_code == 401

        assert len(set(received_ids)) == len(cases)
        with TEST_SESSION() as session:
            records = session.query(ShopifyPrivacyRequest).all()
            assert len(records) == 3
            assert {r.topic for r in records} == {topic for topic, _ in cases}
            assert all(r.status == "pending_policy_review" for r in records)
            assert all("sensitive-private@example.invalid" not in r.selector_encrypted for r in records)
            assert all("+573000000001" not in r.selector_encrypted for r in records)

            tasks = session.query(ShopifyPrivacyWorkItem).all()
            assert len(tasks) == 30
            for request_id in received_ids:
                selected = [item for item in tasks if item.request_id == request_id]
                assert len(selected) == 10
                assert len({item.area for item in selected}) == 10
                assert any(item.area == "signed_receipt" and item.status == "verified" for item in selected)
                assert all(item.status not in {"completed", "fulfilled"} for item in selected)

            audits = session.query(ShopifyPrivacyAuditEvent).all()
            assert len(audits) == 6
            assert sum(e.event_type == "received" for e in audits) == 3
            assert sum(e.event_type == "processing_prepared" for e in audits) == 3

            report = summarize_shopify_privacy_operations(
                session,
                environment={
                    "SHOPIFY_CLIENT_SECRET": "test-shopify-secret",
                    "SHOPIFY_TOKEN_ENCRYPTION_KEY": "present-for-test-only",
                },
            )
            assert report["receipt_total"] == 3
            assert all(v == 1 for v in report["topic_receipts"].values())
            assert report["distinct_signed_received_audits"] == 3
            assert report["distinct_processing_prepared_audits"] == 3
            assert report["receipts_missing_complete_ten_item_queue"] == 0
            assert report["active_suppressions"] == 0
            assert report["review_required"] is False
            assert report["released_shopify_subscription_verified"] is False
            assert report["valid_live_shopify_delivery_verified"] is False
            assert report["data_export_or_erasure_fulfilled"] is False
            safe_report = json.dumps(report)
            assert "sensitive-private@example.invalid" not in safe_report
            assert "test-store.myshopify.com" not in safe_report
