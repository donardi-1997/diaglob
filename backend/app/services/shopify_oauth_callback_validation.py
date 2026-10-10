"""Fail-closed validation of Shopify OAuth callback query parameters.

Starlette's QueryParams can contain duplicate keys. Converting it directly
to dict silently drops duplicates and permits disagreement between signature
verification, logging and downstream OAuth state/token use.
This module performs *structural validation* before HMAC verification; it is
not itself proof of Shopify origin, shop ownership or install authorization.
"""
from __future__ import annotations

MAX_CALLBACK_QUERY_BYTES = 4096
MAX_CALLBACK_PARAMETERS = 24
MAX_CALLBACK_VALUE_LENGTH = 2048
REQUIRED_CALLBACK_KEYS = frozenset({"code", "hmac", "shop", "state"})


class ShopifyCallbackQueryError(ValueError):
    """A callback has an ambiguous, missing or oversized query."""


def canonicalize_oauth_callback(
    pairs: list[tuple[str, str]],
    *,
    raw_query_bytes: int,
) -> dict[str, str]:
    """Validate and flatten only unique, bounded callback parameters.

    Shopify signs a message built from the received query parameters; keeping
    the full set of unique parameters prevents signature inconsistencies.
    A signed request must still pass verify_shopify_hmac and the one-time
    persisted state comparison before any access-token exchange.
    """
    if (
        type(raw_query_bytes) is not int
        or raw_query_bytes < 1
        or raw_query_bytes > MAX_CALLBACK_QUERY_BYTES
        or len(pairs) > MAX_CALLBACK_PARAMETERS
    ):
        raise ShopifyCallbackQueryError("INVALID_SHOPIFY_CALLBACK_QUERY")

    params: dict[str, str] = {}
    for key, value in pairs:
        if (
            type(key) is not str
            or not key
            or len(key) > 80
            or not key.isascii()
            or any(not (c.isalnum() or c in "_-") for c in key)
            or type(value) is not str
            or not value
            or len(value) > MAX_CALLBACK_VALUE_LENGTH
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ShopifyCallbackQueryError("INVALID_SHOPIFY_CALLBACK_QUERY")
        if key in params:
            raise ShopifyCallbackQueryError("DUPLICATE_SHOPIFY_CALLBACK_PARAMETER")
        params[key] = value

    if not REQUIRED_CALLBACK_KEYS.issubset(params):
        raise ShopifyCallbackQueryError("MISSING_SHOPIFY_CALLBACK_PARAMETER")
    return params
