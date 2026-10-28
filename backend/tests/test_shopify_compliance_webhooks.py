import base64
import hashlib
import hmac
import json
import logging
import os

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
from app.models import CommerceConnection, ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest, ShopifyPrivacyShopIdentity, ShopifyPrivacyWorkItem
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

    def test_replayed_webhook_id_cannot_hide_changed_customer_or_orders(self, client):
        original = {
            "shop_id": 123,
            "shop_domain": "test-store.myshopify.com",
            "customer": {"id": 456},
            "orders_to_redact": [789],
        }
        modified = {
            **original,
            "customer": {"id": 999},
            "orders_to_redact": [900],
        }
        first_body = json.dumps(original).encode()
        changed_body = json.dumps(modified).encode()
        secret, headers = _signed_headers(first_body, "customers/redact")
        headers["X-Shopify-Webhook-Id"] = "same-delivery-id"
        _, changed_headers = _signed_headers(changed_body, "customers/redact")
        changed_headers["X-Shopify-Webhook-Id"] = "same-delivery-id"

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            first = client.post(
                "/api/webhooks/shopify/compliance",
                content=first_body, headers=headers,
            )
            duplicate = client.post(
                "/api/webhooks/shopify/compliance",
                content=first_body, headers=headers,
            )
            conflict = client.post(
                "/api/webhooks/shopify/compliance",
                content=changed_body, headers=changed_headers,
            )

        assert first.status_code == duplicate.status_code == 200
        assert duplicate.json()["action"] == "duplicate"
        assert conflict.status_code == 400
        assert conflict.json()["detail"] == "PRIVACY_WEBHOOK_DELIVERY_CONFLICT"
        assert "999" not in conflict.text
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 1
            record = session.query(ShopifyPrivacyRequest).one()
            assert json.loads(decrypt_shopify_secret(
                record.selector_encrypted
            ))["customer"]["id"] == 456
            assert session.query(ShopifyPrivacyWorkItem).count() == 10

    def test_replayed_delivery_refuses_corrupt_existing_identity(self, client):
        body = json.dumps({
            "shop_id": 123, "shop_domain": "test-store.myshopify.com",
            "customer": {"id": 456},
        }).encode()
        secret, headers = _signed_headers(body, "customers/data_request")
        headers["X-Shopify-Webhook-Id"] = "identity-check"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            first = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers
            )
            assert first.status_code == 200
            with TEST_SESSION() as session:
                receipt = session.query(ShopifyPrivacyRequest).one()
                receipt.shop_id = "different-signed-shop"
                session.commit()
            replay = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers
            )
        assert replay.status_code == 400
        assert replay.json()["detail"] == "PRIVACY_WEBHOOK_DELIVERY_CONFLICT"

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
            return_value=CommerceConnection(
                organization_id=19, store_id=47, provider="shopify",
                status="connected", external_store_url="known.myshopify.com",
            ),
        ):
            response = client.post("/api/webhooks/shopify/compliance", content=body, headers=headers)
        assert response.status_code == 200
        with TEST_SESSION() as session:
            item = session.query(ShopifyPrivacyRequest).one()
            assert (item.organization_id, item.store_id) == (19, 47)
            assert item.topic == "customers/redact"
            assert session.query(ShopifyPrivacyShopIdentity).count() == 1
            identity = session.query(ShopifyPrivacyShopIdentity).one()
            assert (identity.shop_id, identity.shop_domain) == (
                "321", "known.myshopify.com",
            )
            assert (identity.organization_id, identity.store_id) == (19, 47)

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
            assert session.query(ShopifyPrivacyShopIdentity).count() == 0


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

    def test_same_delivery_id_cross_shop_is_conflict_not_second_receipt(self, client):
        first_payload = {"shop_id": 123, "shop_domain": "first.myshopify.com"}
        second_payload = {"shop_id": 456, "shop_domain": "second.myshopify.com"}
        first_body = json.dumps(first_payload).encode()
        second_body = json.dumps(second_payload).encode()
        secret, first_headers = _signed_headers(first_body, "shop/redact")
        _, second_headers = _signed_headers(second_body, "shop/redact")
        first_headers["X-Shopify-Webhook-Id"] = "global-delivery-unique"
        second_headers["X-Shopify-Webhook-Id"] = "global-delivery-unique"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            first = client.post(
                "/api/webhooks/shopify/compliance",
                content=first_body, headers=first_headers,
            )
            conflict = client.post(
                "/api/webhooks/shopify/compliance",
                content=second_body, headers=second_headers,
            )
        assert first.status_code == 200
        assert conflict.status_code == 400
        assert conflict.json()["detail"] == "PRIVACY_WEBHOOK_DELIVERY_CONFLICT"
        assert "second.myshopify.com" not in conflict.text
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 1
            assert session.query(ShopifyPrivacyWorkItem).count() == 10

    def test_same_delivery_id_cross_topic_is_conflict_not_second_receipt(self, client):
        payload = {"shop_id": 777, "shop_domain": "test-store.myshopify.com"}
        body = json.dumps(payload).encode()
        secret, first_headers = _signed_headers(body, "shop/redact")
        _, second_headers = _signed_headers(body, "customers/redact")
        first_headers["X-Shopify-Webhook-Id"] = "global-topic-unique"
        second_headers["X-Shopify-Webhook-Id"] = "global-topic-unique"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            assert client.post(
                "/api/webhooks/shopify/compliance",
                content=body, headers=first_headers,
            ).status_code == 200
            conflict = client.post(
                "/api/webhooks/shopify/compliance",
                content=body, headers=second_headers,
            )
        assert conflict.status_code == 400
        assert conflict.json()["detail"] == "PRIVACY_WEBHOOK_DELIVERY_CONFLICT"
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 1

    def test_retry_accepts_historical_key_without_creating_second_receipt(self, client):
        from app.services.shopify_compliance_webhooks import _legacy_delivery_key

        payload = {"shop_id": 456, "shop_domain": "test-store.myshopify.com"}
        body = json.dumps(payload).encode()
        secret, headers = _signed_headers(body, "shop/redact")
        headers["X-Shopify-Webhook-Id"] = "historical-retry"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            original = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
            assert original.status_code == 200
            legacy = _legacy_delivery_key("shop/redact", payload, "historical-retry")
            with TEST_SESSION() as session:
                session.query(ShopifyPrivacyRequest).update(
                    {"request_id": legacy}, synchronize_session=False,
                )
                session.query(ShopifyPrivacyWorkItem).update(
                    {"request_id": legacy}, synchronize_session=False,
                )
                session.query(ShopifyPrivacyAuditEvent).update(
                    {"request_id": legacy}, synchronize_session=False,
                )
                session.commit()
            retry = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
        assert retry.status_code == 200
        assert retry.json()["action"] == "duplicate"
        assert retry.json()["request_id"] == legacy
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 1
            assert session.query(ShopifyPrivacyWorkItem).count() == 10
            assert session.query(ShopifyPrivacyAuditEvent).count() == 2

    @pytest.mark.parametrize("missing_event,actor", [
        ("received", "shopify_hmac_verified"),
        ("processing_prepared", "internal_privacy_processor"),
    ])
    def test_retry_without_required_audit_returns_500(
        self, client, missing_event, actor,
    ):
        payload = {"shop_id": 456, "shop_domain": "test-store.myshopify.com"}
        body = json.dumps(payload).encode()
        secret, headers = _signed_headers(body, "shop/redact")
        headers["X-Shopify-Webhook-Id"] = "missing-" + missing_event
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            first = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
            assert first.status_code == 200
            with TEST_SESSION() as session:
                session.query(ShopifyPrivacyAuditEvent).filter(
                    ShopifyPrivacyAuditEvent.event_type == missing_event,
                    ShopifyPrivacyAuditEvent.actor_type == actor,
                ).delete()
                session.commit()
            retry = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
        assert retry.status_code == 500
        assert retry.json()["detail"] == "Shopify compliance webhook processing failed"
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 1
            assert session.query(ShopifyPrivacyWorkItem).count() == 10

    @pytest.mark.parametrize("tampering", ["completed_status", "wrong_action", "partial_queue"])
    def test_retry_does_not_acknowledge_corrupt_review_tasks(self, client, tampering):
        payload = {"shop_id": 456, "shop_domain": "test-store.myshopify.com"}
        body = json.dumps(payload).encode()
        secret, headers = _signed_headers(body, "shop/redact")
        headers["X-Shopify-Webhook-Id"] = "corrupt-" + tampering
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            first = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
            assert first.status_code == 200
            with TEST_SESSION() as session:
                task = session.query(ShopifyPrivacyWorkItem).filter(
                    ShopifyPrivacyWorkItem.area == "local_structured_records",
                ).one()
                if tampering == "completed_status":
                    task.status = "completed"
                elif tampering == "wrong_action":
                    task.action = "deliver"
                else:
                    session.delete(task)
                session.commit()
            retry = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
        assert retry.status_code == 500
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyRequest).count() == 1
            assert session.query(ShopifyPrivacyAuditEvent).count() == 2

    def test_retry_recreates_missing_tasks_without_duplicate_prepared_audit(self, client):
        payload = {"shop_id": 456, "shop_domain": "test-store.myshopify.com"}
        body = json.dumps(payload).encode()
        secret, headers = _signed_headers(body, "shop/redact")
        headers["X-Shopify-Webhook-Id"] = "recover-no-duplicate-audit"
        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}), patch(
            "app.services.shopify_compliance_webhooks.resolve_shopify_connection",
            return_value=None,
        ):
            first = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
            assert first.status_code == 200
            with TEST_SESSION() as session:
                session.query(ShopifyPrivacyWorkItem).delete()
                session.commit()
            restored = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers,
            )
        assert restored.status_code == 200
        assert restored.json()["action"] == "duplicate"
        with TEST_SESSION() as session:
            assert session.query(ShopifyPrivacyWorkItem).count() == 10
            assert session.query(ShopifyPrivacyAuditEvent).filter(
                ShopifyPrivacyAuditEvent.event_type == "processing_prepared",
            ).count() == 1


def test_privacy_webhook_failure_does_not_log_customer_identifier(client, caplog):
    body = json.dumps({
        "shop_id": 12, "shop_domain": "synthetic.myshopify.com",
        "customer": {"email": "SECRET_CUSTOMER@example.com"},
    }).encode("utf-8")
    secret, headers = _signed_headers(body, "customers/data_request")
    with (
        patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}),
        patch(
            "app.api.shopify.process_shopify_compliance_webhook",
            side_effect=RuntimeError(
                "Provider crash with SECRET_CUSTOMER@example.com"
            ),
        ),
        caplog.at_level(logging.ERROR),
    ):
        resp = client.post(
            "/api/webhooks/shopify/compliance", content=body, headers=headers,
        )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Shopify compliance webhook processing failed"
    assert "SECRET_CUSTOMER@example.com" not in caplog.text
    assert "SECRET_CUSTOMER@example.com" not in resp.text


def test_privacy_webhook_value_error_is_a_sanitized_machine_code(client):
    body = json.dumps({
        "shop_id": 13, "shop_domain": "synthetic.myshopify.com",
        "customer": {"email": "SECRET_CUSTOMER@example.com"},
    }).encode("utf-8")
    secret, headers = _signed_headers(body, "customers/redact")
    with (
        patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}),
        patch(
            "app.api.shopify.process_shopify_compliance_webhook",
            side_effect=ValueError(
                "Untrusted selector SECRET_CUSTOMER@example.com"
            ),
        ),
    ):
        resp = client.post(
            "/api/webhooks/shopify/compliance", content=body, headers=headers,
        )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "INVALID_COMPLIANCE_WEBHOOK_PAYLOAD"
    assert "SECRET_CUSTOMER@example.com" not in resp.text


@pytest.mark.parametrize(
    ("shop_id", "selector_fields"),
    [
        (901, {"customer": {"id": {"nested": "not-a-selector"}}}),
        (902, {"orders_to_redact": [{"id": 789, "email": "not-a-numeric-id"}]}),
        (903, {"customer": {"email": {"nested": "not-a-string"}}}),
        (904, {"customer": {"phone": "x" * 51}}),
        (905, {"data_request": {"id": ["not-a-numeric-id"]}}),
    ],
)
def test_privacy_webhook_rejects_unbounded_or_structured_selectors(
    client, shop_id, selector_fields,
):
    payload = {
        "shop_id": shop_id,
        "shop_domain": f"minimize-{shop_id}.myshopify.com",
        "customer": {"id": 456},
        **selector_fields,
    }
    body = json.dumps(payload).encode("utf-8")
    secret, headers = _signed_headers(body, "customers/redact")
    with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}):
        response = client.post(
            "/api/webhooks/shopify/compliance",
            content=body,
            headers=headers,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "INVALID_COMPLIANCE_WEBHOOK_PAYLOAD"
    assert "not-a-selector" not in response.text
    with TEST_SESSION() as session:
        assert session.query(ShopifyPrivacyRequest).filter(
            ShopifyPrivacyRequest.shop_id == str(shop_id),
        ).count() == 0


def test_privacy_webhook_persists_only_allowlisted_customer_selectors(client):
    payload = {
        "shop_id": 906,
        "shop_domain": "minimize-allowlist.myshopify.com",
        "customer": {
            "id": 456,
            "email": "synthetic@example.com",
            "phone": "+1 555 0100",
            "address": {"line1": "must-not-be-stored"},
            "metafields": [{"key": "unrelated", "value": "must-not-be-stored"}],
        },
        "orders_to_redact": [789],
    }
    body = json.dumps(payload).encode("utf-8")
    secret, headers = _signed_headers(body, "customers/redact")
    with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}):
        response = client.post(
            "/api/webhooks/shopify/compliance",
            content=body,
            headers=headers,
        )

    assert response.status_code == 200
    with TEST_SESSION() as session:
        record = session.query(ShopifyPrivacyRequest).filter(
            ShopifyPrivacyRequest.shop_id == "906",
        ).one()
        selectors = json.loads(decrypt_shopify_secret(record.selector_encrypted))
    assert selectors == {
        "customer": {
            "id": 456,
            "email": "synthetic@example.com",
            "phone": "+1 555 0100",
        },
        "orders_to_redact": [789],
    }
    assert "must-not-be-stored" not in json.dumps(selectors)
