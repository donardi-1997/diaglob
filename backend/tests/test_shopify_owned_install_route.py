"""Shopify App Store 2.3.1: the public install must be Shopify-owned."""

import pytest
from fastapi import HTTPException

from app.api.shopify import ShopifyConnectRequest, start_shopify_connection


@pytest.mark.parametrize(
    "untrusted_domain",
    [
        "legitimate.myshopify.com",
        "other-tenant.myshopify.com",
    ],
)
def test_manual_domain_connect_cannot_start_shopify_oauth(untrusted_domain):
    # Deliberately pass unusable authorization objects. The retired endpoint
    # must reject the request without reading a tenant, token, or writing state.
    with pytest.raises(HTTPException) as caught:
        start_shopify_connection(
            store_id=25,
            payload=ShopifyConnectRequest(shop_domain=untrusted_domain),
            membership=object(),
            db=object(),
        )

    assert caught.value.status_code == 410
    assert caught.value.detail["code"] == "SHOPIFY_MANAGED_INSTALL_REQUIRED"
    assert caught.value.headers["Cache-Control"] == "no-store"
    assert "Shopify Admin" in caught.value.detail["message"]
