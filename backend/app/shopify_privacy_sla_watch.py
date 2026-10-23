"""Read-only, PII-free Shopify privacy SLA watchdog.

This is *monitoring*, NOT GDPR fulfillment or approval. Every receipt remains
open until there is independently proven customer-data fulfillment. A stored
"completed" status does not silence the watchdog.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest
from .shopify_privacy_operational_audit import summarize_shopify_privacy_operations
from .services.shopify_privacy_triage import SUPPORTED_TOPICS


def _count(db: Session, condition) -> int:
    return int(
        db.query(func.count(ShopifyPrivacyRequest.id))
        .filter(condition)
        .scalar()
        or 0
    )


def audit_shopify_privacy_sla(
    db: Session, *, now: datetime | None = None,
    environment: dict[str, str] | None = None,
) -> dict:
    """Read only request and audit metadata, never payloads or selectors.

    The 23/30-day thresholds are Shopify operational action targets. They do
    not provide legal authority to erase, release, or ignore held records.
    """
    reference = now if now is not None else datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    utc_now = reference.astimezone(timezone.utc).replace(tzinfo=None)
    req = ShopifyPrivacyRequest
    audit = ShopifyPrivacyAuditEvent

    signed_received = exists().where(
        audit.request_id == req.request_id
    ).where(
        audit.event_type == "received"
    ).where(
        audit.actor_type == "shopify_hmac_verified"
    )
    prepared = exists().where(
        audit.request_id == req.request_id
    ).where(
        audit.event_type == "processing_prepared"
    ).where(
        audit.actor_type == "internal_privacy_processor"
    )
    unresolved = or_(
        req.organization_id.is_(None), req.store_id.is_(None),
        req.organization_id <= 0, req.store_id <= 0,
    )
    baseline = summarize_shopify_privacy_operations(
        db, environment=environment,
    )
    counts = {
        "approaching_30_day_target": _count(
            db,
            req.created_at <= utc_now - timedelta(days=23),
        ),
        "at_or_past_30_day_target": _count(
            db,
            req.created_at <= utc_now - timedelta(days=30),
        ),
        "tenant_store_unresolved": _count(db, unresolved),
        "signed_receipt_evidence_missing": _count(db, ~signed_received),
        "processing_queue_evidence_missing": _count(db, ~prepared),
        "unsupported_topic": _count(
            db, req.topic.notin_(tuple(SUPPORTED_TOPICS)),
        ),
        "future_or_missing_received_timestamp": _count(
            db, or_(req.created_at > utc_now, req.created_at.is_(None)),
        ),
        "incomplete_work_item_queue": baseline[
            "receipts_missing_complete_ten_item_queue"
        ],
        "unverified_work_item_completion": baseline[
            "work_items_with_unverified_completion_state"
        ],
        "review_api_unavailable_with_open_receipts": int(
            baseline["receipt_total"] > 0
            and not baseline["internal_review_secret_present"]
        ),
    }
    urgent = (
        counts["at_or_past_30_day_target"] > 0
        or counts["tenant_store_unresolved"] > 0
        or counts["signed_receipt_evidence_missing"] > 0
        or counts["processing_queue_evidence_missing"] > 0
        or counts["unsupported_topic"] > 0
        or counts["future_or_missing_received_timestamp"] > 0
        or counts["incomplete_work_item_queue"] > 0
        or counts["unverified_work_item_completion"] > 0
        or counts["review_api_unavailable_with_open_receipts"] > 0
        or not baseline["hmac_secret_present"]
        or not baseline["selector_encryption_key_present"]
    )
    attention = urgent or counts["approaching_30_day_target"] > 0
    return {
        "audit": "shopify_privacy_sla_watch_read_only",
        "as_of_utc": reference.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "receipt_total": baseline["receipt_total"],
        "counts": counts,
        "hmac_secret_present": baseline["hmac_secret_present"],
        "selector_encryption_key_present": baseline[
            "selector_encryption_key_present"
        ],
        "state": (
            "critical" if urgent else "warning" if attention else "normal"
        ),
        "attention_required": attention,
        "requires_manual_review": True,
        "read_only": True,
        "fulfillment_authorized": False,
        "fulfillment_complete": False,
        "privacy_release_ready": False,
    }


def main() -> int:
    with SessionLocal() as db:
        report = audit_shopify_privacy_sla(db)
    print(json.dumps(report, sort_keys=True))
    # CI must alert rather than silently accept breached thresholds or broken
    # evidence. Does not authorize deletion; no customer identifiers logged.
    return 2 if report["attention_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
