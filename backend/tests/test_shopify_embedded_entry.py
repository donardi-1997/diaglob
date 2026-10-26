"""Contract tests for the isolated Shopify iframe entry route."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


def test_shopify_embedded_entry_is_frameable_only_from_shopify():
    with patch.dict("os.environ", {"SHOPIFY_CLIENT_ID": "c5fc9aed710462d41767477fa9e595c0"}):
        response = TestClient(app).get("/api/shopify/embedded?shop=synthetic.myshopify.com")
    assert response.status_code == 200
    assert "https://cdn.shopify.com/shopifycloud/app-bridge.js" in response.text
    assert 'name="shopify-api-key"' in response.text
    assert "frame-ancestors https://admin.shopify.com https://synthetic.myshopify.com;" in response.headers["content-security-policy"]
    assert "*" not in response.headers["content-security-policy"]
    assert "x-frame-options" not in response.headers
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("query", [
    "", "?shop=evil.example", "?shop=a.myshopify.com.evil.example",
    "?shop=a.myshopify.com&shop=b.myshopify.com", "?shop=https://a.myshopify.com",
    "?shop=a.myshopify.com%3Bframe-ancestors%20*", "?shop=a.myshopify.com%0D%0Aevil",
])
def test_missing_or_unsafe_shop_cannot_widen_framing(query):
    with patch.dict("os.environ", {"SHOPIFY_CLIENT_ID": "c5fc9aed710462d41767477fa9e595c0"}):
        response = TestClient(app).get("/api/shopify/embedded" + query)
    assert response.headers["content-security-policy"].startswith(
        "frame-ancestors https://admin.shopify.com;",
    )
    assert "*" not in response.headers["content-security-policy"]


def test_regular_endpoints_are_still_not_frameable():
    response = TestClient(app).get("/api/health")
    assert response.headers["x-frame-options"] == "DENY"


def test_embedded_page_fails_closed_without_matching_client_id():
    with patch.dict("os.environ", {"SHOPIFY_CLIENT_ID": "different-id"}):
        response = TestClient(app).get("/api/shopify/embedded")
    assert response.status_code == 503
    assert response.headers["x-frame-options"] == "DENY"
