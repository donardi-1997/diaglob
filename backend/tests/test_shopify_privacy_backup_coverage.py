"""Synthetic SQLite checks for backup-surface coverage and restore drills.

Drills reconcile only the local suppression checkpoint against an externally
held HMAC. A passed drill never upgrades restore, erasure or fulfillment
flags, and the offsite anchor origin is caller-attested rather than verified.
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.shopify_privacy_backlog import (
    RestoreDrillSubmission,
    post_shopify_privacy_restore_drill,
)
from app.db import Base
from app.models import Organization, ShopifyPrivacySuppression, Store
from app.services.shopify_privacy_backup_coverage import (
    ShopifyPrivacyBackupCoverageError,
    inspect_shopify_privacy_backup_coverage,
    run_shopify_privacy_restore_drill,
)
from app.services.shopify_privacy_controls import RESTORE_CONTROLS
from app.services.shopify_privacy_restore import ShopifyRestoreVerificationError
from app.services.shopify_privacy_suppression import _key_fingerprint, _secret

SUPPRESSION_KEY = "synthetic-suppression-key-0123456789abcdef"


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SHOPIFY_PRIVACY_SUPPRESSION_KEY", SUPPRESSION_KEY)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org_a = Organization(name="Org A", slug="org-a", plan="starter")
        org_b = Organization(name="Org B", slug="org-b", plan="starter")
        db.add_all([org_a, org_b])
        db.flush()
        stores = {}
        for suffix, org in (("a", org_a), ("b", org_a), ("c", org_b)):
            store = Store(
                organization_id=org.id, name=f"Store {suffix}",
                slug=f"store-{suffix}", country_code="CO", currency="COP",
                timezone="UTC", shopify_domain=f"{suffix}.myshopify.com",
            )
            db.add(store)
            stores[suffix] = store
        db.flush()

        fingerprint = _key_fingerprint(_secret())
        for store, digest, kind in (
            (stores["a"], "1" * 64, "customer"),
            (stores["a"], "2" * 64, "order"),
            (stores["b"], "3" * 64, "customer"),
        ):
            db.add(ShopifyPrivacySuppression(
                organization_id=store.organization_id,
                store_id=store.id, request_id="r" * 64,
                kind=kind, selector_digest=digest,
                key_fingerprint=fingerprint,
                domain_fingerprint="d" * 64, status="active",
                created_at=datetime.utcnow(),
            ))
        db.commit()
        org_ids = {"a": org_a.id, "b": org_b.id}
        store_ids = {key: store.id for key, store in stores.items()}
        yield db, org_ids, store_ids
    engine.dispose()


def _external_checkpoint(db) -> tuple[str, int]:
    """Simulate the pre-restore snapshot held in an external ledger."""
    rows = db.query(ShopifyPrivacySuppression).all()
    from app.services.shopify_privacy_restore import (
        checkpoint_for_suppression_rows,
    )
    checkpoint = checkpoint_for_suppression_rows(rows, key=_secret())
    return checkpoint["checkpoint_hmac"], checkpoint["total_records"]


def test_backup_coverage_lists_every_restore_control_fail_closed(db):
    db, org_ids, store_ids = db
    result = inspect_shopify_privacy_backup_coverage(
        db, organization_id=org_ids["a"], store_id=store_ids["a"],
    )
    assert [item["control"] for item in result["backup_surfaces"]] == list(
        RESTORE_CONTROLS
    )
    for surface in result["backup_surfaces"]:
        assert surface["state"] == "verification_required"
        assert surface["drill_status"] == "not_run"
        assert surface["independently_verified"] is False
    assert result["suppression_ledger_rows"] == 2
    assert result["latest_restore_drill"] is None
    assert result["external_offsite_anchor_required"] is True
    assert result["restore_verified"] is False
    assert result["backup_erasure_verified"] is False
    assert result["backup_expiry_reconciled"] is False
    assert result["reingestion_suppression_verified"] is False
    assert "BACKUP_RESTORE_COVERAGE_UNVERIFIED" in result["blockers"]
    assert "SUBPROCESSOR_AND_BACKUP_COVERAGE_UNVERIFIED" in result["blockers"]
    assert result["fulfillment_complete"] is False


def test_suppression_ledger_counts_are_scoped_per_store(db):
    db, org_ids, store_ids = db
    store_b = inspect_shopify_privacy_backup_coverage(
        db, organization_id=org_ids["a"], store_id=store_ids["b"],
    )
    assert store_b["suppression_ledger_rows"] == 1
    foreign = inspect_shopify_privacy_backup_coverage(
        db, organization_id=org_ids["b"], store_id=store_ids["c"],
    )
    assert foreign["suppression_ledger_rows"] == 0


def test_backup_coverage_validates_tenant_before_querying(db):
    db, org_ids, store_ids = db
    with pytest.raises(ShopifyPrivacyBackupCoverageError) as bad_org:
        inspect_shopify_privacy_backup_coverage(
            db, organization_id=None, store_id=store_ids["a"],
        )
    assert str(bad_org.value) == "UNVERIFIED_BACKUP_ORGANIZATION_ID"
    with pytest.raises(ShopifyPrivacyBackupCoverageError) as cross_tenant:
        inspect_shopify_privacy_backup_coverage(
            db, organization_id=org_ids["b"], store_id=store_ids["a"],
        )
    assert str(cross_tenant.value) == "BACKUP_SHOP_NOT_FOUND"


def test_restore_drill_passes_against_external_ledger_without_upgrading_flags(
    db,
):
    db, _, _ = db
    expected_hmac, total_records = _external_checkpoint(db)
    assert total_records == 3
    result = run_shopify_privacy_restore_drill(
        db, externally_stored_hmac=expected_hmac, minimum_records=3,
    )
    assert result["status"] == "checkpoint_reconciliation_passed"
    assert result["recovery_verified"] is True
    assert result["total_records"] == 3
    assert result["external_ledger_used"] is True
    assert result["offsite_anchor_origin"] == (
        "caller_attested_not_independently_verifiable"
    )
    assert result["surfaces_reconciled"] == ["tombstone_offsite_ledger"]
    assert result["evidence_submission_control"] == "restore_reconciliation"
    for surface in result["backup_surfaces"]:
        assert surface["drill_status"] == "reconciliation_passed"
        assert surface["independently_verified"] is False
    # A reconciliation pass is NOT restore verification or fulfillment.
    assert result["restore_verified"] is False
    assert result["backup_erasure_verified"] is False
    assert result["provider_erasure_verified"] is False
    assert result["fulfillment_complete"] is False
    assert "BACKUP_RESTORE_COVERAGE_UNVERIFIED" in result["blockers"]


def test_restore_drill_fails_closed_on_rollback_missing_or_invalid_ledger(db):
    db, _, _ = db
    expected_hmac, _ = _external_checkpoint(db)
    with pytest.raises(ShopifyRestoreVerificationError) as rollback:
        run_shopify_privacy_restore_drill(
            db, externally_stored_hmac=expected_hmac, minimum_records=4,
        )
    assert str(rollback.value) == "SUPPRESSION_LEDGER_ROLLBACK"
    with pytest.raises(ShopifyRestoreVerificationError) as mismatch:
        run_shopify_privacy_restore_drill(
            db, externally_stored_hmac="f" * 64, minimum_records=1,
        )
    assert str(mismatch.value) == "SUPPRESSION_CHECKPOINT_MISMATCH"
    with pytest.raises(ShopifyRestoreVerificationError) as missing:
        run_shopify_privacy_restore_drill(
            db, externally_stored_hmac="", minimum_records=0,
        )
    assert str(missing.value) == "EXTERNAL_LEDGER_REQUIRED"


def test_restore_drill_endpoint_requires_internal_secret(db, monkeypatch):
    db, _, _ = db
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-test-internal-secret")
    expected_hmac, _ = _external_checkpoint(db)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as unauthorized:
        post_shopify_privacy_restore_drill(
            body=RestoreDrillSubmission(
                external_hmac=expected_hmac, minimum_records=3,
            ),
            x_internal_secret="wrong", db=db,
        )
    assert unauthorized.value.status_code == 401

    with pytest.raises(HTTPException) as rejected:
        post_shopify_privacy_restore_drill(
            body=RestoreDrillSubmission(
                external_hmac="f" * 64, minimum_records=3,
            ),
            x_internal_secret="synthetic-test-internal-secret", db=db,
        )
    assert rejected.value.status_code == 400

    result = post_shopify_privacy_restore_drill(
        body=RestoreDrillSubmission(
            external_hmac=expected_hmac, minimum_records=3,
        ),
        x_internal_secret="synthetic-test-internal-secret", db=db,
    )
    assert result["recovery_verified"] is True
    assert result["fulfillment_complete"] is False
