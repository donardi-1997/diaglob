"""Controlled, auditable *synthetic-test-only* privacy review transitions.

This is NOT an export, redaction, completion or merchant-facing API. It
cannot approve real processing and never advances a request to completed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest


class ShopifyPrivacyReviewError(ValueError):
    """The requested manual review transition is not safe or valid."""


ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending_policy_review": frozenset({
        "scope_reviewed", "manual_review_required",
    }),
    "scope_reviewed": frozenset({
        "retention_review_pending", "manual_review_required",
    }),
    "retention_review_pending": frozenset({
        "blocked_external_coverage", "manual_review_required",
    }),
    "blocked_external_coverage": frozenset({
        "retention_review_pending", "manual_review_required",
    }),
    "manual_review_required": frozenset({"pending_policy_review"}),
}

REASON_CODES = frozenset({
    "scope_verified",
    "tenant_unresolved",
    "retention_policy_pending",
    "legal_hold_pending",
    "external_coverage_pending",
    "manual_reinspection",
})


@dataclass(frozen=True)
class PrivacyReviewResult:
    request_id: str
    status: str
    changed: bool


def _ensure_synthetic_test_session(db: Session) -> None:
    """Never mutate a live privacy case, even if invoked accidentally."""
    if (
        os.getenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS") != "1"
        or not os.getenv("PYTEST_CURRENT_TEST")
        or db.get_bind().dialect.name != "sqlite"
    ):
        raise ShopifyPrivacyReviewError("SYNTHETIC_TEST_ONLY")


def record_synthetic_privacy_review(
    db: Session,
    *,
    request_id: str,
    expected_status: str,
    next_status: str,
    reason_code: str,
) -> PrivacyReviewResult:
    """CAS-style transition with a PII-free audit event in one transaction.

    Only status values from the review-only allowlist are permitted; a webhook
    can never reach a state suggesting data deletion or export fulfillment.
    All status changes and their audit evidence commit atomically.
    """
    _ensure_synthetic_test_session(db)
    if next_status not in ALLOWED_TRANSITIONS.get(expected_status, frozenset()):
        raise ShopifyPrivacyReviewError("TRANSITION_NOT_ALLOWED")
    if reason_code not in REASON_CODES:
        raise ShopifyPrivacyReviewError("REASON_CODE_NOT_ALLOWED")
    if (
        not isinstance(request_id, str)
        or len(request_id) != 64
        or any(char not in "0123456789abcdef" for char in request_id)
    ):
        raise ShopifyPrivacyReviewError("INVALID_REQUEST_ID")

    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).first()
    if receipt is None:
        raise ShopifyPrivacyReviewError("REQUEST_NOT_FOUND")

    if receipt.status == next_status:
        # A retry after commit is idempotent and generates no extra audit row.
        return PrivacyReviewResult(
            request_id=request_id, status=next_status, changed=False
        )
    if receipt.status != expected_status:
        raise ShopifyPrivacyReviewError("STALE_REVIEW_STATUS")
    if (
        next_status == "scope_reviewed"
        and (receipt.organization_id is None or receipt.store_id is None)
    ):
        raise ShopifyPrivacyReviewError("TENANT_UNRESOLVED")

    now = datetime.utcnow()
    count = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
        ShopifyPrivacyRequest.status == expected_status,
    ).update(
        {
            ShopifyPrivacyRequest.status: next_status,
            ShopifyPrivacyRequest.updated_at: now,
        },
        synchronize_session=False,
    )
    if count != 1:
        db.rollback()
        raise ShopifyPrivacyReviewError("STALE_REVIEW_STATUS")

    db.add(
        ShopifyPrivacyAuditEvent(
            request_id=request_id,
            event_type="review_transition",
            from_status=expected_status,
            to_status=next_status,
            reason_code=reason_code,
            actor_type="synthetic_review",
            created_at=now,
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return PrivacyReviewResult(
        request_id=request_id, status=next_status, changed=True
    )
