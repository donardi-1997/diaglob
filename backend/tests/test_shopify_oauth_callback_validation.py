"""Shopify callback ambiguity/size guards before authorization-code exchange."""
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.shopify import shopify_oauth_callback
from app.services.shopify_oauth_callback_validation import (
    ShopifyCallbackQueryError,
    canonicalize_oauth_callback,
    MAX_CALLBACK_QUERY_BYTES,
)


def _pairs():
    return [
        ("shop", "test.myshopify.com"),
        ("state", "synthetic-state"),
        ("code", "synthetic-code"),
        ("hmac", "a" * 64),
        ("timestamp", "1790000000"),
        ("host", "YWRtaW4uc2hvcGlmeS5jb20vc3RvcmUvZm9v"),
    ]


def test_normal_valid_shopify_callback_preserves_all_signed_params():
    pairs = _pairs()
    result = canonicalize_oauth_callback(pairs, raw_query_bytes=300)
    assert result == dict(pairs)
    assert result["host"] == pairs[-1][1]


@pytest.mark.parametrize("extra", [
    ("hmac", "b" * 64), ("code", "other"), ("state", "other"),
    ("shop", "attacker.myshopify.com"), ("host", "other"),
])
def test_duplicate_keys_are_rejected_even_if_first_value_is_valid(extra):
    with pytest.raises(ShopifyCallbackQueryError, match="DUPLICATE"):
        canonicalize_oauth_callback(_pairs() + [extra], raw_query_bytes=350)


@pytest.mark.parametrize("malformed", [
    [("invalid\nkey", "value")],
    [("path[]", "value")],
    [("x", "value\r")],
    [("x", "")],
    [("x", "y" * 2049)],
])
def test_unsafe_keys_or_values_are_rejected(malformed):
    with pytest.raises(ShopifyCallbackQueryError, match="INVALID"):
        canonicalize_oauth_callback(_pairs() + malformed, raw_query_bytes=3500)


def test_missing_required_parameter_is_rejected():
    for required in ("hmac", "code", "shop", "state"):
        pairs = [(k, v) for k, v in _pairs() if k != required]
        with pytest.raises(ShopifyCallbackQueryError, match="MISSING"):
            canonicalize_oauth_callback(pairs, raw_query_bytes=300)


@pytest.mark.parametrize("length", [0, MAX_CALLBACK_QUERY_BYTES + 1, True])
def test_callback_query_size_limit_fails_closed(length):
    with pytest.raises(ShopifyCallbackQueryError, match="INVALID"):
        canonicalize_oauth_callback(_pairs(), raw_query_bytes=length)


def _request(raw_query: bytes):
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/shopify/callback",
        "query_string": raw_query,
        "headers": [],
        "server": ("testserver", 80),
        "scheme": "http",
    })


def test_duplicate_param_fails_before_service_and_token_exchange():
    query = (
        b"shop=test.myshopify.com&code=x&state=y&"
        b"hmac=aaa&hmac=bbb"
    )
    with patch("app.api.shopify.svc_process_oauth_callback") as svc:
        with pytest.raises(HTTPException) as exc:
            shopify_oauth_callback(_request(query), db=Mock())
    assert exc.value.status_code == 400
    assert exc.value.detail == "DUPLICATE_SHOPIFY_CALLBACK_PARAMETER"
    svc.assert_not_called()


def test_normal_params_are_forwarded_to_service_for_actual_hmac_verification():
    query = b"shop=test.myshopify.com&code=c&state=s&hmac=abc"
    with patch(
        "app.api.shopify.shopify_public_install.pending_state_exists",
        return_value=False,
    ), patch(
        "app.api.shopify.svc_process_oauth_callback",
        return_value="https://diaglob.tech?shopify=connected",
    ) as svc:
        response = shopify_oauth_callback(_request(query), db=Mock())
    assert response.status_code in (302, 307)
    svc.assert_called_once()
    params = svc.call_args.args[1]
    assert params == {
        "shop": "test.myshopify.com",
        "code": "c",
        "state": "s",
        "hmac": "abc",
    }


def test_oversized_raw_query_is_rejected_before_service_lookup():
    query = (
        b"shop=test.myshopify.com&code=c&state=s&hmac=abc&unused="
        + b"x" * (MAX_CALLBACK_QUERY_BYTES + 1)
    )
    with patch("app.api.shopify.svc_process_oauth_callback") as svc:
        with pytest.raises(HTTPException) as exc:
            shopify_oauth_callback(_request(query), db=Mock())
    assert exc.value.status_code == 400
    assert exc.value.detail == "INVALID_SHOPIFY_CALLBACK_QUERY"
    svc.assert_not_called()
