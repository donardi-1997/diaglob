"""Unit tests for the Shopify-managed installation verifier; synthetic data only."""
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api.shopify_embedded import embedded_managed_installation_verify
from app.services.shopify_managed_installation import (
    ManagedShopifyInstallationError,
    verify_managed_installation,
)

SHOP = "diaglob-poc.myshopify.com"
IDENTITY = {"shop": SHOP, "subject": "fixture-user"}


@patch("app.services.shopify_managed_installation.ShopifyGraphQLClient")
@patch("app.services.shopify_managed_installation.httpx.Client")
def test_valid_managed_installation_proof(client, graphql, monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "fixture-value")
    provider = client.return_value.__enter__.return_value
    provider.post.return_value.json.return_value = {"access_token": "fixture-access"}
    graphql.return_value.query.return_value = {"shop": {"myshopifyDomain": SHOP}}
    result = verify_managed_installation(identity=IDENTITY, id_token="fixture-jwt")
    assert result == {
        "shopify_installation_verified": True,
        "diaglob_link_required": True,
        "shop": SHOP,
    }
    data = provider.post.call_args.kwargs["data"]
    assert data["subject_token"] == "fixture-jwt"
    assert data["requested_token_type"].endswith("online-access-token")
    graphql.assert_called_once_with(shop_domain=SHOP, access_token="fixture-access")


@pytest.mark.parametrize("shop", ["invalid.test", "shop.myshopify.com.attacker.test", "", "https://shop.myshopify.com"])
def test_invalid_shop_does_not_contact_shopify(shop, monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "fixture-value")
    with patch("app.services.shopify_managed_installation.httpx.Client") as client:
        with pytest.raises(ManagedShopifyInstallationError):
            verify_managed_installation(identity={"shop": shop}, id_token="fixture-jwt")
    client.assert_not_called()


@patch("app.services.shopify_managed_installation.ShopifyGraphQLClient")
@patch("app.services.shopify_managed_installation.httpx.Client")
def test_provider_shop_identity_must_match(client, graphql, monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "fixture-value")
    client.return_value.__enter__.return_value.post.return_value.json.return_value = {
        "access_token": "fixture-access"
    }
    graphql.return_value.query.return_value = {
        "shop": {"myshopifyDomain": "other.myshopify.com"}
    }
    with pytest.raises(ManagedShopifyInstallationError):
        verify_managed_installation(identity=IDENTITY, id_token="fixture-jwt")


def test_missing_shopify_session_denied():
    with pytest.raises(HTTPException) as exc:
        embedded_managed_installation_verify(credentials=None)
    assert exc.value.status_code == 401


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value=IDENTITY)
@patch("app.api.shopify_embedded.verify_managed_installation", return_value={
    "shopify_installation_verified": True, "diaglob_link_required": True, "shop": SHOP,
})
def test_api_verifies_fresh_shopify_id_token(exchange, verify):
    bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fixture-jwt")
    result = embedded_managed_installation_verify(credentials=bearer)
    assert result["shopify_installation_verified"]
    verify.assert_called_once_with("fixture-jwt")
    exchange.assert_called_once_with(identity=IDENTITY, id_token="fixture-jwt")


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value=IDENTITY)
@patch("app.api.shopify_embedded.verify_managed_installation", side_effect=ManagedShopifyInstallationError("internal"))
def test_provider_failure_fail_closed(exchange, verify):
    bearer = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fixture-jwt")
    with pytest.raises(HTTPException) as exc:
        embedded_managed_installation_verify(credentials=bearer)
    assert exc.value.status_code == 502
    assert exc.value.detail == "Shopify managed installation not verified"
