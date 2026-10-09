import base64
import hashlib
import hmac
import json
import os
from unittest.mock import patch


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

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False):
            first = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers
            )
            second = client.post(
                "/api/webhooks/shopify/compliance", content=body, headers=headers
            )

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

        with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": secret}, clear=False):
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
