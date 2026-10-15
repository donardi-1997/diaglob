"""Synthetic tests for Shopify expiring offline refresh-token rotation."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CommerceConnection, Organization, Store
from app.shopify_token_lifecycle import ShopifyTokenRefreshError, connection_access_token

ALL_SCOPES = "read_products,read_inventory,read_customers,read_orders,write_orders,write_draft_orders,read_merchant_managed_fulfillment_orders,write_merchant_managed_fulfillment_orders"


@pytest.fixture
def sample(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "fixture-app")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "fixture-secret")
    with Session(engine) as db:
        org = Organization(id=101, name="Refresh Test", slug="refresh-test")
        store = Store(id=102, organization_id=101, name="Test", slug="refresh-test-store",
                      country_code="CO", currency="COP", timezone="America/Bogota", active=True, deleted=False)
        connection = CommerceConnection(
            id=103, organization_id=101, store_id=102, provider="shopify",
            external_store_url="diaglob-poc.myshopify.com",
            access_token_encrypted="old-access", refresh_token_encrypted="old-refresh",
            access_token_expires_at=datetime.utcnow() - timedelta(seconds=2),
            refresh_token_expires_at=datetime.utcnow() + timedelta(days=1),
            status="connected", scopes=ALL_SCOPES,
        )
        db.add_all([org,store,connection])
        db.commit()
        yield db, connection
    engine.dispose()


@patch("app.shopify_token_lifecycle.encrypt_shopify_secret", side_effect=lambda s: "encrypt:" + s)
@patch("app.shopify_token_lifecycle.decrypt_shopify_secret", side_effect=lambda s: s)
@patch("app.shopify_token_lifecycle.httpx.Client")
def test_refresh_rotates_both_tokens_and_persists(client, decrypt, encrypt, sample):
    db, connection = sample
    provider = client.return_value.__enter__.return_value
    provider.post.return_value.json.return_value = {
        "access_token": "next-access", "refresh_token": "next-refresh",
        "expires_in": 3600, "refresh_token_expires_in": 7776000,
        "scope": ALL_SCOPES,
    }
    token = connection_access_token(connection)
    assert token == "next-access"
    db.refresh(connection)
    assert connection.access_token_encrypted == "encrypt:next-access"
    assert connection.refresh_token_encrypted == "encrypt:next-refresh"
    assert connection.access_token_expires_at > datetime.utcnow() + timedelta(minutes=30)
    assert connection_access_token(connection) == "encrypt:next-access"
    provider.post.assert_called_once()
    assert provider.post.call_args.kwargs["data"]["grant_type"] == "refresh_token"


@patch("app.shopify_token_lifecycle.httpx.Client")
def test_expired_refresh_denies_without_network(client, sample):
    db, connection = sample
    connection.refresh_token_expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(ShopifyTokenRefreshError, match="EXPIRED"):
        connection_access_token(connection)
    client.assert_not_called()


@patch("app.shopify_token_lifecycle.decrypt_shopify_secret", side_effect=lambda s: s)
def test_non_expiring_legacy_connection_unchanged(decrypt, sample):
    db, connection = sample
    connection.access_token_expires_at = None
    connection.refresh_token_encrypted = None
    db.commit()
    assert connection_access_token(connection) == "old-access"
