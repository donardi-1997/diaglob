"""Shopify App Pricing verification must never authorize charges by itself."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.services.shopify_app_pricing import (
    ShopifyAppPricingError,
    get_active_shopify_subscription,
    resolve_trusted_shop_gid,
)


def _env(monkeypatch):
    monkeypatch.setenv("SHOPIFY_PARTNER_ORG_ID", "5148778")
    monkeypatch.setenv("SHOPIFY_PARTNER_APP_GID", "gid://shopify/App/416524435457")
    monkeypatch.setenv("SHOPIFY_PARTNER_ACCESS_TOKEN", "test-credential")


def _client(payload, *, status=200, requests=None):
    def handler(request):
        if requests is not None:
            requests.append(request)
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_active_subscription_is_verified_by_partner_api(monkeypatch):
    _env(monkeypatch)
    requests = []
    payload = {
        "data": {
            "activeSubscription": {
                "billingPeriod": "MONTHLY",
                "cancelAtEndOfCycle": False,
                "trialEndsAt": None,
                "currentBillingCycle": {
                    "startTime": "2026-10-01T00:00:00Z",
                    "endTime": "2026-11-01T00:00:00Z",
                },
                "items": [{"handle": "starter-plan", "description": "Starter"}],
            }
        }
    }
    with _client(payload, requests=requests) as client:
        snapshot = get_active_shopify_subscription(
            "gid://shopify/Shop/12345", http_client=client
        )
    assert snapshot.active is True
    assert snapshot.billing_period == "MONTHLY"
    assert snapshot.item_handles == ("starter-plan",)
    assert snapshot.current_cycle_end == "2026-11-01T00:00:00Z"
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == (
        "https://partners.shopify.com/5148778/api/2026-10/graphql.json"
    )
    assert request.headers["X-Shopify-Access-Token"] == "test-credential"
    params = json.loads(request.content)["variables"]
    assert params == {
        "appId": "gid://shopify/App/416524435457",
        "shopId": "gid://shopify/Shop/12345",
    }


def test_missing_subscription_fails_closed_as_inactive(monkeypatch):
    _env(monkeypatch)
    with _client({"data": {"activeSubscription": None}}) as client:
        snapshot = get_active_shopify_subscription(
            "gid://shopify/Shop/9", http_client=client
        )
    assert snapshot.active is False
    assert snapshot.item_handles == ()


@pytest.mark.parametrize(
    "response,status",
    [
        ({"errors": [{"message": "not authorized"}]}, 200),
        ({"data": {}}, 200),
        ({"data": {"activeSubscription": {"items": "invalid"}}}, 200),
        ({"data": {"activeSubscription": None}}, 401),
        ({"data": {"activeSubscription": None}}, 429),
    ],
)
def test_errors_cannot_grant_entitlements(monkeypatch, response, status):
    _env(monkeypatch)
    with _client(response, status=status) as client:
        with pytest.raises(ShopifyAppPricingError):
            get_active_shopify_subscription(
                "gid://shopify/Shop/9", http_client=client
            )


def test_partner_api_requires_explicit_configuration(monkeypatch):
    monkeypatch.delenv("SHOPIFY_PARTNER_ORG_ID", raising=False)
    monkeypatch.delenv("SHOPIFY_PARTNER_APP_GID", raising=False)
    monkeypatch.delenv("SHOPIFY_PARTNER_ACCESS_TOKEN", raising=False)
    with pytest.raises(ShopifyAppPricingError, match="NOT_CONFIGURED"):
        get_active_shopify_subscription("gid://shopify/Shop/123")


@pytest.mark.parametrize(
    "shop_gid",
    ["", "fake.myshopify.com", "gid://shopify/Shop/1?x=1", "gid://shopify/App/1"],
)
def test_user_supplied_shop_domain_cannot_be_used_as_shop_gid(shop_gid, monkeypatch):
    _env(monkeypatch)
    with pytest.raises(ShopifyAppPricingError, match="INVALID_SHOP_GID"):
        get_active_shopify_subscription(shop_gid)


def test_paddle_registry_remains_default():
    from app.billing_providers.registry import registered_billing_providers
    from app.billing_providers.registry import get_billing_provider

    assert "paddle" in registered_billing_providers()
    assert get_billing_provider().name == "paddle"

def test_trusted_shop_gid_resolved_with_authenticated_store_token():
    connection = SimpleNamespace(
        provider="shopify",
        status="connected",
        external_store_url="some-store.myshopify.com",
        access_token_encrypted="encrypted-token",
    )
    with patch(
        "app.services.shopify_app_pricing.decrypt_shopify_secret",
        return_value="access-token",
    ), patch(
        "app.services.shopify_app_pricing.ShopifyGraphQLClient"
    ) as client:
        client.return_value.query.return_value = {
            "shop": {
                "id": "gid://shopify/Shop/123",
                "myshopifyDomain": "some-store.myshopify.com",
            }
        }
        gid = resolve_trusted_shop_gid(connection)
    assert gid == "gid://shopify/Shop/123"
    client.assert_called_once_with(
        shop_domain="some-store.myshopify.com",
        access_token="access-token",
    )


@pytest.mark.parametrize(
    "returned_shop",
    [
        {"id": "gid://shopify/Shop/123", "myshopifyDomain": "other.myshopify.com"},
        {"id": "not-a-gid", "myshopifyDomain": "some-store.myshopify.com"},
        {},
    ],
)
def test_shop_gid_rejects_mismatched_or_invalid_admin_identity(returned_shop):
    connection = SimpleNamespace(
        provider="shopify",
        status="connected",
        external_store_url="some-store.myshopify.com",
        access_token_encrypted="token",
    )
    with patch(
        "app.services.shopify_app_pricing.decrypt_shopify_secret",
        return_value="access-token",
    ), patch(
        "app.services.shopify_app_pricing.ShopifyGraphQLClient"
    ) as client:
        client.return_value.query.return_value = {"shop": returned_shop}
        with pytest.raises(ShopifyAppPricingError):
            resolve_trusted_shop_gid(connection)


def test_disconnected_shopify_connection_cannot_verify_subscription():
    connection = SimpleNamespace(
        provider="shopify",
        status="disconnected",
        external_store_url="some-store.myshopify.com",
        access_token_encrypted="token",
    )
    with pytest.raises(ShopifyAppPricingError, match="NOT_VERIFIED"):
        resolve_trusted_shop_gid(connection)
