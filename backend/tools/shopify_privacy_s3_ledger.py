"""Operator CLI for independently signed Shopify restore anchors in S3 WORM.

Does not create buckets, set IAM policies, modify DBs, or activate live
processing. Run signer commands from an independently controlled workstation,
NOT inside the Lightsail snapshot/DB backup boundary. Never commit keys.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import boto3
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.services.shopify_privacy_execution_authorization import policy_snapshot
from app.services.shopify_privacy_worm_ledger import (
    _decoded, _encoded, append_worm_checkpoint, verify_restored_db_against_worm_ledger,
    verify_worm_ledger,
)


def _public(key: Ed25519PrivateKey) -> str:
    return _encoded(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    ))


def _keygen(out: Path) -> dict:
    if out.exists():
        raise SystemExit("REFUSING_TO_OVERWRITE_WORM_LEDGER_KEY")
    out.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    out.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    if os.name != "nt":
        os.chmod(out, 0o600)
    return {"private_key_written": True, "public_key_b64url": _public(key)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    make = sub.add_parser("keygen")
    make.add_argument("--out", type=Path, required=True)
    for name in ("verify", "append", "verify-restore"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--bucket", required=True)
        cmd.add_argument("--prefix", required=True)
        cmd.add_argument("--region", default="us-east-2")
        cmd.add_argument("--public-key", required=True, help="Base64url Ed25519 public key; not secret")
        if name == "append":
            cmd.add_argument("--private-key", type=Path, required=True)
            cmd.add_argument("--checkpoint", type=Path, required=True,
                             help="Restricted JSON from shopify_privacy_restore_check snapshot")
            cmd.add_argument("--request-id", required=True)
            cmd.add_argument("--retention-days", required=True, type=int)
    args = parser.parse_args()
    if args.cmd == "keygen":
        print(json.dumps(_keygen(args.out), sort_keys=True))
        return 0
    try:
        public = Ed25519PublicKey.from_public_bytes(_decoded(args.public_key))
    except (ValueError, TypeError) as exc:
        raise SystemExit("PRIVACY_LEDGER_PUBLIC_KEY_INVALID") from exc
    s3 = boto3.client("s3", region_name=args.region)
    if args.cmd == "verify":
        report = verify_worm_ledger(s3, bucket=args.bucket, prefix=args.prefix,
                                    public_key=public)
    elif args.cmd == "verify-restore":
        from app.db import SessionLocal
        with SessionLocal() as db:
            report = verify_restored_db_against_worm_ledger(
                db, s3, bucket=args.bucket, prefix=args.prefix, public_key=public,
            )
    else:
        try:
            checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
            if (not isinstance(checkpoint, dict)
                    or set(checkpoint) != {"version", "total_records", "checkpoint_hmac", "recovery_verified"}
                    or checkpoint.get("version") != 1
                    or checkpoint.get("recovery_verified") is not False):
                raise ValueError
        except (OSError, ValueError) as exc:
            raise SystemExit("PRIVACY_CHECKPOINT_REVIEWED_FILE_REQUIRED") from exc
        try:
            signer = serialization.load_pem_private_key(
                args.private_key.read_bytes(), password=None,
            )
        except (OSError, ValueError, TypeError) as exc:
            raise SystemExit("PRIVACY_LEDGER_SIGNING_KEY_INVALID") from exc
        if not isinstance(signer, Ed25519PrivateKey):
            raise SystemExit("PRIVACY_LEDGER_SIGNING_KEY_INVALID")
        report = append_worm_checkpoint(
            s3, bucket=args.bucket, prefix=args.prefix, public_key=public,
            private_key=signer, request_id=args.request_id,
            checkpoint_hmac=checkpoint["checkpoint_hmac"],
            min_records=checkpoint["total_records"],
            policy_sha256=policy_snapshot()[1],
            retention_days=args.retention_days,
        )
    # Never output customer identities, raw selectors, tokens or private keys.
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
