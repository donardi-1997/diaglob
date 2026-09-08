"""Product analytics service.

Centralized, fail-open analytics for Diaglob activation funnel.
Uses PostHog Cloud. Never blocks business operations.
Never sends PII, secrets, or message content.
"""
import logging
import os
from typing import Any

import posthog

logger = logging.getLogger(__name__)

# Event version for future schema changes
EVENT_VERSION = 1

# Forbidden keys — never sent to analytics
FORBIDDEN_KEYS = {
    "access_token", "refresh_token", "password", "token",
    "secret", "key", "authorization", "credential",
    "message", "message_body", "text", "content",
    "phone", "phone_number", "email", "address",
    "raw_payload", "provider_payload",
    "prompt", "response", "ai_response", "rag_context",
    "document_content", "customer_name", "customer_email",
    "customer_phone", "customer_address",
}

_client: posthog.Posthog | None = None
_enabled = False


def _get_client() -> posthog.Posthog | None:
    """Lazy-initialize PostHog client."""
    global _client, _enabled

    if _client is not None:
        return _client

    api_key = os.getenv("POSTHOG_API_KEY", "").strip()
    host = os.getenv("POSTHOG_HOST", "https://us.i.posthog.com").strip()
    enabled_str = os.getenv("PRODUCT_ANALYTICS_ENABLED", "true").strip().lower()

    if not api_key or enabled_str in ("false", "0", "no"):
        _enabled = False
        return None

    try:
        _client = posthog.Posthog(
            api_key,
            host=host,
            enable_exception_autocapture=False,
            autocapture=False,
        )
        _enabled = True
        return _client
    except Exception as exc:
        logger.warning("Failed to initialize PostHog: %s", exc)
        _enabled = False
        return None


def _sanitize_properties(properties: dict[str, Any] | None) -> dict[str, Any]:
    """Remove forbidden keys from event properties."""
    if not properties:
        return {}

    return {
        k: v
        for k, v in properties.items()
        if k not in FORBIDDEN_KEYS
        and not any(forbidden in k.lower() for forbidden in FORBIDDEN_KEYS)
    }


def capture(
    event_name: str,
    distinct_id: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Send an analytics event. Fail-open: never raises."""
    client = _get_client()
    if client is None:
        return

    safe_props = _sanitize_properties(properties)
    safe_props["event_version"] = EVENT_VERSION

    try:
        client.capture(
            distinct_id=distinct_id,
            event=event_name,
            properties=safe_props,
        )
    except Exception as exc:
        logger.warning("Analytics capture failed for %s: %s", event_name, exc)


def identify(
    distinct_id: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Identify a user. Fail-open: never raises."""
    client = _get_client()
    if client is None:
        return

    safe_props = _sanitize_properties(properties)

    try:
        client.identify(
            distinct_id=distinct_id,
            properties=safe_props,
        )
    except Exception as exc:
        logger.warning("Analytics identify failed: %s", exc)


def group_identify(
    group_type: str,
    group_key: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Identify a group (org/store). Fail-open: never raises."""
    client = _get_client()
    if client is None:
        return

    safe_props = _sanitize_properties(properties)

    try:
        client.group_identify(
            group_type=group_type,
            group_key=group_key,
            properties=safe_props,
        )
    except Exception as exc:
        logger.warning("Analytics group_identify failed: %s", exc)


def is_enabled() -> bool:
    """Check if analytics is configured and enabled."""
    _get_client()
    return _enabled


# ============================================================
# CONVENIENCE EVENT CAPTURE FUNCTIONS
# ============================================================


def track_signup_completed(
    user_id: int,
    organization_id: int,
    role: str,
) -> None:
    capture(
        "signup_completed",
        distinct_id=str(user_id),
        properties={
            "organization_id": organization_id,
            "user_id": user_id,
            "role": role,
        },
    )


def track_store_created(
    user_id: int,
    organization_id: int,
    store_id: int,
    country: str | None = None,
    currency: str | None = None,
) -> None:
    capture(
        "store_created",
        distinct_id=str(user_id),
        properties={
            "organization_id": organization_id,
            "store_id": store_id,
            "country": country,
            "currency": currency,
        },
    )


def track_shopify_connected(
    user_id: int,
    organization_id: int,
    store_id: int,
) -> None:
    capture(
        "shopify_connected",
        distinct_id=str(user_id),
        properties={
            "organization_id": organization_id,
            "store_id": store_id,
        },
    )


def track_catalog_synced(
    user_id: int,
    organization_id: int,
    store_id: int,
    products_synced: int,
) -> None:
    capture(
        "catalog_synced",
        distinct_id=str(user_id),
        properties={
            "organization_id": organization_id,
            "store_id": store_id,
            "products_synced": products_synced,
        },
    )


def track_whatsapp_connected(
    user_id: int,
    organization_id: int,
    store_id: int,
) -> None:
    capture(
        "whatsapp_connected",
        distinct_id=str(user_id),
        properties={
            "organization_id": organization_id,
            "store_id": store_id,
        },
    )


def track_first_whatsapp_inbound(
    organization_id: int,
    store_id: int,
    conversation_id: int,
) -> None:
    capture(
        "first_whatsapp_inbound",
        distinct_id=f"org:{organization_id}",
        properties={
            "organization_id": organization_id,
            "store_id": store_id,
            "conversation_id": conversation_id,
        },
    )


def track_first_whatsapp_ai_reply(
    organization_id: int,
    store_id: int,
    conversation_id: int,
) -> None:
    capture(
        "first_whatsapp_ai_reply",
        distinct_id=f"org:{organization_id}",
        properties={
            "organization_id": organization_id,
            "store_id": store_id,
            "conversation_id": conversation_id,
        },
    )


def track_knowledge_created(
    user_id: int,
    organization_id: int,
    kb_id: int,
) -> None:
    capture(
        "knowledge_created",
        distinct_id=str(user_id),
        properties={
            "organization_id": organization_id,
            "kb_id": kb_id,
        },
    )


def track_first_automation_created(
    user_id: int,
    organization_id: int,
    store_id: int,
    automation_id: int,
) -> None:
    capture(
        "first_automation_created",
        distinct_id=str(user_id),
        properties={
            "organization_id": organization_id,
            "store_id": store_id,
            "automation_id": automation_id,
        },
    )


def track_checkout_started(
    user_id: int,
    organization_id: int,
    plan: str,
) -> None:
    capture(
        "checkout_started",
        distinct_id=str(user_id),
        properties={
            "organization_id": organization_id,
            "plan": plan,
        },
    )


def track_checkout_completed(
    organization_id: int,
    plan: str,
    subscription_id: str | None = None,
) -> None:
    capture(
        "checkout_completed",
        distinct_id=f"org:{organization_id}",
        properties={
            "organization_id": organization_id,
            "plan": plan,
            "subscription_id": subscription_id,
        },
    )
