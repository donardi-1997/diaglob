"""Bounded, PII-free internal review queue for Shopify privacy receipts.

Read-only operational triage, NOT GDPR fulfillment. No raw customer selectors,
shop domains, encrypted payloads, tenant identifiers, or arbitrary topic strings
cross the API boundary. All receipts remain outstanding regardless of status.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyRequest
from .shopify_privacy_triage import SUPPORTED_TOPICS, triage_privacy_receipt

MAX_CASES_PER_PAGE = 100
MAX_CASE_OFFSET = 100_000


def list_shopify_privacy_cases(
    db: Session,
    *,
    limit: int = 20,
    offset: int = 0,
    now: datetime | None = None,
) -> dict:
    """Return stable, oldest-first work items without fetching any PII columns.

    This endpoint deliberately does not trust the stored receipt status: a
    manually set "completed" field is NOT evidence of fulfilled rights.
    Database timestamps are currently stored as naive UTC, so they are
    explicitly converted before using the timezone-aware triage algorithm.
    """
    if (
        type(limit) is not int or not 1 <= limit <= MAX_CASES_PER_PAGE
        or type(offset) is not int or not 0 <= offset <= MAX_CASE_OFFSET
    ):
        raise ValueError("INVALID_CASE_PAGINATION")
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")

    rows = (
        db.query(
            ShopifyPrivacyRequest.request_id,
            ShopifyPrivacyRequest.topic,
            ShopifyPrivacyRequest.created_at,
            ShopifyPrivacyRequest.organization_id,
            ShopifyPrivacyRequest.store_id,
        )
        .order_by(ShopifyPrivacyRequest.created_at, ShopifyPrivacyRequest.id)
        .offset(offset)
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    cases = []
    for row in rows[:limit]:
        created_at = row.created_at
        if created_at is None:
            # A corrupt timestamp cannot be given a falsely normal priority.
            raise ValueError("RECEIPT_TIMESTAMP_MISSING")
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        triage = triage_privacy_receipt(
            request_id=row.request_id,
            topic=row.topic,
            received_at=created_at,
            organization_id=row.organization_id,
            store_id=row.store_id,
            now=reference,
        )
        age_days = max(
            0,
            int(
                (reference.astimezone(timezone.utc)
                 - created_at.astimezone(timezone.utc)).total_seconds() // 86400
            ),
        )
        cases.append({
            "request_id": triage.request_id,
            "topic": row.topic if row.topic in SUPPORTED_TOPICS else "unknown",
            "age_days": age_days,
            "priority": triage.priority,
            "reasons": list(triage.reasons),
            "requires_manual_review": True,
            "fulfillment_authorized": False,
        })

    return {
        "read_only": True,
        "fulfillment_authorized": False,
        "cases": cases,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
    }
