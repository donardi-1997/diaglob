"""Detect tombstone rollback during database restore and re-ingestion drills.

The expected checkpoint MUST originate from a separately secured, non-restored
ledger. Comparing a database with its own freshly computed checkpoint proves
nothing. This module does not issue deletion, accept legal clearance, or claim
external processor erasure.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from sqlalchemy.orm import Session

from ..models import ShopifyPrivacySuppression
from .shopify_privacy_suppression import (
    ShopifySuppressionError, _secret, _key_fingerprint,
)


class ShopifyRestoreVerificationError(ValueError):
    """Fail-closed restore verification; never includes selectors or PII."""


def create_shopify_suppression_checkpoint(db: Session) -> dict:
    """Produce a keyed checkpoint for external write-once storage."""
    try:
        key = _secret()
    except ShopifySuppressionError as exc:
        raise ShopifyRestoreVerificationError("SUPPRESSION_KEY_UNAVAILABLE") from exc
    rows = db.query(ShopifyPrivacySuppression).order_by(
        ShopifyPrivacySuppression.organization_id,
        ShopifyPrivacySuppression.store_id,
        ShopifyPrivacySuppression.kind,
        ShopifyPrivacySuppression.selector_digest,
    ).all()
    fingerprint = _key_fingerprint(key)
    if any(not hmac.compare_digest(row.key_fingerprint, fingerprint) for row in rows):
        raise ShopifyRestoreVerificationError("SUPPRESSION_KEY_MISMATCH")
    if len(rows) != len({
        (r.organization_id, r.store_id, r.kind, r.selector_digest)
        for r in rows
    }):
        raise ShopifyRestoreVerificationError("DUPLICATE_SUPPRESSION_ROW")

    # Include staged rows: losing a pending deletion selector is also a
    # recovery incident. Avoid timestamps, which are prone to DB dialect drift.
    canonical = [
        [r.organization_id, r.store_id, r.request_id, r.kind, r.selector_digest,
         r.domain_fingerprint, r.status]
        for r in rows
    ]
    payload = json.dumps(
        ["diaglob.shopify.tombstone-checkpoint.v1", canonical],
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return {"version": 1, "total_records": len(rows), "checkpoint_hmac": digest,
            "recovery_verified": False}


def verify_shopify_suppression_restore(
    db: Session, *, externally_stored_hmac: str, minimum_records: int,
) -> dict:
    """Compare restored DB with independently stored pre-restore HMAC.

    The expected HMAC is caller-provided; callers must first independently
    authenticate its origin from outside the DB/backup being restored.
    An approved restore flow must run this BEFORE ingesting live webhooks.
    """
    if not isinstance(externally_stored_hmac, str) or len(externally_stored_hmac) != 64:
        raise ShopifyRestoreVerificationError("EXTERNAL_LEDGER_REQUIRED")
    try:
        int(externally_stored_hmac, 16)
    except ValueError as exc:
        raise ShopifyRestoreVerificationError("EXTERNAL_LEDGER_REQUIRED") from exc
    if type(minimum_records) is not int or minimum_records < 0:
        raise ShopifyRestoreVerificationError("INVALID_EXPECTED_RECORD_COUNT")
    current = create_shopify_suppression_checkpoint(db)
    if current["total_records"] < minimum_records:
        raise ShopifyRestoreVerificationError("SUPPRESSION_LEDGER_ROLLBACK")
    if not hmac.compare_digest(current["checkpoint_hmac"], externally_stored_hmac):
        raise ShopifyRestoreVerificationError("SUPPRESSION_CHECKPOINT_MISMATCH")
    return {"recovery_verified": True, "total_records": current["total_records"],
            "provider_erasure_verified": False, "fulfillment_complete": False}
