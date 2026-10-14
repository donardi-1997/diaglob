"""Verification of Shopify App Bridge ID tokens; never grants Diaglob tenant access."""
from __future__ import annotations

import os
from urllib.parse import urlparse

import jwt


class ShopifyIdTokenError(ValueError):
    pass


def verify_shopify_id_token(token: str) -> dict[str, str]:
    secret = os.getenv("SHOPIFY_CLIENT_SECRET", "").strip()
    client_id = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
    if not secret or not client_id:
        raise ShopifyIdTokenError("SHOPIFY_EMBEDDED_NOT_CONFIGURED")
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=client_id,
            options={"require": ["aud", "iss", "dest", "sub", "iat", "nbf", "exp", "jti"]},
            leeway=5,
        )
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise ShopifyIdTokenError("SHOPIFY_INVALID_ID_TOKEN") from exc

    dest, iss = claims.get("dest"), claims.get("iss")
    if not isinstance(dest, str) or not isinstance(iss, str):
        raise ShopifyIdTokenError("SHOPIFY_INVALID_SHOP")
    destination = urlparse(dest)
    issuer = urlparse(iss)
    if (
        destination.scheme != "https"
        or issuer.scheme != "https"
        or not destination.hostname
        or not destination.hostname.endswith(".myshopify.com")
        or destination.username or destination.password
        or destination.port is not None
        or destination.path not in ("", "/")
        or destination.query or destination.fragment
        or issuer.hostname != destination.hostname
        or issuer.path.rstrip("/") != "/admin"
        or issuer.query or issuer.fragment
    ):
        raise ShopifyIdTokenError("SHOPIFY_INVALID_SHOP")
    if not isinstance(claims["sub"], str) or not claims["sub"]:
        raise ShopifyIdTokenError("SHOPIFY_INVALID_SUBJECT")
    return {"shop": destination.hostname.lower(), "subject": claims["sub"]}
