"""Synthetic Shopify OAuth, signature, scope and credential boundary matrix.

No network, Shopify merchant sessions, store mutations or production secrets.
"""
from datetime import datetime, timedelta
import hashlib
import hmac

from cryptography.fernet import Fernet
import httpx
import pytest

from app.shopify_oauth import (
    SHOPIFY_SCOPES, build_authorization_url, effective_shopify_scopes,
    exchange_access_token, normalize_shop_domain, verify_shopify_hmac,
)
from app.shopify_security import decrypt_shopify_secret, encrypt_shopify_secret


@pytest.fixture
def oauth_env(monkeypatch):
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "synthetic-app")
    monkeypatch.setenv("SHOPIFY_CLIENT_SECRET", "synthetic-signing-secret")
    monkeypatch.setenv("SHOPIFY_REDIRECT_URI", "https://unit.invalid/shopify/callback")


@pytest.mark.parametrize("shop,expected", [
    ("demo.myshopify.com", "demo.myshopify.com"),
    (" DEMO.MYSHOPIFY.COM ", "demo.myshopify.com"),
    ("https://demo.myshopify.com/", "demo.myshopify.com"),
    ("http://DEMO.myshopify.com/", "demo.myshopify.com"),
])
def test_normalized_shop_domains_are_canonical(shop, expected):
    assert normalize_shop_domain(shop) == expected


@pytest.mark.parametrize("shop", [
    "", "shopify.com", "demo.com", "myshopify.com", ".myshopify.com",
    "demo..myshopify.com", "demo.myshopify.com.evil.invalid",
    "demo.myshopify.com/path", "https://demo.myshopify.com/admin",
    "https://user:password@demo.myshopify.com",
    "https://demo.myshopify.com:444",
    "demo.myshopify.com?token=secret",
    "demo.myshopify.com#fragment", "demo.myshopify.com\nHost: attacker",
    "démø.myshopify.com", "demo.myshopify.com@attacker.invalid",
])
def test_invalid_shop_domains_fail_before_authorization(shop):
    with pytest.raises(ValueError, match="Invalid Shopify shop domain"):
        normalize_shop_domain(shop)


def test_authorization_url_uses_only_canonical_shop_and_required_oauth_fields(oauth_env):
    from urllib.parse import parse_qs, urlparse

    result = build_authorization_url(" DEMO.myshopify.com ", "synthetic-state")
    parsed = urlparse(result)
    params = parse_qs(parsed.query)
    assert parsed.netloc == "demo.myshopify.com"
    assert parsed.scheme == "https"
    assert parsed.path == "/admin/oauth/authorize"
    assert params == {
        "client_id": ["synthetic-app"],
        "redirect_uri": ["https://unit.invalid/shopify/callback"],
        "scope": [SHOPIFY_SCOPES],
        "state": ["synthetic-state"],
    }


def _signed_query(secret="synthetic-signing-secret"):
    values = {
        "shop": "demo.myshopify.com", "state": "synthetic-state",
        "timestamp": "1690000000", "signature": "legacy-signature",
    }
    message = "&".join(
        f"{key}={values[key]}" for key in sorted(values) if key != "signature"
    )
    digest = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {**values, "hmac": digest}


def test_valid_shopify_hmac_and_legacy_signature_exclusion(oauth_env):
    query = _signed_query()
    assert verify_shopify_hmac(query) is True
    assert verify_shopify_hmac({**query, "signature": "changed-not-signed"}) is True


@pytest.mark.parametrize("mutation", [
    {"shop": "other.myshopify.com"}, {"state": "replayed-state"},
    {"timestamp": "1690000001"}, {"hmac": "0" * 64},
    {"hmac": ""}, {"hmac": None},
])
def test_signed_callback_tampering_is_rejected(oauth_env, mutation):
    assert verify_shopify_hmac({**_signed_query(), **mutation}) is False


def test_no_hmac_never_authorizes_callback(oauth_env):
    assert verify_shopify_hmac({"shop": "demo.myshopify.com"}) is False


def test_implicit_scopes_require_matching_write_grants():
    assert {"read_orders", "read_draft_orders", "read_merchant_managed_fulfillment_orders"}.issubset(
        effective_shopify_scopes(
            "write_orders,write_draft_orders,write_merchant_managed_fulfillment_orders"
        )
    )
    assert "read_orders" not in effective_shopify_scopes("read_products")
    assert "read_customers" not in effective_shopify_scopes("write_orders")
    assert "write_orders" not in effective_shopify_scopes("read_orders")
    assert effective_shopify_scopes("read_products, read_products, ,") == {"read_products"}


@pytest.fixture
def grant_response():
    return {
        "access_token": "synthetic-access-token",
        "refresh_token": "synthetic-refresh-token",
        "expires_in": 3600,
        "refresh_token_expires_in": 7776000,
        "scope": SHOPIFY_SCOPES,
    }


def _mock_token_response(monkeypatch, payload, status=200):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        response_args = (
            {"content": b"null"} if payload is None
            else {"json": payload}
        )
        return httpx.Response(
            status, request=httpx.Request("POST", url), **response_args,
        )

    monkeypatch.setattr("app.shopify_oauth.httpx.post", fake_post)
    return calls


def test_expiring_token_exchange_checks_destination_and_transport(oauth_env, monkeypatch, grant_response):
    calls = _mock_token_response(monkeypatch, grant_response)
    before = datetime.utcnow()
    grant = exchange_access_token("DEMO.myshopify.com", "synthetic-authorization-code")
    assert grant.access_token == "synthetic-access-token"
    assert grant.refresh_token == "synthetic-refresh-token"
    assert before + timedelta(minutes=50) < grant.access_token_expires_at
    assert before + timedelta(days=80) < grant.refresh_token_expires_at
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://demo.myshopify.com/admin/oauth/access_token"
    assert kwargs["data"]["expiring"] == "1"
    assert kwargs["data"]["code"] == "synthetic-authorization-code"
    assert kwargs["follow_redirects"] is False
    assert kwargs["timeout"] == 20


@pytest.mark.parametrize("change", [
    {"access_token": ""}, {"access_token": 5},
    {"refresh_token": ""}, {"refresh_token": False},
    {"access_token": "x" * 8193}, {"refresh_token": "x" * 8193},
    {"expires_in": 299}, {"expires_in": True}, {"expires_in": "3600"},
    {"refresh_token_expires_in": 899}, {"refresh_token_expires_in": False},
    {"refresh_token_expires_in": 4.5},
])
def test_incomplete_token_pair_is_rejected(oauth_env, monkeypatch, grant_response, change):
    _mock_token_response(monkeypatch, {**grant_response, **change})
    with pytest.raises(RuntimeError, match="^SHOPIFY_EXPIRING_OFFLINE_TOKEN_REQUIRED$"):
        exchange_access_token("demo.myshopify.com", "synthetic-code")


@pytest.mark.parametrize("scope", [
    "", "read_products", "read_products,write_draft_orders",
    "write_orders,write_draft_orders,read_inventory",
    None, ["read_products"], 1234,
])
def test_missing_shopify_scopes_fail_closed(oauth_env, monkeypatch, grant_response, scope):
    _mock_token_response(monkeypatch, {**grant_response, "scope": scope})
    with pytest.raises(RuntimeError, match="^SHOPIFY_OAUTH_REQUIRED_SCOPES_MISSING$"):
        exchange_access_token("demo.myshopify.com", "synthetic-code")


@pytest.mark.parametrize("provider_payload", [
    None, [], False, "not-json-object", {"error": "invalid_grant"},
])
def test_non_object_provider_grants_never_return_credentials(
    oauth_env, monkeypatch, provider_payload,
):
    _mock_token_response(monkeypatch, provider_payload)
    with pytest.raises(RuntimeError, match="SHOPIFY_EXPIRING_OFFLINE_TOKEN_REQUIRED"):
        exchange_access_token("demo.myshopify.com", "synthetic-code")


@pytest.mark.parametrize("http_status", [400, 401, 403, 429, 500, 503])
def test_provider_http_errors_are_sanitized(oauth_env, monkeypatch, http_status):
    _mock_token_response(monkeypatch, {"error": "secret-from-provider"}, status=http_status)
    with pytest.raises(RuntimeError, match="^SHOPIFY_OAUTH_CODE_EXCHANGE_FAILED$") as exc:
        exchange_access_token("demo.myshopify.com", "synthetic-code")
    assert "secret-from-provider" not in str(exc.value)


def test_shopify_credential_encryption_roundtrip_and_tampering(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    plaintext = "synthetic-shopify-offline-token"
    encrypted_one = encrypt_shopify_secret(plaintext)
    encrypted_two = encrypt_shopify_secret(plaintext)
    assert encrypted_one != plaintext
    assert encrypted_one != encrypted_two
    assert decrypt_shopify_secret(encrypted_one) == plaintext

    with pytest.raises(RuntimeError, match="Unable to decrypt Shopify secret"):
        decrypt_shopify_secret(encrypted_one[:-4] + "AAAA")


def test_invalid_or_missing_shopify_encryption_keys_fail_closed(monkeypatch):
    monkeypatch.delenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="is not configured"):
        encrypt_shopify_secret("synthetic")
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", "invalid-key")
    with pytest.raises(RuntimeError, match="is invalid"):
        encrypt_shopify_secret("synthetic")


@pytest.mark.parametrize("secret", ["", None])
def test_blank_shopify_secrets_are_rejected_before_crypto(secret):
    with pytest.raises(ValueError):
        encrypt_shopify_secret(secret)
    with pytest.raises(ValueError):
        decrypt_shopify_secret(secret)
