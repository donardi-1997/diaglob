"""OAuth state replay/race guards using a real SQLite transactional session."""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ShopifyOAuthState
from app.services.shopify_service import (
    ShopifyOAuthError,
    ShopifyProviderError,
    _claim_shopify_oauth_state,
    process_oauth_callback,
)


@pytest.fixture
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        state = ShopifyOAuthState(
            state="unique-shopify-state",
            organization_id=7,
            store_id=8,
            user_id=9,
            shop_domain="valid.myshopify.com",
            used=False,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )
        db.add(state)
        db.commit()
        yield db, state
    engine.dispose()


def test_state_is_committed_as_used_before_any_token_exchange(sandbox):
    db, state = sandbox
    _claim_shopify_oauth_state(
        db, state, normalized_shop="valid.myshopify.com"
    )
    db.expire_all()
    assert db.query(ShopifyOAuthState).one().used is True
    with pytest.raises(ShopifyOAuthError, match="already used"):
        _claim_shopify_oauth_state(
            db, state, normalized_shop="valid.myshopify.com"
        )


def test_wrong_shop_cannot_claim_or_consume_state(sandbox):
    db, state = sandbox
    with pytest.raises(ShopifyOAuthError, match="already used"):
        _claim_shopify_oauth_state(
            db, state, normalized_shop="other.myshopify.com"
        )
    db.expire_all()
    assert db.query(ShopifyOAuthState).one().used is False


def test_expired_state_cannot_be_claimed(sandbox):
    db, state = sandbox
    state.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(ShopifyOAuthError, match="already used"):
        _claim_shopify_oauth_state(
            db, state, normalized_shop="valid.myshopify.com"
        )
    db.expire_all()
    assert db.query(ShopifyOAuthState).one().used is False


def test_replayed_callback_never_reaches_shopify_token_api(sandbox):
    db, state = sandbox
    _claim_shopify_oauth_state(db, state, normalized_shop="valid.myshopify.com")
    params = {
        "shop": "valid.myshopify.com",
        "state": "unique-shopify-state",
        "code": "test-code",
        "hmac": "test-hmac",
    }
    with patch(
        "app.services.shopify_service.verify_shopify_hmac", return_value=True
    ), patch("app.services.shopify_service.exchange_access_token") as exchange:
        with pytest.raises(ShopifyOAuthError, match="already used"):
            process_oauth_callback(db, params)
    exchange.assert_not_called()


def test_provider_error_still_consumes_oauth_state_to_prevent_replay(sandbox):
    db, _ = sandbox
    params = {
        "shop": "valid.myshopify.com",
        "state": "unique-shopify-state",
        "code": "test-code",
        "hmac": "test-hmac",
    }
    with patch(
        "app.services.shopify_service.verify_shopify_hmac", return_value=True
    ), patch(
        "app.services.shopify_service.exchange_access_token",
        side_effect=RuntimeError("Synthetic temporary failure"),
    ) as exchange:
        with pytest.raises(ShopifyProviderError):
            process_oauth_callback(db, params)
    exchange.assert_called_once_with("valid.myshopify.com", "test-code")
    db.expire_all()
    assert db.query(ShopifyOAuthState).one().used is True
