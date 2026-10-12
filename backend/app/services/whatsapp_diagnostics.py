"""Read-only WhatsApp Cloud API diagnostics for a tenant-authorized store.

A stored WhatsApp token is NOT proof that the WABA owns the phone, or that
Meta routes webhooks to Diaglob. Never disclose tokens, phone numbers,
provider payloads, or Graph API error text in diagnostics.
"""
import os
import re

import httpx
from sqlalchemy.orm import Session

from ..models import WhatsAppConnection
from ..whatsapp_security import decrypt_whatsapp_secret


def _version() -> str:
    version = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v21.0")
    return version if re.fullmatch(r"v[0-9]{1,2}\\.[0-9]", version) else "v21.0"


def _graph_get(path: str, token: str, params: dict | None = None) -> dict:
    response = httpx.get(
        f"https://graph.facebook.com/{_version()}/{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=12,
        follow_redirects=False,
    )
    if response.status_code != 200:
        raise RuntimeError("META_API_DIAGNOSTIC_FAILED")
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("META_API_DIAGNOSTIC_FAILED") from exc
    if not isinstance(data, dict):
        raise RuntimeError("META_API_DIAGNOSTIC_FAILED")
    return data


def diagnose_whatsapp(db: Session, organization_id: int, store_id: int) -> dict:
    connection = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.organization_id == organization_id,
        WhatsAppConnection.store_id == store_id,
        WhatsAppConnection.status == "connected",
    ).first()
    result = {
        "configured": connection is not None,
        "provider_verified": False,
        "waba_subscription_verified": False,
        "webhook_signature_ready": bool(os.getenv("WHATSAPP_APP_SECRET")),
        "webhook_verify_configured": bool(os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")),
        "errors": [],
    }
    if connection is None:
        result["errors"].append("WHATSAPP_NOT_CONFIGURED")
        return result
    if not re.fullmatch(r"[0-9]{5,30}", connection.phone_number_id or "") or not re.fullmatch(
        r"[0-9]{5,30}", connection.business_account_id or ""
    ):
        result["errors"].append("WHATSAPP_INVALID_PROVIDER_IDS")
        return result

    try:
        access_token = decrypt_whatsapp_secret(connection.access_token_encrypted)
        # This verifies both the token and the WABA->phone ownership, not just
        # that the phone ID exists in any WhatsApp Business Account.
        phones = _graph_get(
            f"{connection.business_account_id}/phone_numbers",
            access_token,
            {"fields": "id,verified_name", "limit": 100},
        )
        numbers = phones.get("data")
        if not isinstance(numbers, list):
            raise RuntimeError("META_API_DIAGNOSTIC_FAILED")
        owned = any(
            isinstance(item, dict) and str(item.get("id")) == connection.phone_number_id
            for item in numbers
        )
        if not owned:
            result["errors"].append("WHATSAPP_PHONE_NOT_IN_WABA")
            return result
        result["provider_verified"] = True
        # If WABA has >100 numbers, absence on the first page is inconclusive.
        # We only verify positive identity; never claim a missing phone from
        # an incomplete provider page is definitely absent.
        app_id = (os.getenv("WHATSAPP_META_APP_ID") or "").strip()
        if not re.fullmatch(r"[0-9]{5,30}", app_id):
            result["errors"].append("WHATSAPP_META_APP_ID_NOT_CONFIGURED")
            return result
        subscriptions = _graph_get(
            f"{connection.business_account_id}/subscribed_apps",
            access_token,
        )
        subscribed = subscriptions.get("data")
        if not isinstance(subscribed, list):
            raise RuntimeError("META_API_DIAGNOSTIC_FAILED")
        result["waba_subscription_verified"] = any(
            isinstance(entry, dict)
            and (str(entry.get("id")) == app_id
                 or str((entry.get("whatsapp_business_api_data") or {}).get("id")) == app_id)
            for entry in subscribed
        )
        if not result["waba_subscription_verified"]:
            result["errors"].append("WHATSAPP_APP_NOT_SUBSCRIBED")
    except (httpx.HTTPError, RuntimeError, ValueError):
        result["errors"].append("WHATSAPP_PROVIDER_DIAGNOSTIC_UNAVAILABLE")
    if not result["webhook_signature_ready"]:
        result["errors"].append("WHATSAPP_APP_SECRET_NOT_CONFIGURED")
    return result
