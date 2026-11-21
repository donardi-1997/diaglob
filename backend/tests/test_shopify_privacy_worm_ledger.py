"""S3 WORM ledger contract tests with no AWS account, network or real erasure."""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.shopify_privacy_worm_ledger import (
    ShopifyPrivacyWormLedgerError, append_worm_checkpoint,
    verify_restored_db_against_worm_ledger, verify_worm_ledger,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
PUB = Ed25519PrivateKey.generate()
ARGS = {
    "bucket": "isolated-privacy-worm-ledger",
    "prefix": "privacy/restore/checkpoints",
    "public_key": PUB.public_key(),
}
INPUT = {
    "request_id": "a" * 64,
    "checkpoint_hmac": "b" * 64,
    "min_records": 4,
    "policy_sha256": "c" * 64,
    "retention_days": 365,
}


class FakeS3:
    def __init__(self):
        self.lock_enabled = True
        self.versioning_enabled = True
        self.records = []
        self.delete_markers = []

    def get_bucket_versioning(self, *, Bucket):
        return {"Status": "Enabled" if self.versioning_enabled else "Suspended"}

    def get_object_lock_configuration(self, *, Bucket):
        return {"ObjectLockConfiguration": {
            "ObjectLockEnabled": "Enabled" if self.lock_enabled else "Disabled",
        }}

    def list_object_versions(self, *, Bucket, Prefix, KeyMarker=None, VersionIdMarker=None):
        return {
            "IsTruncated": False,
            "Versions": [
                {"Key": row["Key"], "VersionId": row["VersionId"],
                 "IsLatest": row["IsLatest"]}
                for row in self.records if row["Key"].startswith(Prefix)
            ],
            "DeleteMarkers": list(self.delete_markers),
        }

    def put_object(self, *, Bucket, Key, Body, IfNoneMatch, ContentType,
                   ContentMD5, ServerSideEncryption, ObjectLockMode,
                   ObjectLockRetainUntilDate):
        assert IfNoneMatch == "*"
        assert ObjectLockMode == "COMPLIANCE"
        assert ContentType == "application/json"
        assert ServerSideEncryption == "AES256"
        for row in self.records:
            if row["Key"] == Key:
                raise ValueError("duplicate write")
        self.records.append({
            "Key": Key, "VersionId": str(len(self.records) + 1),
            "IsLatest": True, "Body": Body,
            "Retention": {"Mode": ObjectLockMode, "RetainUntilDate": ObjectLockRetainUntilDate},
        })
        return {"VersionId": self.records[-1]["VersionId"]}

    def get_object(self, *, Bucket, Key, VersionId):
        row = next(r for r in self.records if r["Key"] == Key and r["VersionId"] == VersionId)
        return {"Body": io.BytesIO(row["Body"])}

    def get_object_retention(self, *, Bucket, Key, VersionId):
        row = next(r for r in self.records if r["Key"] == Key and r["VersionId"] == VersionId)
        return {"Retention": row["Retention"]}


def append(s3, **overrides):
    return append_worm_checkpoint(s3, **ARGS, private_key=PUB, now=NOW, **(INPUT | overrides))


def verify(s3):
    return verify_worm_ledger(s3, **ARGS, now=NOW)


def test_signed_append_and_multi_checkpoint_chain_are_verifiable():
    s3 = FakeS3()
    first = append(s3)
    assert first["stored"] is True and first["sequence"] == 1
    assert first["fulfillment_complete"] is False
    second = append(s3, request_id="d" * 64,
                    checkpoint_hmac="e" * 64, min_records=5)
    report = verify(s3)
    assert second["sequence"] == 2
    assert report["record_count"] == 2
    assert report["last_checkpoint_hmac"] == "e" * 64
    assert report["last_min_records"] == 5
    assert report["last_record_sha256"] == second["record_sha256"]
    assert report["data_erasure_certified"] is False


@pytest.mark.parametrize("property,value", [
    ("lock_enabled", False), ("versioning_enabled", False),
])
def test_refuses_non_worm_bucket(property, value):
    s3 = FakeS3()
    setattr(s3, property, value)
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="PRIVACY_LEDGER_BUCKET_NOT_WORM"):
        append(s3)
    assert s3.records == []


def test_cannot_verify_tampered_body_even_if_s3_returns_it():
    s3 = FakeS3()
    append(s3)
    s3.records[0]["Body"] += b" "
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="RECORD_HASH_MISMATCH"):
        verify(s3)


def test_expired_lock_or_governance_is_not_accepted():
    s3 = FakeS3()
    append(s3)
    s3.records[0]["Retention"]["Mode"] = "GOVERNANCE"
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="RETENTION_UNVERIFIED"):
        verify(s3)
    s3.records[0]["Retention"]["Mode"] = "COMPLIANCE"
    s3.records[0]["Retention"]["RetainUntilDate"] = NOW - timedelta(seconds=1)
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="RETENTION_UNVERIFIED"):
        verify(s3)


def test_expiring_before_approved_backup_horizon_is_rejected():
    s3 = FakeS3()
    append(s3)
    # Still locked now, but about to expire before the full backup retention
    # window. An old DB snapshot could be restored after the ledger disappears.
    s3.records[0]["Retention"]["RetainUntilDate"] = NOW + timedelta(days=6)
    assert verify_worm_ledger(s3, **ARGS, now=NOW,
                              minimum_remaining_days=5)["verified"] is True
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="RETENTION_HORIZON_INSUFFICIENT"):
        verify_worm_ledger(s3, **ARGS, now=NOW, minimum_remaining_days=7)


@pytest.mark.parametrize("invalid", [-1, 3651, True, 3.5])
def test_invalid_retention_horizon_config_is_rejected(invalid):
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="MINIMUM_RETENTION_INVALID"):
        verify_worm_ledger(FakeS3(), **ARGS, now=NOW,
                           minimum_remaining_days=invalid)


def test_new_version_delete_marker_and_fork_are_detected():
    s3 = FakeS3()
    append(s3)
    original = s3.records[0].copy()
    s3.records[0]["IsLatest"] = False
    s3.records.append({**original, "VersionId": "new-version", "IsLatest": True})
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="OBJECT_OVERWRITTEN"):
        verify(s3)
    s3.records.pop()
    s3.records[0]["IsLatest"] = True
    s3.delete_markers.append({"Key": original["Key"], "VersionId": "deleted"})
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="DELETE_MARKER_PRESENT"):
        verify(s3)


def test_concurrent_fork_rejects_two_records_with_same_sequence():
    s3 = FakeS3()
    append(s3)
    original = dict(s3.records[0])
    # Replaying a second independently signed event under sequence 1 is never
    # silently accepted, even if both objects have valid S3 compliance retention.
    raw = original["Body"]
    s3.records.append({
        **original,
        "Key": original["Key"].replace("-" + hashlib.sha256(raw).hexdigest(),
                                       "-" + ("a" * 64)),
        "VersionId": "second",
    })
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="RECORD_HASH_MISMATCH"):
        verify(s3)


def test_rejects_suppression_count_regression():
    s3 = FakeS3()
    append(s3, min_records=4)
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="COUNT_REGRESSION"):
        append(s3, request_id="e" * 64, checkpoint_hmac="d" * 64, min_records=3)
    assert len(s3.records) == 1


def test_wrong_signer_does_not_create_object():
    s3 = FakeS3()
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="SIGNER_MISMATCH"):
        append_worm_checkpoint(s3, **ARGS, private_key=Ed25519PrivateKey.generate(),
                               now=NOW, **INPUT)
    assert s3.records == []


@pytest.mark.parametrize("change", [
    {"retention_days": 0}, {"retention_days": 3651},
    {"checkpoint_hmac": "invalid"}, {"min_records": -1},
    {"request_id": "not-a-request"}, {"policy_sha256": "x" * 64},
])
def test_rejects_invalid_anchor_inputs(change):
    s3 = FakeS3()
    with pytest.raises(ShopifyPrivacyWormLedgerError, match="INPUT_INVALID"):
        append(s3, **change)
    assert s3.records == []


def test_restored_database_must_match_external_head():
    s3 = FakeS3()
    with patch("app.services.shopify_privacy_worm_ledger.verify_shopify_suppression_restore") as verifier:
        with pytest.raises(ShopifyPrivacyWormLedgerError, match="PRIVACY_LEDGER_EMPTY"):
            verify_restored_db_against_worm_ledger(None, s3, **ARGS)
        verifier.assert_not_called()
    append(s3)
    with patch("app.services.shopify_privacy_worm_ledger.verify_shopify_suppression_restore") as verifier:
        verifier.return_value = {"recovery_verified": True}
        with patch("app.services.shopify_privacy_worm_ledger.verify_worm_ledger", return_value=verify(s3)):
            result = verify_restored_db_against_worm_ledger(None, s3, **ARGS)
        verifier.assert_called_once_with(None,
            externally_stored_hmac="b" * 64, minimum_records=4)
        assert result["recovery_verified"] is True
        assert result["fulfillment_complete"] is False
