"""Independently signed S3 Object Lock ledger for Shopify tombstone recovery.

This code NEVER auto-creates a bucket, modifies production retention, or changes
application activation. The ledger is an external, separately operated
prerequisite for restoring suppression checkpoints. An IAM-isolated signer
must attest a real checkpoint before use.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy.orm import Session

from .shopify_privacy_restore import verify_shopify_suppression_restore

_CONTEXT = b"diaglob.shopify.privacy.worm-ledger.v1\0"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_PREFIX = re.compile(r"^[a-z0-9][a-z0-9/_-]{0,150}$")
_RECORD_NAME = re.compile(r"^([0-9]{12})-([0-9a-f]{64})\.json$")
_REQUIRED = frozenset((
    "version", "sequence", "recorded_at", "request_id", "checkpoint_hmac",
    "min_records", "policy_sha256", "previous_sha256", "nonce",
))


class ShopifyPrivacyWormLedgerError(ValueError):
    """Stable, non-sensitive failure code."""


def _fail(code: str):
    raise ShopifyPrivacyWormLedgerError(code)


def _encoded(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decoded(s: str) -> bytes:
    return base64.b64decode(s + "=" * (-len(s) % 4), altchars=b"-_", validate=True)


def _canon(doc: dict) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _prefix(prefix: str) -> str:
    if not isinstance(prefix, str) or not _PREFIX.fullmatch(prefix) or ".." in prefix or "//" in prefix:
        _fail("PRIVACY_LEDGER_PREFIX_INVALID")
    return prefix.rstrip("/") + "/"


def _check_immutable_bucket(s3, bucket: str) -> None:
    if not isinstance(bucket, str) or not 3 <= len(bucket) <= 63:
        _fail("PRIVACY_LEDGER_BUCKET_INVALID")
    try:
        versioning = s3.get_bucket_versioning(Bucket=bucket)
        lock = s3.get_object_lock_configuration(Bucket=bucket)
    except Exception as exc:
        raise ShopifyPrivacyWormLedgerError("PRIVACY_LEDGER_BUCKET_NOT_WORM") from exc
    if (versioning.get("Status") != "Enabled"
            or lock.get("ObjectLockConfiguration", {}).get("ObjectLockEnabled") != "Enabled"):
        _fail("PRIVACY_LEDGER_BUCKET_NOT_WORM")


def _list_objects(s3, bucket: str, prefix: str) -> list[dict]:
    rows: list[dict] = []
    key_marker = version_marker = None
    while True:
        params = {"Bucket": bucket, "Prefix": prefix}
        if key_marker is not None:
            params["KeyMarker"] = key_marker
        if version_marker is not None:
            params["VersionIdMarker"] = version_marker
        try:
            response = s3.list_object_versions(**params)
        except Exception as exc:
            raise ShopifyPrivacyWormLedgerError("PRIVACY_LEDGER_LIST_FAILED") from exc
        if response.get("DeleteMarkers"):
            _fail("PRIVACY_LEDGER_DELETE_MARKER_PRESENT")
        rows.extend(response.get("Versions", []))
        if not response.get("IsTruncated"):
            break
        next_key = response.get("NextKeyMarker")
        next_version = response.get("NextVersionIdMarker")
        if not next_key or (next_key, next_version) == (key_marker, version_marker):
            _fail("PRIVACY_LEDGER_PAGINATION_INVALID")
        key_marker, version_marker = next_key, next_version
    if any(not item.get("IsLatest", False) for item in rows):
        _fail("PRIVACY_LEDGER_OBJECT_OVERWRITTEN")
    if len({item.get("Key") for item in rows}) != len(rows):
        _fail("PRIVACY_LEDGER_OBJECT_OVERWRITTEN")
    return rows


def _read_verified(s3, bucket: str, item: dict, prefix: str,
                   public_key: Ed25519PublicKey, now: datetime) -> tuple[dict, str]:
    key = item.get("Key", "")
    name = key[len(prefix):] if key.startswith(prefix) else ""
    match = _RECORD_NAME.fullmatch(name)
    if match is None or not item.get("VersionId"):
        _fail("PRIVACY_LEDGER_OBJECT_KEY_INVALID")
    args = {"Bucket": bucket, "Key": key, "VersionId": item["VersionId"]}
    try:
        response = s3.get_object(**args)
        raw = response["Body"].read()
        retention = s3.get_object_retention(**args)["Retention"]
    except Exception as exc:
        raise ShopifyPrivacyWormLedgerError("PRIVACY_LEDGER_RECORD_UNREADABLE") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != match.group(2) or len(raw) > 4096:
        _fail("PRIVACY_LEDGER_RECORD_HASH_MISMATCH")
    retain_until = retention.get("RetainUntilDate")
    if (retention.get("Mode") != "COMPLIANCE" or not isinstance(retain_until, datetime)
            or retain_until.astimezone(timezone.utc) <= now):
        _fail("PRIVACY_LEDGER_RETENTION_UNVERIFIED")
    try:
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
            _fail("PRIVACY_LEDGER_SCHEMA_INVALID")
        payload = envelope["payload"]
        if not isinstance(payload, dict) or set(payload) != _REQUIRED:
            _fail("PRIVACY_LEDGER_SCHEMA_INVALID")
        public_key.verify(_decoded(envelope["signature"]), _CONTEXT + _canon(payload))
    except ShopifyPrivacyWormLedgerError:
        raise
    except (ValueError, TypeError, KeyError, binascii.Error, InvalidSignature) as exc:
        raise ShopifyPrivacyWormLedgerError("PRIVACY_LEDGER_SIGNATURE_INVALID") from exc
    if (type(payload["version"]) is not int or payload["version"] != 1
            or type(payload["sequence"]) is not int or payload["sequence"] != int(match.group(1))
            or not isinstance(payload["recorded_at"], str)
            or not isinstance(payload["request_id"], str) or not _HASH.fullmatch(payload["request_id"])
            or not isinstance(payload["checkpoint_hmac"], str) or not _HASH.fullmatch(payload["checkpoint_hmac"])
            or not isinstance(payload["policy_sha256"], str) or not _HASH.fullmatch(payload["policy_sha256"])
            or type(payload["min_records"]) is not int or payload["min_records"] < 0
            or not isinstance(payload["nonce"], str) or not re.fullmatch(r"[0-9a-f]{32}", payload["nonce"])
            or not isinstance(payload["previous_sha256"], str)
            or payload["previous_sha256"] and not _HASH.fullmatch(payload["previous_sha256"])):
        _fail("PRIVACY_LEDGER_RECORD_INVALID")
    try:
        created = datetime.fromisoformat(payload["recorded_at"].replace("Z", "+00:00"))
        if created.tzinfo is None or created.astimezone(timezone.utc) > now + timedelta(minutes=5):
            _fail("PRIVACY_LEDGER_TIMESTAMP_INVALID")
    except ValueError as exc:
        raise ShopifyPrivacyWormLedgerError("PRIVACY_LEDGER_TIMESTAMP_INVALID") from exc
    return payload, digest


def verify_worm_ledger(s3, *, bucket: str, prefix: str,
                       public_key: Ed25519PublicKey, now: datetime | None = None) -> dict:
    """Verify ALL versioned objects, signatures, chain, WORM retention and last anchor.

    Detects forks/rewrites/delete-markers. No claims of data erasure or backup
    expiry. A separately authorized single writer and IAM restrictions remain
    essential (S3 Object Lock does not prevent new versions/delete markers).
    """
    prefix = _prefix(prefix)
    now = now or datetime.now(timezone.utc)
    _check_immutable_bucket(s3, bucket)
    items = _list_objects(s3, bucket, prefix)
    records = []
    for item in items:
        payload, digest = _read_verified(s3, bucket, item, prefix, public_key, now)
        records.append((payload["sequence"], payload, digest))
    records.sort(key=lambda x: x[0])
    previous_sha = ""
    for index, (sequence, payload, digest) in enumerate(records, start=1):
        if sequence != index or payload["previous_sha256"] != previous_sha:
            _fail("PRIVACY_LEDGER_CHAIN_INVALID")
        previous_sha = digest
    last = records[-1][1] if records else None
    return {
        "verified": True, "record_count": len(records), "last_record_sha256": previous_sha,
        "last_checkpoint_hmac": last["checkpoint_hmac"] if last else None,
        "last_min_records": last["min_records"] if last else None,
        "last_policy_sha256": last["policy_sha256"] if last else None,
        "last_request_id": last["request_id"] if last else None,
        "data_erasure_certified": False,
    }


def append_worm_checkpoint(s3, *, bucket: str, prefix: str,
                           public_key: Ed25519PublicKey, private_key: Ed25519PrivateKey,
                           request_id: str, checkpoint_hmac: str, min_records: int,
                           policy_sha256: str, retention_days: int,
                           now: datetime | None = None) -> dict:
    """Append single independently signed checkpoint with explicit Object Lock.

    The S3 writer must be restricted by IAM/bucket policy, in an independently
    managed security account where possible. Only opaque HMACs and digests.
    """
    now = now or datetime.now(timezone.utc)
    prefix = _prefix(prefix)
    if (not isinstance(request_id, str) or not _HASH.fullmatch(request_id)
            or not isinstance(checkpoint_hmac, str) or not _HASH.fullmatch(checkpoint_hmac)
            or not isinstance(policy_sha256, str) or not _HASH.fullmatch(policy_sha256)
            or type(min_records) is not int or min_records < 0
            or type(retention_days) is not int or not 30 <= retention_days <= 3650):
        _fail("PRIVACY_LEDGER_INPUT_INVALID")
    signer_pub = private_key.public_key().public_bytes_raw()
    expected_pub = public_key.public_bytes_raw()
    if not hmac.compare_digest(signer_pub, expected_pub):
        _fail("PRIVACY_LEDGER_SIGNER_MISMATCH")
    old = verify_worm_ledger(s3, bucket=bucket, prefix=prefix, public_key=public_key, now=now)
    sequence = old["record_count"] + 1
    payload = {
        "version": 1, "sequence": sequence,
        "recorded_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "request_id": request_id, "checkpoint_hmac": checkpoint_hmac,
        "min_records": min_records, "policy_sha256": policy_sha256,
        "previous_sha256": old["last_record_sha256"], "nonce": secrets.token_hex(16),
    }
    signature = private_key.sign(_CONTEXT + _canon(payload))
    raw = _canon({"payload": payload, "signature": _encoded(signature)})
    digest = hashlib.sha256(raw).hexdigest()
    key = f"{prefix}{sequence:012d}-{digest}.json"
    try:
        s3.put_object(
            Bucket=bucket, Key=key, Body=raw, IfNoneMatch="*",
            ContentType="application/json",
            ContentMD5=base64.b64encode(hashlib.md5(raw).digest()).decode(),
            ServerSideEncryption="AES256",
            ObjectLockMode="COMPLIANCE",
            ObjectLockRetainUntilDate=now + timedelta(days=retention_days),
        )
    except Exception as exc:
        raise ShopifyPrivacyWormLedgerError("PRIVACY_LEDGER_WRITE_FAILED") from exc
    confirmed = verify_worm_ledger(s3, bucket=bucket, prefix=prefix, public_key=public_key, now=now)
    if (confirmed["record_count"] != sequence or
            confirmed["last_record_sha256"] != digest or
            confirmed["last_checkpoint_hmac"] != checkpoint_hmac):
        _fail("PRIVACY_LEDGER_APPEND_NOT_VERIFIED")
    return {
        "stored": True, "sequence": sequence, "record_sha256": digest,
        "record_count": confirmed["record_count"], "retention_mode": "COMPLIANCE",
        "protection_expires_at": (now + timedelta(days=retention_days)).isoformat(),
        "provider_erasure_verified": False, "fulfillment_complete": False,
    }


def verify_restored_db_against_worm_ledger(db: Session, s3, *, bucket: str,
                                          prefix: str, public_key: Ed25519PublicKey) -> dict:
    """Fail closed if no WORM anchor or restored tombstones mismatch latest."""
    anchor = verify_worm_ledger(s3, bucket=bucket, prefix=prefix, public_key=public_key)
    if not anchor["last_checkpoint_hmac"]:
        _fail("PRIVACY_LEDGER_EMPTY")
    result = verify_shopify_suppression_restore(
        db, externally_stored_hmac=anchor["last_checkpoint_hmac"],
        minimum_records=anchor["last_min_records"],
    )
    return {
        "recovery_verified": result["recovery_verified"],
        "ledger_record_count": anchor["record_count"],
        "ledger_head_sha256": anchor["last_record_sha256"],
        "provider_erasure_verified": False,
        "fulfillment_complete": False,
    }
