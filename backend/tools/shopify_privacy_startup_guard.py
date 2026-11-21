"""Systemd ExecStartPre fail-closed Shopify privacy restore gate.

Install only after a real, approved, independently managed S3 Object Lock
COMPLIANCE ledger exists, with its public key and read-only AWS credentials.
Runs before each API/worker start and never writes to DB or AWS.
"""
from __future__ import annotations

import base64
import binascii
import os
import sys

import boto3
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.orm import Session

from app.services.shopify_privacy_execution_authorization import policy_snapshot
from app.services.shopify_privacy_restore import verify_shopify_suppression_restore
from app.services.shopify_privacy_worm_ledger import verify_worm_ledger


class PrivacyStartupGuardError(ValueError):
    """No PII or infrastructure secrets in error codes."""


def _public_key(value: str) -> Ed25519PublicKey:
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise PrivacyStartupGuardError("PRIVACY_LEDGER_PUBLIC_KEY_INVALID") from exc


def verify_startup_privacy_checkpoint(db: Session, s3, *, settings: dict[str, str]) -> dict:
    """Check external, signed WORM head before allowing service startup.

    Even zero local tombstones are unsafe after a database restore. An empty
    recovered DB and env file may both predate a signed redaction, so no
    shortcut for disabled processing or zero visible suppressions is allowed.
    This gate is installed ONLY after a valid WORM ledger has been provisioned.
    """
    required = (
        "SHOPIFY_PRIVACY_WORM_LEDGER_BUCKET",
        "SHOPIFY_PRIVACY_WORM_LEDGER_PREFIX",
        "SHOPIFY_PRIVACY_WORM_LEDGER_PUBLIC_KEY",
        "SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC",
        "SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS",
        "SHOPIFY_PRIVACY_SUPPRESSION_KEY",
    )
    if any(not settings.get(name) for name in required):
        raise PrivacyStartupGuardError("PRIVACY_EXTERNAL_LEDGER_CONFIGURATION_REQUIRED")
    try:
        minimum = int(settings["SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS"])
        if minimum < 0 or str(minimum) != settings["SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS"]:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise PrivacyStartupGuardError("PRIVACY_LEDGER_RECORD_COUNT_INVALID") from exc
    _, current_policy = policy_snapshot()
    try:
        anchor = verify_worm_ledger(
            s3, bucket=settings["SHOPIFY_PRIVACY_WORM_LEDGER_BUCKET"],
            prefix=settings["SHOPIFY_PRIVACY_WORM_LEDGER_PREFIX"],
            public_key=_public_key(settings["SHOPIFY_PRIVACY_WORM_LEDGER_PUBLIC_KEY"]),
        )
    except Exception as exc:
        raise PrivacyStartupGuardError("PRIVACY_LEDGER_EXTERNAL_CHECK_FAILED") from exc
    if (anchor["record_count"] <= 0
            or anchor["last_checkpoint_hmac"] != settings["SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC"]
            or anchor["last_min_records"] != minimum
            or anchor["last_policy_sha256"] != current_policy):
        raise PrivacyStartupGuardError("PRIVACY_LEDGER_HEAD_MISMATCH")
    try:
        result = verify_shopify_suppression_restore(
            db, externally_stored_hmac=anchor["last_checkpoint_hmac"],
            minimum_records=anchor["last_min_records"],
        )
    except Exception as exc:
        raise PrivacyStartupGuardError("PRIVACY_RESTORE_TOMBSTONE_MISMATCH") from exc
    if result.get("recovery_verified") is not True:
        raise PrivacyStartupGuardError("PRIVACY_RESTORE_TOMBSTONE_MISMATCH")
    return {
        "startup_allowed": True, "ledger_anchored": True,
        "ledger_record_count": anchor["record_count"],
        "fulfillment_complete": False,
    }


def main() -> int:
    from app.db import SessionLocal
    settings = dict(os.environ)
    try:
        s3 = boto3.client(
            "s3", region_name=settings.get("AWS_REGION", settings.get("AWS_DEFAULT_REGION", "us-east-2")),
        )
        with SessionLocal() as db:
            report = verify_startup_privacy_checkpoint(db, s3, settings=settings)
    except Exception:
        # Do not accidentally expose exception strings, bucket names, public
        # keys, credentials, subjects or raw SQL payloads in journald.
        print("PRIVACY_STARTUP_WORM_PREFLIGHT_FAILED", file=sys.stderr)
        return 1
    print("PRIVACY_STARTUP_WORM_PREFLIGHT_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
