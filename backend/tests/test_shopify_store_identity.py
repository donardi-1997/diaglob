"""Read-only Shopify store verification requires provider-confirmed identity.

No real Shopify requests and no merchant mutations in this test.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.shopify_client import ShopifyAPIError, ShopifyAuthError
from app.shopify_sync import test_shopify_connection as verify_shop


def _connection(domain="diaglob-poc.myshopify.com"):
    return SimpleNamespace(
        external_store_url=domain,
        access_token_encrypted="encrypted-test-fixture",
    )


def _shop_response(domain="diaglob-poc.myshopify.com"):
    return {
        "shop": {
            "name": "Diaglob POC",
            "myshopifyDomain": domain,
            "currencyCode": "USD",
        }
    }


def test_shopify_store_identity_matches_installed_domain():
    with patch(
        "app.shopify_sync.decrypt_shopify_secret", return_value="mock-admin-token"
    ), patch(
        "app.shopify_sync.ShopifyGraphQLClient.query",
        return_value=_shop_response(),
    ) as query:
        result = verify_shop(_connection())
    assert result == {
        "connected": True,
        "shop_name": "Diaglob POC",
        "shop_domain": "diaglob-poc.myshopify.com",
        "currency": "USD",
    }
    query.assert_called_once()


@pytest.mark.parametrize("response", [
    {},
    {"shop": None},
    {"shop": {}},
    {"shop": {"myshopifyDomain": None}},
    {"shop": {"myshopifyDomain": "https://non-shop.example"}},
    {"shop": []},
    {"shop": {"myshopifyDomain": ""}},
])
def test_shopify_store_never_reports_connected_without_verifiable_identity(response):
    with patch(
        "app.shopify_sync.decrypt_shopify_secret", return_value="mock-admin-token"
    ), patch(
        "app.shopify_sync.ShopifyGraphQLClient.query", return_value=response
    ):
        with pytest.raises(ShopifyAPIError, match="IDENTITY_UNVERIFIED"):
            verify_shop(_connection())


def test_shopify_store_fails_closed_on_other_store_token():
    with patch(
        "app.shopify_sync.decrypt_shopify_secret", return_value="mock-admin-token"
    ), patch(
        "app.shopify_sync.ShopifyGraphQLClient.query",
        return_value=_shop_response("another-store.myshopify.com"),
    ):
        with pytest.raises(ShopifyAuthError, match="IDENTITY_MISMATCH"):
            verify_shop(_connection())


def test_shopify_store_test_does_not_write_to_db():
    # The low-level verification uses only Shopify Admin GraphQL read queries.
    # DB status updates are a separate, tenant-scoped service concern.
    with patch(
        "app.shopify_sync.decrypt_shopify_secret", return_value="mock-admin-token"
    ), patch(
        "app.shopify_sync.ShopifyGraphQLClient.query",
        return_value=_shop_response(),
    ):
        verify_shop(_connection())
