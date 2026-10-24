"""Server-side Shopify offline access-token refresh with rotating refresh tokens.

Legacy non-expiring connections are unchanged. Expiring managed-install
credentials are refreshed and committed atomically before any Admin API call.
Neither token nor provider response is exposed in logs or browser responses.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import object_session

from .models import CommerceConnection
from .shopify_security import decrypt_shopify_secret, encrypt_shopify_secret
from .shopify_oauth import (
    SHOPIFY_SCOPES, effective_shopify_scopes, normalize_shop_domain,
)


class ShopifyTokenRefreshError(RuntimeError):
    pass


def connection_access_token(connection: CommerceConnection, *, decrypt_legacy=None) -> str:
    """Return a valid Shopify token, preserving legacy non-expiring callers."""
    if getattr(connection, "provider", "shopify") != "shopify" or getattr(connection, "status", "connected") != "connected":
        raise ShopifyTokenRefreshError("SHOPIFY_CONNECTION_NOT_ACTIVE")

    expiration = getattr(connection, "access_token_expires_at", None)
    if expiration is None:
        # Existing non-expiring connections and mock-injected legacy decryptors.
        decrypt = decrypt_legacy or decrypt_shopify_secret
        return decrypt(connection.access_token_encrypted or "")
    if not isinstance(expiration, datetime):
        raise ShopifyTokenRefreshError("SHOPIFY_EXPIRY_INVALID")
    if expiration > datetime.utcnow() + timedelta(minutes=2):
        return decrypt_shopify_secret(connection.access_token_encrypted or "")

    db = object_session(connection)
    if db is None:
        raise ShopifyTokenRefreshError("SHOPIFY_REFRESH_REQUIRES_DB_SESSION")

    locked = db.query(CommerceConnection).filter(
        CommerceConnection.id == connection.id,
        CommerceConnection.provider == "shopify",
        CommerceConnection.status == "connected",
    ).populate_existing().with_for_update().first()
    if locked is None:
        raise ShopifyTokenRefreshError("SHOPIFY_CONNECTION_REVOKED")

    if locked.access_token_expires_at and locked.access_token_expires_at > datetime.utcnow() + timedelta(minutes=2):
        return decrypt_shopify_secret(locked.access_token_encrypted or "")

    if (
        not locked.refresh_token_encrypted
        or not locked.refresh_token_expires_at
        or locked.refresh_token_expires_at <= datetime.utcnow()
    ):
        raise ShopifyTokenRefreshError("SHOPIFY_REFRESH_TOKEN_EXPIRED")

    client_id = os.getenv("SHOPIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SHOPIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise ShopifyTokenRefreshError("SHOPIFY_REFRESH_NOT_CONFIGURED")

    try:
        shop = normalize_shop_domain(locked.external_store_url)
        refresh = decrypt_shopify_secret(locked.refresh_token_encrypted)
        with httpx.Client(timeout=8, follow_redirects=False, trust_env=False) as client:
            response = client.post(
                f"https://{shop}/admin/oauth/access_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                },
            )
            response.raise_for_status()
            data = response.json()
        access = data.get("access_token") if isinstance(data, dict) else None
        next_refresh = data.get("refresh_token") if isinstance(data, dict) else None
        expires = data.get("expires_in") if isinstance(data, dict) else None
        refresh_expires = data.get("refresh_token_expires_in") if isinstance(data, dict) else None
        scopes = data.get("scope") if isinstance(data, dict) else None
        if (
            not isinstance(access, str) or not access or len(access) > 8192
            or not isinstance(next_refresh, str) or not next_refresh or len(next_refresh) > 8192
            or type(expires) is not int or expires < 300
            or type(refresh_expires) is not int or refresh_expires < 900
            or not isinstance(scopes, str)
            or not set(SHOPIFY_SCOPES.split(",")).issubset(effective_shopify_scopes(scopes))
        ):
            raise ShopifyTokenRefreshError("SHOPIFY_REFRESH_RESPONSE_INVALID")
        now = datetime.utcnow()
        locked.access_token_encrypted = encrypt_shopify_secret(access)
        locked.refresh_token_encrypted = encrypt_shopify_secret(next_refresh)
        locked.access_token_expires_at = now + timedelta(seconds=expires)
        locked.refresh_token_expires_at = now + timedelta(seconds=refresh_expires)
        locked.updated_at = now
        db.commit()
        return access
    except ShopifyTokenRefreshError:
        raise
    except (httpx.HTTPError, TypeError, ValueError, RuntimeError) as exc:
        raise ShopifyTokenRefreshError("SHOPIFY_TOKEN_REFRESH_FAILED") from exc
