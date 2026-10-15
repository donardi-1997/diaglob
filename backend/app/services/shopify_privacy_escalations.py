"""Read-only, priority-ordered Shopify privacy escalation queue.

Operational monitoring only. Never assume a stored "completed" status means
GDPR fulfillment; completion cannot be inferred without independent proof.
Selects metadata only: no encrypted selectors, buyer information or shop IDs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyRequest
from .shopify_privacy_triage import SUPPORTED_TOPICS, triage_privacy_receipt

MAX_ESCALATIONS_PER_PAGE = 100
MAX_ESCALATION_OFFSET = 100_000


def list_shopify_privacy_escalations(
    db: Session, *, limit: int = 20, offset: int = 0,
    now: datetime | None = None,
) -> dict:
    """Surface all warning/overdue cases, unresolved tenants and anomalies.

    The SQL filter runs *before* pagination: a backlog of normal cases cannot
    hide a later critical case. Priority is calculated in SQL for ordering and
    checked independently with the existing triage classifier. No status filter:
    until true fulfillment exists, even a manually set 'completed' is open.
    """
    if (
        type(limit) is not int or not 1 <= limit <= MAX_ESCALATIONS_PER_PAGE
        or type(offset) is not int or not 0 <= offset <= MAX_ESCALATION_OFFSET
    ):
        raise ValueError("INVALID_ESCALATION_PAGINATION")
    reference = now if now is not None else datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    reference = reference.astimezone(timezone.utc)
    sql_now = reference.replace(tzinfo=None)
    critical_before = sql_now - timedelta(days=30)
    warning_before = sql_now - timedelta(days=23)

    model = ShopifyPrivacyRequest
    missing_timestamp = model.created_at.is_(None)
    unresolved = or_(
        model.organization_id.is_(None), model.store_id.is_(None),
        model.organization_id <= 0, model.store_id <= 0,
    )
    anomaly = or_(
        missing_timestamp, model.created_at > sql_now,
        model.topic.notin_(tuple(SUPPORTED_TOPICS)), unresolved,
    )
    attention = or_(model.created_at <= warning_before, anomaly)
    critical = or_(missing_timestamp, model.created_at <= critical_before)
    urgency = case((critical, 0), else_=1)
    rows = (
        db.query(
            model.request_id, model.topic, model.created_at,
            model.organization_id, model.store_id,
        )
        .filter(attention)
        .order_by(urgency.asc(), model.created_at.asc(), model.id.asc())
        .offset(offset).limit(limit + 1)
        .all()
    )
    cases = []
    for item in rows[:limit]:
        received_at = item.created_at
        if received_at is None:
            # Missing timestamps are an integrity emergency, never discarded
            # or silently dated using an inferred/default receipt time.
            cases.append({
                "request_id": item.request_id,
                "topic": item.topic if item.topic in SUPPORTED_TOPICS else "unknown",
                "priority": "critical", "reasons": ["RECEIPT_TIMESTAMP_MISSING"],
                "age_days": None, "deadline_at_utc": None,
                "requires_manual_review": True,
                "fulfillment_authorized": False,
                "fulfillment_complete": False,
            })
            continue
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=timezone.utc)
        triage = triage_privacy_receipt(
            request_id=item.request_id, topic=item.topic,
            received_at=received_at, organization_id=item.organization_id,
            store_id=item.store_id, now=reference,
        )
        if triage.priority == "normal":
            # SQL predicates and triage policy must not drift silently.
            raise ValueError("PRIVACY_ESCALATION_TRIAGE_DRIFT")
        deadline = received_at.astimezone(timezone.utc) + timedelta(days=30)
        cases.append({
            "request_id": triage.request_id,
            "topic": item.topic if item.topic in SUPPORTED_TOPICS else "unknown",
            "priority": triage.priority,
            "reasons": list(triage.reasons),
            "age_days": max(0, int((reference - received_at).total_seconds() // 86400)),
            "deadline_at_utc": deadline.isoformat().replace("+00:00", "Z"),
            "requires_manual_review": True,
            "fulfillment_authorized": False,
            "fulfillment_complete": False,
        })
    has_more = len(rows) > limit
    return {
        "read_only": True, "fulfillment_authorized": False,
        "fulfillment_complete": False,
        "cases": cases, "limit": limit, "offset": offset,
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
    }
