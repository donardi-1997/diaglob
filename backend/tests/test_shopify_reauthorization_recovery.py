"""Recover a Shopify connection after token expiry without widening tenant scope."""
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import CommerceConnection, Organization, ShopifyOAuthState, Store, User
from app.services.shopify_service import (
    ShopifyConnectionError,
    ShopifyNotFoundError,
    start_reauthorization,
)


@pytest.fixture
def installed_store():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    org = Organization(name="Shopify reconnect", slug="shopify-reconnect-fixture")
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Dev Test Shop",
        slug="dev-test-shop",
        country_code="US",
        currency="USD",
        timezone="America/New_York",
        default_language="en",
        active=True,
    )
    user = User(
        email="store-reconnect@example.com",
        name="Reconnect Tester",
        external_auth_id="reconnect-user-fixture",
    )
    db.add_all([store, user])
    db.flush()
    connection = CommerceConnection(
        organization_id=org.id,
        store_id=store.id,
        provider="shopify",
        external_store_url="diaglob-poc.myshopify.com",
        access_token_encrypted="encrypted-placeholder",
        status="error",
    )
    db.add(connection)
    db.commit()
    try:
        yield db, org, store, user, connection
    finally:
        db.close()
        engine.dispose()


def _reauthorize(db, org, store, user):
    with patch(
        "app.services.shopify_service.generate_oauth_state",
        return_value="test-state-not-a-real-secret",
    ), patch(
        "app.services.shopify_service.build_authorization_url",
        return_value="https://diaglob-poc.myshopify.com/admin/oauth/authorize",
    ) as oauth:
        result = start_reauthorization(db, org.id, store.id, user.id)
    return result, oauth


def test_auth_error_state_can_start_new_signed_oauth(installed_store):
    db, org, store, user, connection = installed_store
    result, oauth = _reauthorize(db, org, store, user)
    assert result["ok"] is True
    assert result["reauthorization"] is True
    assert result["shop_domain"] == connection.external_store_url
    assert connection.status == "error"
    oauth.assert_called_once_with(
        "diaglob-poc.myshopify.com", "test-state-not-a-real-secret"
    )
    states = db.query(ShopifyOAuthState).filter(
        ShopifyOAuthState.organization_id == org.id,
        ShopifyOAuthState.store_id == store.id,
    ).all()
    assert len(states) == 1
    assert states[0].used is False


@pytest.mark.parametrize("state", ["revoked", "disconnected"])
def test_revoked_or_disconnected_install_is_not_reused(installed_store, state):
    db, org, store, user, connection = installed_store
    connection.status = state
    db.commit()
    with pytest.raises(ShopifyNotFoundError):
        _reauthorize(db, org, store, user)
    assert db.query(ShopifyOAuthState).count() == 0


def test_inactive_store_cannot_reauthorize(installed_store):
    db, org, store, user, connection = installed_store
    store.active = False
    db.commit()
    with pytest.raises(ShopifyConnectionError):
        _reauthorize(db, org, store, user)
    assert db.query(ShopifyOAuthState).count() == 0


def test_cross_tenant_cannot_reauthorize_other_store(installed_store):
    db, org, store, user, connection = installed_store
    other = Organization(name="Other org", slug="reauth-other-org")
    db.add(other)
    db.commit()
    with pytest.raises(ShopifyNotFoundError):
        start_reauthorization(db, other.id, store.id, user.id)
    assert db.query(ShopifyOAuthState).count() == 0
