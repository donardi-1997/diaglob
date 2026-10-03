"""Diaglob customer-acquisition attribution and Meta Conversions API delivery.

This service is for Diaglob's own marketing funnel. It is deliberately separate from
merchant Meta Ads connections under app.services.meta_ads_service.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from ..model_domains.marketing import (
    MarketingFunnelEvent,
    MarketingRegistrationAttribution,
)
from ..models import User

logger = logging.getLogger(__name__)

_SUPPORTED_META_FUNNEL_EVENTS = {
    "CompleteRegistration",
    "StartTrial",
    "Subscribe",
}
_ALLOWED_TOUCH_FIELDS = {
    "source",
    "medium",
    "campaign",
    "content",
    "term",
    "fbclid",
    "ttclid",
    "landing_path",
    "captured_at",
}


def _clean(value, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _normalize_touch(value: dict | None) -> dict | None:
    if not isinstance(value, dict):
        return None

    cleaned: dict[str, str] = {}
    limits = {
        "source": 120,
        "medium": 120,
        "campaign": 255,
        "content": 255,
        "term": 255,
        "fbclid": 500,
        "ttclid": 500,
        "landing_path": 2048,
        "captured_at": 80,
    }
    for key in _ALLOWED_TOUCH_FIELDS:
        cleaned_value = _clean(value.get(key), limits[key])
        if cleaned_value is not None:
            cleaned[key] = cleaned_value
    return cleaned or None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _captured_at_millis(touch: dict | None) -> int:
    raw = (touch or {}).get("captured_at")
    if raw:
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return int(parsed.timestamp() * 1000)
        except (TypeError, ValueError):
            pass
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _fallback_fbc(touch: dict | None) -> str | None:
    fbclid = _clean((touch or {}).get("fbclid"), 500)
    if not fbclid:
        return None
    return f"fb.1.{_captured_at_millis(touch)}.{fbclid}"


def _event_time_seconds(value: datetime | None) -> int | None:
    if value is None:
        return None
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return int(normalized.timestamp())


def build_meta_conversion_event(
    *,
    event_id: str,
    email: str,
    user_id: int,
    event_source_url: str | None,
    first_touch: dict | None,
    last_touch: dict | None,
    fbp: str | None,
    fbc: str | None,
    client_ip: str | None,
    client_user_agent: str | None,
    event_name: str = "CompleteRegistration",
    event_time: int | None = None,
    custom_data: dict | None = None,
) -> dict:
    """Build a Meta CAPI funnel event without persisting raw matching data."""
    if event_name not in _SUPPORTED_META_FUNNEL_EVENTS:
        raise ValueError(f"Unsupported Meta funnel event: {event_name}")

    user_data: dict[str, object] = {
        "em": [_sha256(email.strip().lower())],
        "external_id": [_sha256(str(user_id))],
    }

    normalized_fbp = _clean(fbp, 500)
    normalized_fbc = (
        _clean(fbc, 500)
        or _fallback_fbc(last_touch)
        or _fallback_fbc(first_touch)
    )
    if normalized_fbp:
        user_data["fbp"] = normalized_fbp
    if normalized_fbc:
        user_data["fbc"] = normalized_fbc
    if client_ip:
        user_data["client_ip_address"] = client_ip
    if client_user_agent:
        user_data["client_user_agent"] = client_user_agent

    event: dict[str, object] = {
        "event_name": event_name,
        "event_time": event_time or int(datetime.now(timezone.utc).timestamp()),
        "event_id": event_id,
        "action_source": "website",
        "user_data": user_data,
    }
    if event_source_url:
        event["event_source_url"] = event_source_url
    if custom_data:
        event["custom_data"] = custom_data
    return event


def _send_meta_conversion(event: dict) -> tuple[str, str | None]:
    pixel_id = os.getenv("META_PIXEL_ID", "").strip()
    access_token = os.getenv("META_CONVERSIONS_API_ACCESS_TOKEN", "").strip()
    if not pixel_id or not access_token:
        return "disabled", None

    graph_version = (
        os.getenv("META_GRAPH_API_VERSION", "v21.0").strip()
        or "v21.0"
    )
    url = f"https://graph.facebook.com/{graph_version}/{pixel_id}/events"
    payload: dict[str, object] = {"data": [event]}
    test_event_code = os.getenv("META_CAPI_TEST_EVENT_CODE", "").strip()
    if test_event_code:
        payload["test_event_code"] = test_event_code

    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(
                url,
                params={"access_token": access_token},
                json=payload,
            )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message")
            except Exception:
                detail = None
            return "failed", _clean(
                detail or f"HTTP {response.status_code}",
                500,
            )
    except httpx.HTTPError as exc:
        return "failed", _clean(str(exc), 500)

    return "delivered", None


def _event_row_from_attribution(
    *,
    attribution: MarketingRegistrationAttribution,
    event_key: str,
    event_name: str,
    provider_event_id: str | None = None,
    value: Decimal | None = None,
    currency: str | None = None,
    event_data: dict | None = None,
    occurred_at: datetime | None = None,
) -> MarketingFunnelEvent:
    return MarketingFunnelEvent(
        registration_attribution_id=attribution.id,
        organization_id=attribution.organization_id,
        user_id=attribution.user_id,
        event_key=event_key,
        event_name=event_name,
        provider_event_id=_clean(provider_event_id, 255),
        source=attribution.source,
        medium=attribution.medium,
        campaign=attribution.campaign,
        content=attribution.content,
        value=value,
        currency=_clean(currency, 10),
        event_data=event_data,
        meta_delivery_status="pending",
        occurred_at=occurred_at or datetime.utcnow(),
    )


def record_registration_conversion(
    db: Session,
    *,
    organization_id: int,
    user_id: int,
    email: str,
    marketing_context: dict | None,
    client_ip: str | None = None,
    client_user_agent: str | None = None,
) -> dict:
    """Persist registration attribution and deliver CompleteRegistration."""
    context = marketing_context if isinstance(marketing_context, dict) else {}
    if context.get("consented") is not True:
        return {"recorded": False, "reason": "advertising_consent_missing"}

    event_id = _clean(context.get("event_id"), 120)
    if not event_id:
        return {"recorded": False, "reason": "event_id_missing"}

    existing = (
        db.query(MarketingRegistrationAttribution)
        .filter(MarketingRegistrationAttribution.event_id == event_id)
        .first()
    )
    if existing:
        return {
            "recorded": True,
            "deduplicated": True,
            "meta_delivery_status": existing.meta_delivery_status,
        }

    first_touch = _normalize_touch(context.get("first_touch"))
    last_touch = _normalize_touch(context.get("last_touch"))
    effective_touch = last_touch or first_touch or {}
    event_source_url = _clean(context.get("event_source_url"), 2048)

    row = MarketingRegistrationAttribution(
        organization_id=organization_id,
        user_id=user_id,
        event_id=event_id,
        source=_clean(effective_touch.get("source"), 120),
        medium=_clean(effective_touch.get("medium"), 120),
        campaign=_clean(effective_touch.get("campaign"), 255),
        content=_clean(effective_touch.get("content"), 255),
        term=_clean(effective_touch.get("term"), 255),
        fbclid=_clean(effective_touch.get("fbclid"), 500),
        first_touch=first_touch,
        last_touch=last_touch,
        event_source_url=event_source_url,
        consented=True,
        meta_delivery_status="pending",
    )
    db.add(row)
    db.flush()

    funnel_event = _event_row_from_attribution(
        attribution=row,
        event_key=event_id,
        event_name="CompleteRegistration",
    )
    db.add(funnel_event)
    db.commit()
    db.refresh(row)
    db.refresh(funnel_event)

    event = build_meta_conversion_event(
        event_id=event_id,
        email=email,
        user_id=user_id,
        event_source_url=event_source_url,
        first_touch=first_touch,
        last_touch=last_touch,
        fbp=_clean(context.get("fbp"), 500),
        fbc=_clean(context.get("fbc"), 500),
        client_ip=_clean(client_ip, 120),
        client_user_agent=_clean(client_user_agent, 1000),
    )
    delivery_status, meta_error = _send_meta_conversion(event)

    row.meta_delivery_status = delivery_status
    row.meta_error = meta_error
    row.updated_at = datetime.utcnow()
    funnel_event.meta_delivery_status = delivery_status
    funnel_event.meta_error = meta_error
    funnel_event.updated_at = datetime.utcnow()
    db.commit()

    return {
        "recorded": True,
        "deduplicated": False,
        "meta_delivery_status": delivery_status,
    }


def record_lifecycle_conversion(
    db: Session,
    *,
    organization_id: int,
    event_name: str,
    event_key: str,
    provider_event_id: str | None = None,
    occurred_at: datetime | None = None,
    value: Decimal | None = None,
    currency: str | None = None,
    event_data: dict | None = None,
) -> dict:
    """Send a later funnel milestone using the original consented attribution."""
    if event_name not in _SUPPORTED_META_FUNNEL_EVENTS:
        raise ValueError(f"Unsupported Meta funnel event: {event_name}")

    normalized_key = _clean(event_key, 160)
    if not normalized_key:
        return {"recorded": False, "reason": "event_key_missing"}

    existing = (
        db.query(MarketingFunnelEvent)
        .filter(MarketingFunnelEvent.event_key == normalized_key)
        .first()
    )
    if existing:
        return {
            "recorded": True,
            "deduplicated": True,
            "meta_delivery_status": existing.meta_delivery_status,
        }

    attribution = (
        db.query(MarketingRegistrationAttribution)
        .filter(
            MarketingRegistrationAttribution.organization_id == organization_id,
            MarketingRegistrationAttribution.consented.is_(True),
        )
        .order_by(MarketingRegistrationAttribution.created_at.asc())
        .first()
    )
    if attribution is None:
        return {"recorded": False, "reason": "attribution_not_found"}

    user = db.query(User).filter(User.id == attribution.user_id).first()
    if user is None or not user.email:
        return {"recorded": False, "reason": "user_email_not_found"}

    event_row = _event_row_from_attribution(
        attribution=attribution,
        event_key=normalized_key,
        event_name=event_name,
        provider_event_id=provider_event_id,
        value=value,
        currency=currency,
        event_data=event_data,
        occurred_at=occurred_at,
    )
    db.add(event_row)
    db.commit()
    db.refresh(event_row)

    custom_data = dict(event_data or {})
    if value is not None:
        custom_data["value"] = float(value)
    normalized_currency = _clean(currency, 10)
    if normalized_currency:
        custom_data["currency"] = normalized_currency

    event = build_meta_conversion_event(
        event_id=normalized_key,
        event_name=event_name,
        email=user.email,
        user_id=user.id,
        event_source_url=attribution.event_source_url,
        first_touch=attribution.first_touch,
        last_touch=attribution.last_touch,
        fbp=None,
        fbc=None,
        client_ip=None,
        client_user_agent=None,
        event_time=_event_time_seconds(occurred_at),
        custom_data=custom_data or None,
    )
    delivery_status, meta_error = _send_meta_conversion(event)

    event_row.meta_delivery_status = delivery_status
    event_row.meta_error = meta_error
    event_row.updated_at = datetime.utcnow()
    db.commit()

    return {
        "recorded": True,
        "deduplicated": False,
        "meta_delivery_status": delivery_status,
    }
