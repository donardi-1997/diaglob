"""Regression coverage for expiring OAuth authorization-code grants.

No network requests, real merchants or production token exchanges.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    CommerceConnection, Organization, ShopifyOAuthState, ShopifyPendingInstall, Store,
)
from app.shopify_oauth import (
    SHOPIFY_SCOPES, ShopifyExpiringOfflineGrant, exchange_access_token,
)
from app.services import shopify_public_install, shopify_service


def _grant():
    return ShopifyExpiringOfflineGrant(
        access_token="access-expiring",
        refresh_token="rotating-refresh",
        access_token_expires_at=datetime.utcnow() + timedelta(minutes=59),
        refresh_token_expires_at=datetime.utcnow() + timedelta(days=89),
    )


def test_code_exchange_explicitly_requests_expiring_token(monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "test-client")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "test-secret")
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "access_token": "a", "refresh_token": "r",
            "expires_in": 3600, "refresh_token_expires_in": 7776000,
            "scope": SHOPIFY_SCOPES,
        })

    monkeypatch.setattr("app.shopify_oauth.httpx.post", fake_post)
    before = datetime.utcnow()
    result = exchange_access_token("example.myshopify.com", "signed-code")
    assert isinstance(result, ShopifyExpiringOfflineGrant)
    assert result.access_token == "a"
    assert result.refresh_token == "r"
    assert result.access_token_expires_at > before + timedelta(minutes=55)
    assert result.refresh_token_expires_at > before + timedelta(days=80)
    assert len(calls) == 1
    assert calls[0][0] == "https://example.myshopify.com/admin/oauth/access_token"
    assert calls[0][1]["data"] == {
        "client_id": "test-client", "client_secret": "test-secret",
        "code": "signed-code", "expiring": "1",
    }
    assert "json" not in calls[0][1]


@pytest.mark.parametrize("changes", [
    {"refresh_token": None},
    {"expires_in": None},
    {"refresh_token_expires_in": None},
    {"expires_in": True},
    {"refresh_token_expires_in": 0},
    {"scope": "read_products"},
    {"scope": None},
])
def test_code_exchange_rejects_incomplete_or_nonrenewable_grants(monkeypatch, changes):
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "test-client")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "test-secret")
    data = {
        "access_token": "a", "refresh_token": "r",
        "expires_in": 3600, "refresh_token_expires_in": 7776000,
        "scope": SHOPIFY_SCOPES,
    }
    data.update(changes)
    monkeypatch.setattr(
        "app.shopify_oauth.httpx.post",
        lambda url, **kwargs: httpx.Response(
            200, request=httpx.Request("POST", url), json=data,
        ),
    )
    with pytest.raises(RuntimeError, match="SHOPIFY_"):
        exchange_access_token("example.myshopify.com", "signed-code")


@pytest.fixture
def installed_shop():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(
            id=901, name="OAuth sample", slug="shopify-oauth-expiring",
            billing_provider="shopify",
        )
        store = Store(
            id=902, organization_id=901, name="Store",
            slug="oauth-token-store", country_code="CO", currency="COP",
            timezone="America/Bogota", active=True, deleted=False,
        )
        connection = CommerceConnection(
            id=903, organization_id=901, store_id=902, provider="shopify",
            external_store_url="example.myshopify.com",
            access_token_encrypted="original-legacy",
            status="connected", scopes=SHOPIFY_SCOPES,
        )
        db.add_all([org, store, connection])
        db.commit()
        yield db, store, connection
    engine.dispose()


def test_legacy_reauthorization_persists_rotating_credentials(monkeypatch, installed_shop):
    db, store, connection = installed_shop
    db.add(ShopifyOAuthState(
        state="nonce", organization_id=901, store_id=902, user_id=904,
        shop_domain="example.myshopify.com",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
        used=False,
    ))
    db.commit()
    monkeypatch.setattr(shopify_service, "verify_shopify_hmac", lambda _: True)
    monkeypatch.setattr(shopify_service, "exchange_access_token", lambda *_: _grant())
    monkeypatch.setattr(shopify_service, "encrypt_shopify_secret", lambda x: "enc:" + x)
    monkeypatch.setattr(shopify_service, "confirm_shopify_install_billing", lambda *a, **kw: None)
    monkeypatch.setattr(shopify_service, "ensure_shopify_order_webhooks", lambda _: None)
    from app.services import auto_fulfillment
    monkeypatch.setattr(auto_fulfillment, "requeue_store_auto_fulfillment", lambda *a: None)

    shopify_service.process_oauth_callback(
        db, {"state": "nonce", "code": "code", "shop": "example.myshopify.com"},
    )
    db.refresh(connection)
    assert connection.access_token_encrypted == "enc:access-expiring"
    assert connection.refresh_token_encrypted == "enc:rotating-refresh"
    assert connection.access_token_expires_at > datetime.utcnow()
    assert connection.refresh_token_expires_at > datetime.utcnow() + timedelta(days=80)


def test_public_install_stages_pair_and_claim_rotates_existing_connection(
    monkeypatch, installed_shop,
):
    db, store, connection = installed_shop
    db.add(ShopifyPendingInstall(
        state="public-state", shop_domain="example.myshopify.com",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
        state_used=False,
    ))
    db.commit()
    monkeypatch.setattr(shopify_public_install, "verify_shopify_hmac", lambda _: True)
    monkeypatch.setattr(shopify_public_install, "exchange_access_token", lambda *_: _grant())
    monkeypatch.setattr(shopify_public_install, "encrypt_shopify_secret", lambda x: "enc:" + x)
    monkeypatch.setattr(
        shopify_public_install.ShopifyGraphQLClient, "query",
        lambda *args: {"shop": {"myshopifyDomain": "example.myshopify.com"}},
    )
    monkeypatch.setattr(shopify_public_install, "ensure_shopify_order_webhooks", lambda _: None)
    secret = shopify_public_install.finish_public_install(db, {
        "state": "public-state", "code": "signed-code",
        "shop": "example.myshopify.com",
    })
    pending = db.query(ShopifyPendingInstall).filter_by(state="public-state").one()
    assert pending.token_encrypted == "enc:access-expiring"
    assert pending.refresh_token_encrypted == "enc:rotating-refresh"
    assert pending.access_token_expires_at > datetime.utcnow()
    assert pending.refresh_token_expires_at > datetime.utcnow()

    result = shopify_public_install.claim_install(
        db, secret=secret, membership=SimpleNamespace(organization_id=901),
        store=store,
    )
    assert result["connected"] is True
    db.refresh(connection)
    assert connection.access_token_encrypted == "enc:access-expiring"
    assert connection.refresh_token_encrypted == "enc:rotating-refresh"
    assert connection.access_token_expires_at > datetime.utcnow()
    db.refresh(pending)
    assert pending.token_encrypted is None
    assert pending.refresh_token_encrypted is None


def test_public_claim_refuses_legacy_unrefreshable_grant(monkeypatch, installed_shop):
    db, store, connection = installed_shop
    from app.services.shopify_service import ShopifyOAuthError
    secret = "s" * 40
    db.add(ShopifyPendingInstall(
        state="old-pending", shop_domain="example.myshopify.com",
        expires_at=datetime.utcnow() + timedelta(minutes=10),
        state_used=True, token_encrypted="unrefreshable",
        claim_hash=shopify_public_install._digest(secret),
        claim_expires_at=datetime.utcnow() + timedelta(minutes=10),
    ))
    db.commit()
    with pytest.raises(ShopifyOAuthError, match="SHOPIFY_EXPIRING_INSTALL_GRANT_REQUIRED"):
        shopify_public_install.claim_install(
            db, secret=secret, membership=SimpleNamespace(organization_id=901),
            store=store,
        )
    db.refresh(connection)
    assert connection.access_token_encrypted == "original-legacy"
