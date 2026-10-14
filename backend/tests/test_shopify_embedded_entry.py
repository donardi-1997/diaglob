"""Contract tests for the isolated Shopify iframe entry route."""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_shopify_embedded_entry_is_frameable_only_from_shopify():
    with patch.dict("os.environ", {"SHOPIFY_CLIENT_ID": "c5fc9aed710462d41767477fa9e595c0"}):
        response = TestClient(app).get("/api/shopify/embedded")
    assert response.status_code == 200
    assert "https://cdn.shopify.com/shopifycloud/app-bridge.js" in response.text
    assert 'name="shopify-api-key"' in response.text
    assert "frame-ancestors https://admin.shopify.com https://*.myshopify.com" in response.headers["content-security-policy"]
    assert "x-frame-options" not in response.headers
    assert response.headers["cache-control"] == "no-store"


def test_regular_endpoints_are_still_not_frameable():
    response = TestClient(app).get("/api/health")
    assert response.headers["x-frame-options"] == "DENY"


def test_embedded_page_fails_closed_without_matching_client_id():
    with patch.dict("os.environ", {"SHOPIFY_CLIENT_ID": "different-id"}):
        response = TestClient(app).get("/api/shopify/embedded")
    assert response.status_code == 503
    assert response.headers["x-frame-options"] == "DENY"
