"""Read-only backup-surface coverage and restore-drill reporting.

There is no backup engine, no backup deletion and no offsite ledger storage
in this module: backup systems live outside the application and must be
operated and attested externally. A passed drill reconciles only the local
suppression checkpoint against an independently stored HMAC; it never proves
backup expiry, provider erasure, or completed GDPR fulfillment.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import ShopifyPrivacySuppression, Store
from .shopify_privacy_controls import RESTORE_CONTROLS
from .shopify_privacy_restore import (
    ShopifyRestoreVerificationError,
    verify_shopify_suppression_restore,
)


class ShopifyPrivacyBackupCoverageError(ValueError):
    """Stable, PII-free backup-coverage failure codes."""


# Operators must run this AFTER restoring from a backup and BEFORE resuming
# live webhook/customer ingestion, using the pre-restore checkpoint.
RESTORE_DRILL_NAME = "suppression_restore_reconciliation"

_BLOCKERS = (
    "BACKUP_RESTORE_COVERAGE_UNVERIFIED",
    "SUBPROCESSOR_AND_BACKUP_COVERAGE_UNVERIFIED",
)


def _validate_tenant(organization_id: int, store_id: int) -> None:
    for label, value in (("organization_id", organization_id), ("store_id", store_id)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ShopifyPrivacyBackupCoverageError(
                f"UNVERIFIED_BACKUP_{label.upper()}"
            )


def _backup_surfaces(drill_status: str) -> list[dict]:
    return [
        {
            "control": name,
            "state": "verification_required",
            "drill_status": drill_status,
            "independently_verified": False,
        }
        for name in RESTORE_CONTROLS
    ]


def inspect_shopify_privacy_backup_coverage(
    db: Session,
    *,
    organization_id: int,
    store_id: int,
) -> dict:
    """Report backup/restore control state for one verified shop.

    Only suppression-ledger row counts are queried; backup payloads, dumps
    and snapshot contents are never read because they do not live here.
    """
    _validate_tenant(organization_id, store_id)
    store = db.query(Store.id).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
    ).first()
    if store is None:
        raise ShopifyPrivacyBackupCoverageError("BACKUP_SHOP_NOT_FOUND")

    suppression_rows = int(
        db.query(ShopifyPrivacySuppression)
        .filter(
            ShopifyPrivacySuppression.organization_id == organization_id,
            ShopifyPrivacySuppression.store_id == store_id,
        )
        .count()
    )
    return {
        "backup_surfaces": _backup_surfaces(drill_status="not_run"),
        "suppression_ledger_rows": suppression_rows,
        "external_offsite_anchor_required": True,
        "latest_restore_drill": None,
        "restore_verified": False,
        "backup_erasure_verified": False,
        "backup_expiry_reconciled": False,
        "reingestion_suppression_verified": False,
        "blockers": list(_BLOCKERS),
        "fulfillment_complete": False,
    }


def run_shopify_privacy_restore_drill(
    db: Session,
    *,
    externally_stored_hmac: str,
    minimum_records: int,
) -> dict:
    """Reconcile a restored suppression ledger against an external checkpoint.

    The expected HMAC MUST come from an append-only, access-controlled
    location created BEFORE the backup. Its origin cannot be verified by
    this service — the caller attests to it, and that attestation is recorded
    as ``caller_attested`` rather than as independent verification.
    """
    try:
        result = verify_shopify_suppression_restore(
            db,
            externally_stored_hmac=externally_stored_hmac,
            minimum_records=minimum_records,
        )
    except ShopifyRestoreVerificationError:
        # Propagate the stable failure code; never return partial drill state.
        raise
    return {
        "drill": RESTORE_DRILL_NAME,
        "status": "checkpoint_reconciliation_passed",
        "external_ledger_used": True,
        "offsite_anchor_origin": "caller_attested_not_independently_verifiable",
        "recovery_verified": bool(result["recovery_verified"]),
        "total_records": int(result["total_records"]),
        "backup_surfaces": _backup_surfaces(drill_status="reconciliation_passed"),
        "surfaces_reconciled": ["tombstone_offsite_ledger"],
        "evidence_submission_control": "restore_reconciliation",
        "restore_verified": False,
        "backup_erasure_verified": False,
        "provider_erasure_verified": False,
        "blockers": list(_BLOCKERS),
        "fulfillment_complete": False,
    }
