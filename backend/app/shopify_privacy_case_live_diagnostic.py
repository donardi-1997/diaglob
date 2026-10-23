"""PII-free production classification of Shopify GDPR case resolution blockers.

Does not read/decrypt customer selectors or log shop IDs/domains, request
digests, emails, phone numbers or authentication values. Does not mutate data.
"""
from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import ShopifyPrivacyRequest
from .services.shopify_privacy_identity_repair import (
    ShopifyPrivacyIdentityRepairError,
    repair_signed_shopify_privacy_receipt_identity,
)

_ALLOWED_REASONS = frozenset({
    "INVALID_PRIVACY_REQUEST_ID",
    "PRIVACY_REQUEST_NOT_FOUND",
    "HISTORICAL_COMPLETION_REQUIRES_REVIEW",
    "SIGNED_SHOP_HISTORY_CONFLICT",
    "SIGNED_INTAKE_EVIDENCE_MISSING",
    "PRIVACY_PROCESSING_QUEUE_UNVERIFIED",
    "UNVERIFIED_PRIVACY_COMPLETION",
    "PARTIAL_TENANT_BINDING_UNSAFE",
    "SIGNED_SHOP_HISTORY_UNVERIFIED",
    "SIGNED_SHOP_HISTORY_MISSING",
    "HISTORICAL_STORE_UNVERIFIED",
    "TENANT_REBIND_FORBIDDEN",
})
_TOPICS = frozenset({
    "shop/redact", "customers/redact", "customers/data_request",
})


def diagnose_shopify_privacy_cases(
    db: Session, *, environment: dict[str, str] | None = None,
    now: datetime | None = None,
) -> dict:
    """Classify receipt repair eligibility; no modifications or raw IDs."""
    env = os.environ if environment is None else environment
    reference = datetime.now(timezone.utc) if now is None else now
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    reference = reference.astimezone(timezone.utc).replace(tzinfo=None)
    counts = Counter()
    cases = db.query(
        ShopifyPrivacyRequest.request_id,
        ShopifyPrivacyRequest.topic,
        ShopifyPrivacyRequest.status,
        ShopifyPrivacyRequest.created_at,
    ).order_by(ShopifyPrivacyRequest.id).all()
    for request_id, topic, status, created_at in cases:
        if topic not in _TOPICS:
            counts["unsupported_topic"] += 1
            continue
        if status == "completed":
            # A stored completed status is not evidence of fulfilled deletion.
            counts["claimed_complete_requires_external_evidence"] += 1
            continue
        if topic != "shop/redact":
            counts["customer_request_requires_subject_provenance"] += 1
            continue
        counts["open_shop_redact"] += 1
        if created_at is None or created_at > reference:
            counts["invalid_received_timestamp"] += 1
        try:
            report = repair_signed_shopify_privacy_receipt_identity(
                db, request_id=request_id, dry_run=True,
            )
        except ShopifyPrivacyIdentityRepairError as exc:
            reason = str(exc)
            counts[
                reason if reason in _ALLOWED_REASONS else
                "UNCLASSIFIED_REVIEW_BLOCKER"
            ] += 1
        else:
            if report.get("repair_eligible") is True:
                counts["eligible_for_controlled_identity_repair"] += 1
            elif report.get("scope_recovered") is True:
                counts["scope_already_recovered"] += 1
            else:
                counts["UNCLASSIFIED_REVIEW_BLOCKER"] += 1
    return {
        "audit": "shopify_privacy_case_live_diagnostic_read_only",
        "receipts": len(cases),
        "classification_counts": dict(sorted(counts.items())),
        "internal_operator_auth_configured": bool(
            env.get("DIAGLOB_INTERNAL_SECRET")
        ),
        "signed_shopify_delivery_independently_verified": False,
        "read_only": True,
        "requires_manual_review": bool(cases),
        "erasure_authorized": False,
        "fulfillment_complete": False,
        "privacy_release_ready": False,
    }


def main() -> int:
    with SessionLocal() as db:
        report = diagnose_shopify_privacy_cases(db)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
