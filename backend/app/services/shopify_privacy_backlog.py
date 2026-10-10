"""PII-free backlog and deadline monitoring for received Shopify privacy requests.

Only aggregate SQL queries over receipt metadata. No customer selectors are
decrypted, no payloads are fetched, and no request status is changed.
A Shopify 30-day fulfillment target is a monitoring threshold, not proof of
legal compliance or authorization for destructive processing.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyRequest


# No real-data fulfillment workflow is enabled. A status string such as
# "completed" is NOT evidence that a request was fulfilled. Until a verified
# processing and completion path is implemented, every recorded receipt stays
# in the outstanding backlog, even if its status text was manually changed.
SHOPIFY_FULFILLMENT_DAYS = 30
ALERT_WINDOW_DAYS = 7
COMPLIANCE_TOPICS = (
    "customers/data_request",
    "customers/redact",
    "shop/redact",
)


@dataclass(frozen=True)
class PrivacyTopicBacklog:
    topic: str
    outstanding: int
    overdue: int
    due_within_7_days: int
    tenant_unresolved: int


@dataclass(frozen=True)
class PrivacyBacklogSummary:
    outstanding_total: int
    overdue_total: int
    due_within_7_days_total: int
    tenant_unresolved_total: int
    unrecognized_topic_total: int
    oldest_outstanding_days: int | None
    fulfillment_target_days: int
    live_processing_ready: bool
    topics: tuple[PrivacyTopicBacklog, ...]

    def safe_dict(self) -> dict:
        """Expose metrics only, never shop/customer/request identifiers."""
        return asdict(self)


def summarize_shopify_privacy_backlog(
    db: Session,
    *,
    now: datetime | None = None,
) -> PrivacyBacklogSummary:
    """Aggregate unresolved receipts in SQL without retrieving raw PII rows."""
    if now is None:
        reference = datetime.utcnow()
    elif now.tzinfo is not None:
        reference = now.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        reference = now
    overdue_before = reference - timedelta(days=SHOPIFY_FULFILLMENT_DAYS)
    expiring_before = reference - timedelta(
        days=SHOPIFY_FULFILLMENT_DAYS - ALERT_WINDOW_DAYS
    )

    # COUNT/SUM/MIN are database aggregates. No raw shop_id, domain, receipt
    # selector, customer ID, or message content crosses the database boundary.
    rows = (
        db.query(
            ShopifyPrivacyRequest.topic,
            func.count(ShopifyPrivacyRequest.id).label("outstanding"),
            func.sum(
                case(
                    (ShopifyPrivacyRequest.created_at < overdue_before, 1),
                    else_=0,
                )
            ).label("overdue"),
            func.sum(
                case(
                    (
                        and_(
                            ShopifyPrivacyRequest.created_at >= overdue_before,
                            ShopifyPrivacyRequest.created_at <= expiring_before,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("due_soon"),
            func.sum(
                case(
                    (
                        or_(
                            ShopifyPrivacyRequest.organization_id.is_(None),
                            ShopifyPrivacyRequest.store_id.is_(None),
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("unresolved"),
            func.min(ShopifyPrivacyRequest.created_at).label("oldest"),
        )
        .group_by(ShopifyPrivacyRequest.topic)
        .all()
    )

    by_topic = {row.topic: row for row in rows}
    unrecognized = tuple(
        row for row in rows if row.topic not in COMPLIANCE_TOPICS
    )
    summaries = []
    oldest = min(
        (row.oldest for row in rows if row.oldest is not None),
        default=None,
    )
    for topic in COMPLIANCE_TOPICS:
        row = by_topic.get(topic)
        if row is None:
            summaries.append(PrivacyTopicBacklog(topic, 0, 0, 0, 0))
            continue
        summaries.append(
            PrivacyTopicBacklog(
                topic=topic,
                outstanding=int(row.outstanding or 0),
                overdue=int(row.overdue or 0),
                due_within_7_days=int(row.due_soon or 0),
                tenant_unresolved=int(row.unresolved or 0),
            )
        )

    return PrivacyBacklogSummary(
        outstanding_total=sum(int(row.outstanding or 0) for row in rows),
        overdue_total=sum(int(row.overdue or 0) for row in rows),
        due_within_7_days_total=sum(int(row.due_soon or 0) for row in rows),
        tenant_unresolved_total=sum(int(row.unresolved or 0) for row in rows),
        unrecognized_topic_total=sum(int(row.outstanding or 0) for row in unrecognized),
        oldest_outstanding_days=(
            max(0, (reference - oldest).days) if oldest is not None else None
        ),
        fulfillment_target_days=SHOPIFY_FULFILLMENT_DAYS,
        live_processing_ready=False,
        topics=tuple(summaries),
    )
