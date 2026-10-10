"""Shopify App Store entry handoff: safe URL and no implicit authorization."""
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.shopify import shopify_install_handoff
from app.services.shopify_install_handoff import (
    ShopifyInstallHandoffError, build_shopify_install_handoff,
)


def test_handoff_targets_configured_fixed_frontend(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://diaglob.tech")
    url = build_shopify_install_handoff("SAMPLE.MYSHOPIFY.COM")
    assert url == "https://diaglob.tech/shopify/install?shop=sample.myshopify.com"
    assert "oauth" not in url
    assert "state=" not in url


@pytest.mark.parametrize("shop", [
    "https://sample.myshopify.com",
    "http://sample.myshopify.com",
    "sample.myshopify.com/evil",
    "sample.myshopify.com@evil.com",
    "sample.myshopify.com.evil.com",
    "//evil.com",
    "sample.myshopify.com?next=evil",
    "sample.myshopify.com:8443",
    "a" * 300,
])
def test_malformed_shop_cannot_be_used_as_redirect(shop, monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://diaglob.tech")
    with pytest.raises(ShopifyInstallHandoffError, match="INVALID_SHOP_DOMAIN"):
        build_shopify_install_handoff(shop)


@pytest.mark.parametrize("base", [
    "http://diaglob.tech",
    "https://diaglob.tech.evil.com/account",  # path
    "https://username:password@diaglob.tech",
    "https://diaglob.tech?return_to=https://evil.com",
    "https://diaglob.tech/#home",
    "https://diaglob.tech:444",
    "//diaglob.tech",
])
def test_unsafe_frontend_config_fails_closed(base, monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", base)
    with pytest.raises(ShopifyInstallHandoffError, match="FRONTEND_URL_NOT_SAFE"):
        build_shopify_install_handoff("sample.myshopify.com")


def test_handoff_route_has_no_database_or_oauth_side_effects(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://diaglob.tech")
    with patch("app.api.shopify.svc_start_oauth") as start, patch(
        "app.api.shopify.svc_process_oauth_callback"
    ) as callback:
        response = shopify_install_handoff(shop="sample.myshopify.com")
    assert response.status_code == 303
    assert response.headers["location"] == (
        "https://diaglob.tech/shopify/install?shop=sample.myshopify.com"
    )
    assert response.headers["cache-control"] == "no-store"
    start.assert_not_called()
    callback.assert_not_called()


def test_handoff_route_invalid_shop_is_client_error(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://diaglob.tech")
    with pytest.raises(HTTPException) as exc:
        shopify_install_handoff(shop="https://evil.myshopify.com")
    assert exc.value.status_code == 400


def test_handoff_will_not_treat_extra_shopify_headers_as_proof(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://diaglob.tech")
    response = shopify_install_handoff(shop="shop.myshopify.com")
    assert response.status_code == 303
    assert "access_token" not in response.headers["location"]
    assert "org=" not in response.headers["location"]
