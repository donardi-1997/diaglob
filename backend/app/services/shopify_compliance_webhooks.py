"""Shopify mandatory privacy webhook handling.

This service records authenticated subject requests idempotently. Redaction is
deliberately not destructive until DIAGLOB's retention and legal-hold policy is
defined and validated against the stored data inventory.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..models import CommerceConnection

logger = logging.getLogger(__name__)

COMPLIANCE_TOPICS = frozenset(
    {"customers/data_request", "customers/redact", "shop/redact"}
)


def _event_key(topic: str, payload: dict[str, Any]) -> str:
    shop_id = str(payload.get("shop_id") or "")
    if not shop_id:
        raise ValueError("SHOP_ID_REQUIRED")

    subject = payload.get("customer") or {}
    identifiers = [str(subject.get(key) or "") for key in ("id", "email", "phone")]
    orders = sorted(str(value) for value in (payload.get("orders_to_redact") or []))
    canonical = json.dumps(
        {"topic": topic, "shop_id": shop_id, "subject": identifiers, "orders": orders},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def process_shopify_compliance_webhook(
    db: Session,
    *,
    topic: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Record a compliance request without logging its personal data.

    The authenticated request is acknowledged with an auditable, deterministic
    receipt. Actual redaction requires a reviewed data map and retention policy;
    this handler intentionally leaves source records untouched pending that work.
    """
    if topic not in COMPLIANCE_TOPICS:
        raise ValueError("UNSUPPORTED_COMPLIANCE_TOPIC")
    if not isinstance(payload, dict):
        raise ValueError("INVALID_PAYLOAD")

    shop_id = str(payload.get("shop_id") or "")
    shop_domain = str(payload.get("shop_domain") or "").strip().lower()
    parsed_domain = urlparse(f"https://{shop_domain}")
    if (
        not shop_id
        or parsed_domain.hostname != shop_domain
        or not shop_domain.endswith(".myshopify.com")
    ):
        raise ValueError("INVALID_SHOP_IDENTITY")

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider == "shopify",
            CommerceConnection.external_store_url == shop_domain,
        )
        .first()
    )
    # Shopify expects a 2xx for a shop already uninstalled. The receipt is
    # logged as a digest only so repeated delivery remains safe and private.
    digest = _event_key(topic, payload)
    logger.info(
        "shopify.compliance.received topic=%s shop_id=%s connected=%s request=%s at=%s",
        topic,
        shop_id,
        bool(connection),
        digest,
        datetime.now(timezone.utc).isoformat(),
    )
    return {
        "ok": True,
        "action": "recorded",
        "topic": topic,
        "request_id": digest,
        "store_connected": bool(connection),
        "redaction_status": "pending_policy_review"
        if topic in {"customers/redact", "shop/redact"}
        else "data_request_recorded",
    }
