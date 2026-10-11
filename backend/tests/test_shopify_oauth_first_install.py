"""OAuth-first Shopify install contract: no DIAGLOB tenant before Shopify grant."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.db import Base
from app.models import CommerceConnection, ShopifyPendingInstall, Store
from app.api.shopify import shopify_install_handoff
from app.services.shopify_public_install import (
    begin_public_install, finish_public_install, claim_install,
    pending_install_status, ShopifyOAuthError, ShopifyConnectionError,
)


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "test-client")
    monkeypatch.setenv("SHOPIFY_REDIRECT_URI", "https://api.diaglob.tech/api/shopify/callback")
    with Session(engine) as db:
        yield db
    engine.dispose()


def _begin(db):
    url = begin_public_install(db, "dev-shop.myshopify.com")
    state = parse_qs(urlsplit(url).query)["state"][0]
    return url, state


def _callback(state, shop="dev-shop.myshopify.com"):
    return {"state": state, "code": "test-code", "shop": shop, "hmac": "synthetic"}


def _finish(db, state, provider_shop="dev-shop.myshopify.com"):
    with patch(
        "app.services.shopify_public_install.verify_shopify_hmac", return_value=True
    ), patch(
        "app.services.shopify_public_install.exchange_access_token",
        return_value="synthetic-token",
    ) as exchange, patch(
        "app.services.shopify_public_install.ShopifyGraphQLClient"
    ) as client, patch(
        "app.services.shopify_public_install.encrypt_shopify_secret",
        return_value="encrypted-fixture",
    ):
        client.return_value.query.return_value = {
            "shop": {"myshopifyDomain": provider_shop}
        }
        result = finish_public_install(db, _callback(state))
    return result, exchange


def test_install_enters_shopify_oauth_immediately_without_tenant(database, monkeypatch):
    monkeypatch.setenv("SHOPIFY_OAUTH_FIRST_ENABLED", "true")
    url, state = _begin(database)
    assert url.startswith("https://dev-shop.myshopify.com/admin/oauth/authorize?")
    assert "redirect_uri" in parse_qs(urlsplit(url).query)
    grant = database.query(ShopifyPendingInstall).filter_by(state=state).one()
    assert grant.shop_domain == "dev-shop.myshopify.com"
    assert grant.token_encrypted is None
    response = shopify_install_handoff(shop="dev-shop.myshopify.com", db=database)
    assert response.status_code == 303
    assert response.headers["location"].startswith(
        "https://dev-shop.myshopify.com/admin/oauth/authorize?"
    )


def test_callback_one_use_provider_identity_and_no_browser_token(database):
    _, state = _begin(database)
    cookie, exchange = _finish(database, state)
    assert len(cookie) >= 32
    assert "synthetic-token" not in cookie
    assert pending_install_status(database, cookie)["shop_domain"] == "dev-shop.myshopify.com"
    with patch("app.services.shopify_public_install.verify_shopify_hmac", return_value=True):
        with pytest.raises(ShopifyOAuthError, match="already used"):
            finish_public_install(database, _callback(state))
    exchange.assert_called_once()


def test_invalid_hmac_or_shop_cannot_exchange(database):
    _, state = _begin(database)
    with patch("app.services.shopify_public_install.exchange_access_token") as exchange:
        with pytest.raises(ShopifyOAuthError, match="HMAC"):
            finish_public_install(database, _callback(state))
        with patch("app.services.shopify_public_install.verify_shopify_hmac", return_value=True):
            with pytest.raises(ShopifyOAuthError):
                finish_public_install(database, _callback(state, shop="evil.myshopify.com"))
    exchange.assert_not_called()


def test_expired_or_wrong_identity_grant_never_usable(database):
    _, state = _begin(database)
    grant = database.query(ShopifyPendingInstall).filter_by(state=state).one()
    grant.expires_at = datetime.utcnow() - timedelta(seconds=1)
    database.commit()
    with patch("app.services.shopify_public_install.verify_shopify_hmac", return_value=True):
        with pytest.raises(ShopifyOAuthError):
            finish_public_install(database, _callback(state))
    assert pending_install_status(database, "fake") == {
        "pending": False, "shop_domain": None
    }


def test_provider_shop_identity_mismatch_does_not_stage_token(database):
    _, state = _begin(database)
    with pytest.raises(Exception, match="SHOPIFY_INSTALL_VERIFICATION_FAILED"):
        _finish(database, state, "wrong.myshopify.com")
    grant = database.query(ShopifyPendingInstall).filter_by(state=state).one()
    assert grant.state_used is True
    assert grant.token_encrypted is None


def test_claim_binds_once_only_to_explicit_authorized_store(database):
    _, state = _begin(database)
    cookie, _ = _finish(database, state)
    membership = SimpleNamespace(organization_id=31)
    store = Store(id=7, organization_id=31, name="Test", slug="test",
                  country_code="CO", active=True, deleted=False)
    with patch(
        "app.services.shopify_public_install.activate_trial_for_verified_store",
        return_value={"trial_activated": False},
    ), patch(
        "app.services.shopify_public_install.confirm_shopify_install_billing",
        return_value=False,
    ):
        result = claim_install(database, secret=cookie, membership=membership, store=store)
    assert result["connected"] is True
    connection = database.query(CommerceConnection).one()
    assert connection.store_id == 7 and connection.organization_id == 31
    assert connection.access_token_encrypted == "encrypted-fixture"
    assert pending_install_status(database, cookie)["pending"] is False
    with pytest.raises(ShopifyOAuthError, match="EXPIRED"):
        claim_install(database, secret=cookie, membership=membership, store=store)


def test_wrong_tenant_is_rejected_without_consuming_grant(database):
    _, state = _begin(database)
    cookie, _ = _finish(database, state)
    store = Store(id=8, organization_id=99, name="Wrong", slug="wrong",
                  country_code="CO", active=True, deleted=False)
    with pytest.raises(ShopifyOAuthError, match="STORE_INVALID"):
        claim_install(database, secret=cookie,
                      membership=SimpleNamespace(organization_id=31), store=store)
    database.rollback()
    assert pending_install_status(database, cookie)["pending"] is True
