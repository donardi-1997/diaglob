"""No live AWS or DB access: startup must fail closed on stale checkpoints."""
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.shopify_privacy_execution_authorization import policy_snapshot
from tools.shopify_privacy_startup_guard import (
    PrivacyStartupGuardError, verify_startup_privacy_checkpoint,
)


def configured():
    from app.services.shopify_privacy_attestations import b64encode
    private = Ed25519PrivateKey.generate()
    return {
        "SHOPIFY_PRIVACY_WORM_LEDGER_BUCKET": "isolated-privacy-bucket",
        "SHOPIFY_PRIVACY_WORM_LEDGER_PREFIX": "privacy/restore/checkpoints",
        "SHOPIFY_PRIVACY_WORM_LEDGER_PUBLIC_KEY": b64encode(private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)),
        "SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC": "a" * 64,
        "SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS": "3",
        "SHOPIFY_PRIVACY_SUPPRESSION_KEY": "test-only-stable-secret-of-sufficient-length",
        "SHOPIFY_PRIVACY_PROCESSING_ENABLED": "false",
    }


def anchor():
    return {
        "record_count": 2, "last_checkpoint_hmac": "a" * 64,
        "last_min_records": 3, "last_policy_sha256": policy_snapshot()[1],
    }


def verify_with_mocks(settings, source):
    with patch("tools.shopify_privacy_startup_guard.verify_worm_ledger", return_value=source) as ext:
        with patch("tools.shopify_privacy_startup_guard.verify_shopify_suppression_restore",
                   return_value={"recovery_verified": True}) as restored:
            result = verify_startup_privacy_checkpoint(None, object(), settings=settings)
            return result, ext, restored


def test_startup_reconciles_external_worm_head_even_if_processing_disabled():
    result, external, restored = verify_with_mocks(configured(), anchor())
    assert result["startup_allowed"] is True
    assert result["fulfillment_complete"] is False
    external.assert_called_once()
    restored.assert_called_once_with(None,
        externally_stored_hmac="a" * 64, minimum_records=3)


def test_missing_external_ledger_fails_even_if_local_database_is_empty():
    settings = configured()
    settings.pop("SHOPIFY_PRIVACY_WORM_LEDGER_BUCKET")
    with patch("tools.shopify_privacy_startup_guard.verify_worm_ledger") as ext:
        with pytest.raises(PrivacyStartupGuardError, match="CONFIGURATION_REQUIRED"):
            verify_startup_privacy_checkpoint(None, object(), settings=settings)
        ext.assert_not_called()


@pytest.mark.parametrize("field,value", [
    ("last_checkpoint_hmac", "b" * 64), ("last_min_records", 2),
    ("record_count", 0), ("last_policy_sha256", "c" * 64),
])
def test_old_or_mismatched_worm_checkpoint_blocks_startup(field, value):
    source = anchor() | {field: value}
    with patch("tools.shopify_privacy_startup_guard.verify_worm_ledger", return_value=source):
        with patch("tools.shopify_privacy_startup_guard.verify_shopify_suppression_restore") as restored:
            with pytest.raises(PrivacyStartupGuardError, match="HEAD_MISMATCH"):
                verify_startup_privacy_checkpoint(None, object(), settings=configured())
            restored.assert_not_called()


def test_invalid_signature_or_aws_outage_blocks_startup():
    with patch("tools.shopify_privacy_startup_guard.verify_worm_ledger",
               side_effect=RuntimeError("Synthetic AWS outage")):
        with pytest.raises(PrivacyStartupGuardError, match="EXTERNAL_CHECK_FAILED"):
            verify_startup_privacy_checkpoint(None, object(), settings=configured())


def test_restored_db_older_than_external_checkpoint_blocks_startup():
    with patch("tools.shopify_privacy_startup_guard.verify_worm_ledger", return_value=anchor()):
        with patch("tools.shopify_privacy_startup_guard.verify_shopify_suppression_restore",
                   side_effect=ValueError("rollback")):
            with pytest.raises(PrivacyStartupGuardError, match="TOMBSTONE_MISMATCH"):
                verify_startup_privacy_checkpoint(None, object(), settings=configured())


def test_proposed_dropins_fail_closed_on_every_api_and_worker_restart():
    root = Path(__file__).resolve().parents[2] / "backend" / "ops" / "privacy-gate-dropins"
    for service in ("diaglob-api", "diaglob-automation-worker"):
        path = root / f"{service}.service.d/20-shopify-privacy-worm.conf"
        text = path.read_text(encoding="utf-8")
        assert "[Service]" in text
        assert "ExecStartPre=" in text
        assert "tools.shopify_privacy_startup_guard" in text
        assert "EnvironmentFile=/etc/diaglob/diaglob.env" in text
        assert "OPTIONAL SYSTEMD DROP-IN" in text
