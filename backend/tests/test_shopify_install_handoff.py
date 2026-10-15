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


def test_public_install_disabled_fails_closed_without_external_handoff(monkeypatch):
    monkeypatch.delenv("SHOPIFY_OAUTH_FIRST_ENABLED", raising=False)
    with patch("app.api.shopify.shopify_public_install.begin_public_install") as begin:
        with pytest.raises(HTTPException) as exc:
            shopify_install_handoff(shop="sample.myshopify.com")
    assert exc.value.status_code == 503
    assert exc.value.detail == "SHOPIFY_PUBLIC_INSTALL_NOT_ENABLED"
    assert exc.value.headers["Cache-Control"] == "no-store"
    begin.assert_not_called()


def test_public_install_disabled_cannot_redirect_to_diaglob_login(monkeypatch):
    monkeypatch.setenv("SHOPIFY_OAUTH_FIRST_ENABLED", "false")
    with patch("app.api.shopify.shopify_public_install.begin_public_install") as begin:
        with pytest.raises(HTTPException) as exc:
            shopify_install_handoff(shop="sample.myshopify.com")
    assert exc.value.status_code == 503
    assert "shopify/install?shop=" not in exc.value.detail
    begin.assert_not_called()


def test_public_install_enabled_goes_directly_to_shopify_oauth(monkeypatch):
    monkeypatch.setenv("SHOPIFY_OAUTH_FIRST_ENABLED", "true")
    target = "https://sample.myshopify.com/admin/oauth/authorize?state=fixture"
    with patch(
        "app.api.shopify.shopify_public_install.begin_public_install",
        return_value=target,
    ) as begin:
        response = shopify_install_handoff(shop="sample.myshopify.com", db=object())
    assert response.status_code == 303
    assert response.headers["location"] == target
    assert response.headers["cache-control"] == "no-store"
    begin.assert_called_once()


def test_public_install_enabled_invalid_shop_fails_without_fallback(monkeypatch):
    from app.services.shopify_service import ShopifyOAuthError

    monkeypatch.setenv("SHOPIFY_OAUTH_FIRST_ENABLED", "true")
    with patch(
        "app.api.shopify.shopify_public_install.begin_public_install",
        side_effect=ShopifyOAuthError("INVALID_SHOPIFY_DOMAIN"),
    ):
        with pytest.raises(HTTPException) as exc:
            shopify_install_handoff(shop="https://evil.myshopify.com", db=object())
    assert exc.value.status_code == 400
