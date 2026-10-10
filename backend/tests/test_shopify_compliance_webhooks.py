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
from app.models import ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest
from app.shopify_security import decrypt_shopify_secret
from app.services.shopify_compliance_webhooks import (
    process_shopify_compliance_webhook,
)
from app.services.shopify_webhook_service import verify_shopify_webhook_hmac


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
            assert len(audits) == 1
            assert audits[0].request_id == record.request_id
            assert audits[0].event_type == "received"
            assert audits[0].to_status == "pending_policy_review"
            assert audits[0].actor_type == "shopify_hmac_verified"
            assert "private@example.com" not in str(audits[0].__dict__)

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
