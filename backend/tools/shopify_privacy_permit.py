"""Operator-only signing of per-case Shopify privacy execution permits.

Run on the operator workstation; the private key never reaches the server,
which only holds SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY. Inputs come from the
store owner's preview of the exact case (scope digest and, for redactions,
the planned restore checkpoint). A permit is valid for at most 24 hours and
for one operation on one request, tenant and store.

    python -m tools.shopify_privacy_permit keygen --out C:/secure/permits
    python -m tools.shopify_privacy_permit sign --key C:/secure/permits/permit.key \
        --operation local_redaction --request-id <64 hex> --organization-id 1 \
        --store-id 2 --scope-sha256 <64 hex> \
        --restore-checkpoint-hmac <64 hex> --restore-min-records 3

Confirm the case has no legal hold before signing: the permit asserts it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.shopify_privacy_attestations import b64encode
from app.services.shopify_privacy_execution_authorization import (
    ExecutionPermit,
    policy_snapshot,
)

SIGNING_CONTEXT = b"diaglob.shopify.privacy.execution.v1\0"
MAX_TTL_SECONDS = 86400


def mint_permit(private: Ed25519PrivateKey, *, now: int, ttl_seconds: int, **fields) -> str:
    if not 60 <= ttl_seconds < MAX_TTL_SECONDS:
        raise ValueError("PERMIT_TTL_OUT_OF_RANGE")
    permit = ExecutionPermit(
        version=1, policy_sha256=policy_snapshot()[1], expires_at=now + ttl_seconds,
        legal_hold=False, **fields,
    )
    payload = permit.model_dump_json().encode("utf-8")
    return b64encode(payload) + "." + b64encode(private.sign(SIGNING_CONTEXT + payload))


def append_checkpoint_ledger(ledger: Path, *, request_id: str, checkpoint_hmac: str,
                             min_records: int, now: int) -> None:
    """Append-only, off-server record of every planned tombstone checkpoint.

    The server's own checkpoint (env + database) is inside the same instance
    snapshot, so a restore can roll both back consistently. After any restore,
    compare the restored database with the LAST entry of this ledger
    (tools.shopify_privacy_restore_check verify) before resuming ingestion.
    Contains only opaque digests and counts, never customer data.
    """
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "recorded_at": now, "request_id": request_id,
            "checkpoint_hmac": checkpoint_hmac, "min_records": min_records,
        }, sort_keys=True) + "\n")


def _keygen(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    key_path = out / "permit.key"
    if key_path.exists():
        print("REFUSING_TO_OVERWRITE_EXISTING_KEY", file=sys.stderr)
        return 1
    private = Ed25519PrivateKey.generate()
    key_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    print(json.dumps({"private_key_path": str(key_path),
                      "SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY": b64encode(public)}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("--out", required=True)
    sign = sub.add_parser("sign")
    sign.add_argument("--key", required=True)
    sign.add_argument("--operation", required=True, choices=["local_export", "local_redaction", "shop_knowledge_erasure", "shop_copilot_erasure"])
    sign.add_argument("--request-id", required=True)
    sign.add_argument("--organization-id", type=int, required=True)
    sign.add_argument("--store-id", type=int, required=True)
    sign.add_argument("--scope-sha256", required=True)
    sign.add_argument("--restore-checkpoint-hmac")
    sign.add_argument("--restore-min-records", type=int)
    sign.add_argument("--ttl-minutes", type=int, default=60)
    sign.add_argument("--ledger", help="Off-server checkpoint ledger; defaults next to the key")
    args = parser.parse_args()
    if args.command == "keygen":
        return _keygen(Path(args.out))
    if args.operation == "local_redaction" and (
        args.restore_checkpoint_hmac is None or args.restore_min_records is None
    ):
        print("REDACTION_REQUIRES_PLANNED_RESTORE_CHECKPOINT", file=sys.stderr)
        return 1
    private = serialization.load_pem_private_key(Path(args.key).read_bytes(), password=None)
    now = int(time.time())
    token = mint_permit(
        private, now=now, ttl_seconds=args.ttl_minutes * 60,
        operation=args.operation, request_id=args.request_id,
        organization_id=args.organization_id, store_id=args.store_id,
        scope_sha256=args.scope_sha256,
        restore_checkpoint_hmac=args.restore_checkpoint_hmac,
        restore_min_records=args.restore_min_records,
    )
    if args.restore_checkpoint_hmac is not None:
        ledger = Path(args.ledger) if args.ledger else Path(args.key).parent / "checkpoint-ledger.jsonl"
        append_checkpoint_ledger(
            ledger, request_id=args.request_id, checkpoint_hmac=args.restore_checkpoint_hmac,
            min_records=args.restore_min_records, now=now,
        )
        print(f"LEDGER_APPENDED={ledger}", file=sys.stderr)
    # The token is a short-lived bearer credential: hand it to the store
    # owner's execution request only; never paste it into tickets or chat.
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
