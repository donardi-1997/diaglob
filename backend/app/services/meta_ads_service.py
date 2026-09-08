"""Meta Ads service.

Application orchestration for Meta Ads connection.
Does NOT own HTTP requests (client does).
Does NOT own analytics formulas (analytics service does).
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from ..integrations.meta_ads.client import (
    MetaAdsError,
    MetaAuthError,
    get_ad_account,
    get_me,
    list_ad_accounts,
)
from ..meta_ads_security import encrypt_secret, decrypt_secret
from ..models import MetaAdsConnection, Store

logger = logging.getLogger(__name__)

META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_REDIRECT_URI = os.getenv("META_ADS_REDIRECT_URI", "")


class MetaAdsNotFoundError(Exception):
    pass


class MetaAdsConnectionError(Exception):
    pass


def get_oauth_url(
    organization_id: int,
    store_id: int,
    user_id: int,
) -> dict:
    """Generate Meta Ads OAuth URL with state."""
    state = secrets.token_urlsafe(32)

    scopes = "ads_read,ads_management,business_management"
    auth_url = (
        f"https://www.facebook.com/{'v21.0'}/dialog/oauth?"
        + urlencode({
            "client_id": META_APP_ID,
            "redirect_uri": META_REDIRECT_URI,
            "scope": scopes,
            "state": state,
            "response_type": "code",
        })
    )

    return {
        "authorization_url": auth_url,
        "state": state,
    }


def process_oauth_callback(
    db: Session,
    code: str,
    organization_id: int,
    store_id: int,
) -> dict:
    """Exchange OAuth code for access token and discover accounts."""
    import httpx

    token_url = f"https://graph.facebook.com/v21.0/oauth/access_token"
    params = {
        "client_id": META_APP_ID,
        "client_secret": META_APP_SECRET,
        "redirect_uri": META_REDIRECT_URI,
        "code": code,
    }

    try:
        response = httpx.get(token_url, params=params, timeout=30)
        response.raise_for_status()
        token_data = response.json()
    except Exception as exc:
        raise MetaAdsConnectionError(f"Token exchange failed: {exc}")

    access_token = token_data.get("access_token")
    if not access_token:
        raise MetaAdsConnectionError("No access token received")

    # Get user info
    try:
        user_info = get_me(access_token)
    except MetaAdsError as exc:
        raise MetaAdsConnectionError(f"Failed to get user info: {exc}")

    # List ad accounts
    try:
        accounts = list_ad_accounts(access_token)
    except MetaAdsError as exc:
        raise MetaAdsConnectionError(f"Failed to list ad accounts: {exc}")

    # Encrypt token
    encrypted_token = encrypt_secret(access_token)

    return {
        "encrypted_token": encrypted_token,
        "user_id": user_info.get("id"),
        "accounts": [
            {
                "id": acc["id"],
                "name": acc.get("name", ""),
                "currency": acc.get("currency", "USD"),
                "timezone": acc.get("timezone_id", ""),
                "status": acc.get("account_status"),
            }
            for acc in accounts
        ],
    }


def connect_account(
    db: Session,
    organization_id: int,
    store_id: int,
    encrypted_token: str,
    account_id: str,
    account_name: str,
    account_currency: str,
    account_timezone: str,
) -> dict:
    """Create Meta Ads connection for a store."""
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if not store:
        raise MetaAdsNotFoundError("Store not found")

    existing = (
        db.query(MetaAdsConnection)
        .filter(MetaAdsConnection.store_id == store_id)
        .first()
    )
    if existing:
        raise MetaAdsConnectionError("Meta Ads already connected for this store")

    now = datetime.utcnow()

    connection = MetaAdsConnection(
        organization_id=organization_id,
        store_id=store_id,
        provider="meta_ads",
        external_account_id=account_id,
        external_account_name=account_name,
        account_currency=account_currency,
        account_timezone=account_timezone,
        access_token_encrypted=encrypted_token,
        status="connected",
        connected_at=now,
        created_at=now,
        updated_at=now,
    )

    db.add(connection)
    db.commit()
    db.refresh(connection)

    return {
        "ok": True,
        "connected": True,
        "account_id": account_id,
        "account_name": account_name,
        "currency": account_currency,
    }


def disconnect(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    """Remove Meta Ads connection."""
    connection = (
        db.query(MetaAdsConnection)
        .filter(
            MetaAdsConnection.store_id == store_id,
            MetaAdsConnection.organization_id == organization_id,
        )
        .first()
    )
    if not connection:
        raise MetaAdsNotFoundError("Meta Ads not connected")

    db.delete(connection)
    db.commit()

    return {"ok": True, "connected": False, "store_id": store_id}


def get_connection_status(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    """Get Meta Ads connection status."""
    connection = (
        db.query(MetaAdsConnection)
        .filter(
            MetaAdsConnection.store_id == store_id,
            MetaAdsConnection.organization_id == organization_id,
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "account_id": None,
            "account_name": None,
            "currency": None,
            "timezone": None,
            "last_sync_at": None,
            "last_error": None,
        }

    return {
        "connected": connection.status == "connected",
        "status": connection.status,
        "account_id": connection.external_account_id,
        "account_name": connection.external_account_name,
        "currency": connection.account_currency,
        "timezone": connection.account_timezone,
        "connected_at": (
            connection.connected_at.isoformat() + "Z"
            if connection.connected_at
            else None
        ),
        "last_sync_at": (
            connection.last_sync_at.isoformat() + "Z"
            if connection.last_sync_at
            else None
        ),
        "last_error": connection.last_error,
    }
