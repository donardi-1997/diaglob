"""Shopify ID token validation must not authorize a DIAGLOB tenant."""
import os
import time
from unittest.mock import patch

import jwt
import pytest

from app.services.shopify_embedded_identity import (
    ShopifyIdTokenError, verify_shopify_id_token,
)

SECRET = "test-only-secret"
CLIENT = "test-shopify-client"


def make_token(**updates):
    now = int(time.time())
    claims = {
        "aud": CLIENT,
        "iss": "https://test-store.myshopify.com/admin",
        "dest": "https://test-store.myshopify.com",
        "sub": "12345",
        "iat": now,
        "nbf": now,
        "exp": now + 60,
        "jti": "token-1",
    }
    claims.update(updates)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def check(token):
    with patch.dict(os.environ, {"SHOPIFY_CLIENT_SECRET": SECRET, "SHOPIFY_CLIENT_ID": CLIENT}):
        return verify_shopify_id_token(token)


def test_valid_id_token_returns_only_shop_identity():
    assert check(make_token()) == {"shop": "test-store.myshopify.com", "subject": "12345"}


@pytest.mark.parametrize("updates", [
    {"aud": "another-app"},
    {"exp": 1},
    {"nbf": 9999999999},
    {"dest": "https://evil.example"},
    {"iss": "https://other-store.myshopify.com/admin"},
    {"sub": ""},
])
def test_rejects_bad_claims(updates):
    with pytest.raises(ShopifyIdTokenError):
        check(make_token(**updates))


def test_rejects_bad_signature():
    token = jwt.encode({
        "aud": CLIENT,
        "iss": "https://test-store.myshopify.com/admin",
        "dest": "https://test-store.myshopify.com",
        "sub": "12345",
        "iat": int(time.time()),
        "nbf": int(time.time()),
        "exp": int(time.time()) + 60,
        "jti": "bad",
    }, "wrong-secret", algorithm="HS256")
    with pytest.raises(ShopifyIdTokenError):
        check(token)
