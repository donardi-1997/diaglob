import base64
import hashlib
import hmac
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.shopify import router
from app.db import Base, get_db
from app.main import app
from app.services.shopify_compliance_webhooks import (
    process_shopify_compliance_webhook,
)
from app.services.shopify_webhook_service import verify_shopify_webhook_hmac


TEST_ENGINE = create_engine("sqlite://", connect_args={"check_same_thread": False})
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
