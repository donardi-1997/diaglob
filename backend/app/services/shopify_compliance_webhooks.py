"""Durable intake of Shopify's authenticated privacy webhooks.

This is an inbox, NOT a finished privacy export/erasure processor. Every valid
request is committed before acknowledgement. Actual processing remains gated
on a legally reviewed retention policy and synthetic end-to-end tests.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest
from ..shopify_oauth import normalize_shop_domain
from ..shopify_security import encrypt_shopify_secret
from .shopify_webhook_service import resolve_shopify_connection

logger = logging.getLogger(__name__)

COMPLIANCE_TOPICS = frozenset(
    {"customers/data_request", "customers/redact", "shop/redact"}
)


def _event_key(
    topic: str,
    payload: dict[str, Any],
    *,
    webhook_id: str | None = None,
) -> str:
    """Deduplicate transport retries; prefer Shopify's delivery identifier.

    Without an ID we fall back to a canonical subject/payload hash; identical
    legacy deliveries can therefore coalesce, and must be reviewed manually.
    """
    shop_id = str(payload.get("shop_id") or "")
    if not shop_id:
        raise ValueError("SHOP_ID_REQUIRED")

    if webhook_id:
        if len(webhook_id) > 255:
            raise ValueError("INVALID_WEBHOOK_ID")
        canonical = {
            "topic": topic,
            "shop_id": shop_id,
            "shop_domain": payload.get("shop_domain"),
            "webhook_id": webhook_id,
        }
    else:
        canonical = {"topic": topic, "shop_id": shop_id, "payload": payload}
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _minimal_selectors(payload: dict[str, Any]) -> dict[str, Any]:
    """Retain only the selectors a future privacy processor needs.

    Avoid copying arbitrary Shopify payload fields into our database. This data
    is encrypted at rest; do not log or include it in API responses.
    """
    subject = payload.get("customer")
    if subject is not None and not isinstance(subject, dict):
        raise ValueError("INVALID_CUSTOMER")
    customer = {
        key: subject[key]
        for key in ("id", "email", "phone")
        if isinstance(subject, dict) and subject.get(key) is not None
    }
    selectors: dict[str, Any] = {"customer": customer}
    for key in ("orders_to_redact", "orders_requested"):
        values = payload.get(key)
        if values is not None:
            if not isinstance(values, list) or len(values) > 500:
                raise ValueError("INVALID_ORDER_SELECTORS")
            selectors[key] = values
    data_request = payload.get("data_request")
    if isinstance(data_request, dict) and data_request.get("id") is not None:
        selectors["data_request_id"] = data_request["id"]
    return selectors


def process_shopify_compliance_webhook(
    db: Session,
    *,
    topic: str,
    payload: dict[str, Any],
    webhook_id: str | None = None,
    header_shop_domain: str | None = None,
) -> dict[str, Any]:
    """Persist an authenticated Shopify privacy callback before returning 200.

    The route authenticates HMAC over the raw body. Disconnected/unknown shops
    are still stored, but never bound to a guessed tenant. Duplicate deliveries
    share one durable receipt and never re-run destructive processing.
    """
    if topic not in COMPLIANCE_TOPICS:
        raise ValueError("UNSUPPORTED_COMPLIANCE_TOPIC")
    if not isinstance(payload, dict):
        raise ValueError("INVALID_PAYLOAD")

    shop_id = str(payload.get("shop_id") or "")
    if not shop_id or len(shop_id) > 80:
        raise ValueError("INVALID_SHOP_IDENTITY")

    try:
        shop_domain = normalize_shop_domain(str(payload.get("shop_domain") or ""))
        if header_shop_domain and normalize_shop_domain(header_shop_domain) != shop_domain:
            raise ValueError("SHOP_DOMAIN_MISMATCH")
    except (ValueError, AttributeError) as exc:
        raise ValueError("INVALID_SHOP_IDENTITY") from exc

    selectors = _minimal_selectors(payload)
    receipt_id = _event_key(topic, payload, webhook_id=webhook_id)
    existing = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == receipt_id,
    ).first()
    if existing is not None:
        return _receipt(existing, duplicate=True)

    # Encryption is mandatory: if key is unavailable fail/retry, never persist
    # customer selectors or email addresses in plaintext.
    encrypted_selectors = encrypt_shopify_secret(
        json.dumps(selectors, sort_keys=True, separators=(",", ":"))
    )
    connection = resolve_shopify_connection(db, shop_domain)
    request = ShopifyPrivacyRequest(
        request_id=receipt_id,
        topic=topic,
        shop_id=shop_id,
        shop_domain=shop_domain,
        organization_id=connection.organization_id if connection else None,
        store_id=connection.store_id if connection else None,
        selector_encrypted=encrypted_selectors,
        status="pending_policy_review",
        attempts=0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    # The event and receipt share one transaction. Retries are deduplicated
    # by the receipt key, so no duplicate received audit is emitted.
    db.add(request)
    db.add(
        ShopifyPrivacyAuditEvent(
            request_id=receipt_id,
            event_type="received",
            from_status=None,
            to_status="pending_policy_review",
            reason_code=(
                "tenant_bound" if connection else "tenant_unresolved"
            ),
            actor_type="shopify_hmac_verified",
            created_at=datetime.utcnow(),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # A second worker may have committed the same delivery concurrently.
        db.rollback()
        already_recorded = db.query(ShopifyPrivacyRequest).filter(
            ShopifyPrivacyRequest.request_id == receipt_id,
        ).first()
        if already_recorded is None:
            raise
        return _receipt(already_recorded, duplicate=True)

    logger.info(
        "shopify.compliance.persisted topic=%s request=%s mapped=%s",
        topic,
        receipt_id,
        bool(connection),
    )
    return _receipt(request, duplicate=False)


def _receipt(request: ShopifyPrivacyRequest, *, duplicate: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "action": "duplicate" if duplicate else "recorded",
        "topic": request.topic,
        "request_id": request.request_id,
        "store_connected": request.organization_id is not None,
        "redaction_status": (
            "pending_policy_review"
            if request.topic in {"customers/redact", "shop/redact"}
            else "data_request_recorded"
        ),
    }
