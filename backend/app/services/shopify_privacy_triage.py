"""Pure, fail-closed Shopify privacy receipt triage.

The result is internal operational guidance, never fulfillment authorization.
No PII, database lookups, decryption, network access or mutations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SUPPORTED_TOPICS = frozenset({
    "customers/data_request", "customers/redact", "shop/redact",
})


@dataclass(frozen=True)
class PrivacyTriage:
    request_id: str
    reasons: tuple[str, ...]
    priority: str
    requires_manual_review: bool = True
    fulfillment_authorized: bool = False


def triage_privacy_receipt(
    *,
    request_id: str,
    topic: str,
    received_at: datetime,
    organization_id: int | None,
    store_id: int | None,
    now: datetime,
    warning_after_days: int = 23,
    overdue_after_days: int = 30,
) -> PrivacyTriage:
    """Classify a stored receipt without suggesting completion.

    Time thresholds are operational indicators, not definitive legal deadlines.
    Naive datetimes are rejected: mixed time zones can suppress escalation.
    The request identifier is an opaque 64-character lowercase hex digest.
    """
    if (
        type(request_id) is not str or len(request_id) != 64
        or any(c not in "0123456789abcdef" for c in request_id)
    ):
        raise ValueError("INVALID_REQUEST_ID")
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    if (
        type(warning_after_days) is not int or type(overdue_after_days) is not int
        or warning_after_days < 0 or overdue_after_days <= warning_after_days
    ):
        raise ValueError("INVALID_THRESHOLDS")

    age = now.astimezone(timezone.utc) - received_at.astimezone(timezone.utc)
    reasons: list[str] = []
    if topic not in SUPPORTED_TOPICS:
        reasons.append("UNKNOWN_TOPIC")
    if (
        type(organization_id) is not int or organization_id <= 0
        or type(store_id) is not int or store_id <= 0
    ):
        reasons.append("TENANT_UNRESOLVED")
    if age < timedelta(0):
        reasons.append("FUTURE_RECEIPT_TIMESTAMP")
    elif age >= timedelta(days=overdue_after_days):
        reasons.append("OPERATIONAL_THRESHOLD_EXCEEDED")
    elif age >= timedelta(days=warning_after_days):
        reasons.append("APPROACHING_OPERATIONAL_THRESHOLD")

    if "OPERATIONAL_THRESHOLD_EXCEEDED" in reasons:
        priority = "critical"
    elif any(r in reasons for r in (
        "UNKNOWN_TOPIC", "TENANT_UNRESOLVED", "FUTURE_RECEIPT_TIMESTAMP",
        "APPROACHING_OPERATIONAL_THRESHOLD",
    )):
        priority = "high"
    else:
        priority = "normal"
    return PrivacyTriage(
        request_id=request_id,
        reasons=tuple(reasons),
        priority=priority,
    )
