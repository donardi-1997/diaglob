"""Meta Ads provider client.

Handles Meta Graph API HTTP requests.
Owns: base URL, auth, pagination, timeouts, provider error normalization.
Does NOT own: business logic, analytics formulas, billing.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

META_GRAPH_VERSION = os.getenv("META_GRAPH_API_VERSION", "v21.0")
META_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"


class MetaAdsError(Exception):
    """Base Meta Ads error."""
    def __init__(self, message: str, code: str = "META_UNKNOWN_ERROR"):
        super().__init__(message)
        self.code = code


class MetaAuthError(MetaAdsError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, "META_AUTH_REQUIRED")


class MetaPermissionError(MetaAdsError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, "META_PERMISSION_DENIED")


class MetaRateLimitError(MetaAdsError):
    def __init__(self, message: str = "Rate limited"):
        super().__init__(message, "META_RATE_LIMITED")


class MetaTemporaryError(MetaAdsError):
    def __init__(self, message: str = "Temporary error"):
        super().__init__(message, "META_TEMPORARY_ERROR")


def _handle_meta_error(response: httpx.Response):
    """Normalize Meta API errors."""
    try:
        data = response.json()
        error = data.get("error", {})
        message = error.get("message", "Unknown Meta API error")
        code = error.get("code", 0)
    except Exception:
        message = f"Meta API error: {response.status_code}"
        code = 0

    if response.status_code == 401:
        raise MetaAuthError(message)
    elif response.status_code == 403:
        raise MetaPermissionError(message)
    elif response.status_code == 429:
        raise MetaRateLimitError(message)
    elif response.status_code >= 500:
        raise MetaTemporaryError(message)
    else:
        raise MetaAdsError(message, "META_INVALID_REQUEST")


def _request(
    method: str,
    path: str,
    access_token: str,
    params: dict | None = None,
    timeout: int = 30,
) -> dict:
    """Make a Meta Graph API request."""
    url = f"{META_GRAPH_BASE}{path}"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method, url, headers=headers, params=params
            )
    except httpx.TimeoutException:
        raise MetaTemporaryError("Meta API request timed out")
    except httpx.RequestError as exc:
        raise MetaTemporaryError(f"Meta API request failed: {exc}")

    if response.status_code >= 400:
        _handle_meta_error(response)

    return response.json()


def get_me(access_token: str) -> dict:
    """Get current user info."""
    return _request("GET", "/me", access_token)


def list_ad_accounts(access_token: str) -> list[dict]:
    """List accessible ad accounts."""
    data = _request(
        "GET",
        "/me/adaccounts",
        access_token,
        params={"fields": "id,name,currency,timezone_id,account_status"},
    )
    return data.get("data", [])


def get_ad_account(access_token: str, account_id: str) -> dict:
    """Get ad account details."""
    return _request(
        "GET",
        f"/{account_id}",
        access_token,
        params={"fields": "id,name,currency,timezone_id,account_status"},
    )


def get_insights(
    access_token: str,
    account_id: str,
    date_preset: str | None = None,
    time_range: dict | None = None,
    fields: list[str] | None = None,
) -> list[dict]:
    """Get Insights for an ad account.

    Args:
        access_token: OAuth access token
        account_id: Meta ad account ID
        date_preset: e.g., 'today', 'yesterday', 'last_7d', 'last_30d'
        time_range: {'since': 'YYYY-MM-DD', 'until': 'YYYY-MM-DD'}
        fields: list of metric names
    """
    if fields is None:
        fields = [
            "spend",
            "impressions",
            "clicks",
            "reach",
            "ctr",
            "cpc",
            "cpm",
        ]

    params: dict = {
        "fields": ",".join(fields),
        "level": "account",
    }

    if date_preset:
        params["date_preset"] = date_preset
    elif time_range:
        params["time_range"] = str(time_range).replace("'", '"')

    data = _request(
        "GET",
        f"/{account_id}/insights",
        access_token,
        params=params,
    )

    return data.get("data", [])


def get_campaign_insights(
    access_token: str,
    account_id: str,
    date_preset: str | None = None,
    time_range: dict | None = None,
) -> list[dict]:
    """Get per-campaign Insights."""
    fields = [
        "campaign_id",
        "campaign_name",
        "spend",
        "impressions",
        "clicks",
        "reach",
        "ctr",
        "cpc",
        "cpm",
    ]

    params: dict = {
        "fields": ",".join(fields),
        "level": "campaign",
    }

    if date_preset:
        params["date_preset"] = date_preset
    elif time_range:
        params["time_range"] = str(time_range).replace("'", '"')

    data = _request(
        "GET",
        f"/{account_id}/insights",
        access_token,
        params=params,
    )

    return data.get("data", [])


def parse_insights_row(row: dict) -> dict:
    """Parse an Insights row into safe numeric values."""
    def safe_decimal(value, default="0"):
        if value is None:
            return Decimal(default)
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    return {
        "spend": safe_decimal(row.get("spend")),
        "impressions": int(row.get("impressions", 0) or 0),
        "clicks": int(row.get("clicks", 0) or 0),
        "reach": int(row.get("reach", 0) or 0),
        "ctr": safe_decimal(row.get("ctr")),
        "cpc": safe_decimal(row.get("cpc")),
        "cpm": safe_decimal(row.get("cpm")),
    }
