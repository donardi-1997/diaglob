"""Offline signer for independent per-case Shopify legal clearance.

Use ONLY after an authorized reviewer verifies a real merchant instruction,
the case-specific absence of a blocking legal hold, and approved retention
exceptions. The private key must NEVER be deployed to the application.
Evidence files must remain in a restricted vault, never be uploaded to Git.

Example from backend:
 python -m tools.shopify_privacy_legal_clearance keygen --out /secure/legal-review
 python -m tools.shopify_privacy_legal_clearance sign --key /secure/legal-review/clearance.key \
   --request-id <opaque-64-hex> --organization-id 1 --store-id 2 \
   --scope-sha256 <sha256> --merchant-instruction /private/instruction.pdf \
   --legal-review /private/legal-case-decision.pdf \
   --reviewer-role privacy_counsel --legal-hold-cleared
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.shopify_privacy_attestations import b64encode
from app.services.shopify_privacy_execution_authorization import policy_snapshot
from app.services.shopify_privacy_legal_clearance import (
    CaseLegalClearance, MAX_TTL_SECONDS, _SIGNING_CONTEXT,
)

ROLES = ("privacy_counsel", "merchant_controller", "authorized_privacy_reviewer")


def _evidence_sha256(path: Path) -> str:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("LEGAL_EVIDENCE_FILE_MISSING_OR_EMPTY")
    digest = hashlib.sha256()
    with path.open("rb") as fd:
        for block in iter(lambda: fd.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sign_case_clearance(private: Ed25519PrivateKey, *, now: int,
                        ttl_seconds: int, **fields) -> str:
    if not 60 <= ttl_seconds < MAX_TTL_SECONDS:
        raise ValueError("LEGAL_CLEARANCE_TTL_OUT_OF_RANGE")
    decision = CaseLegalClearance(
        version=1, policy_sha256=policy_snapshot()[1],
        issued_at=now, expires_at=now + ttl_seconds,
        legal_hold=False, **fields,
    )
    payload = decision.model_dump_json().encode("utf-8")
    return b64encode(payload) + "." + b64encode(private.sign(_SIGNING_CONTEXT + payload))


def _keygen(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    key_file = out / "clearance.key"
    if key_file.exists():
        print("REFUSING_TO_OVERWRITE_EXISTING_LEGAL_REVIEW_KEY", file=sys.stderr)
        return 1
    key = Ed25519PrivateKey.generate()
    key_file.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    if os.name != "nt":
        os.chmod(key_file, 0o600)
    pub = b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    ))
    print("SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY=" + pub)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("--out", required=True)
    sign = sub.add_parser("sign")
    sign.add_argument("--key", required=True)
    sign.add_argument("--request-id", required=True)
    sign.add_argument("--organization-id", type=int, required=True)
    sign.add_argument("--store-id", type=int, required=True)
    sign.add_argument("--scope-sha256", required=True)
    sign.add_argument("--merchant-instruction", required=True)
    sign.add_argument("--legal-review", required=True)
    sign.add_argument("--reviewer-role", choices=ROLES, required=True)
    sign.add_argument("--legal-hold-cleared", action="store_true",
                      help="Reviewer declares that legal holds were actually checked and cleared for this exact scope")
    sign.add_argument("--ttl-minutes", type=int, default=60)
    args = parser.parse_args()
    if args.command == "keygen":
        return _keygen(Path(args.out))
    if not args.legal_hold_cleared:
        raise SystemExit("EXPLICIT_LEGAL_REVIEW_SIGNOFF_REQUIRED")
    evidence = {
        "merchant_instruction_evidence_sha256": _evidence_sha256(Path(args.merchant_instruction)),
        "legal_review_evidence_sha256": _evidence_sha256(Path(args.legal_review)),
    }
    private = serialization.load_pem_private_key(Path(args.key).read_bytes(), password=None)
    token = sign_case_clearance(
        private, now=int(time.time()), ttl_seconds=args.ttl_minutes * 60,
        request_id=args.request_id, organization_id=args.organization_id,
        store_id=args.store_id, scope_sha256=args.scope_sha256,
        reviewer_role=args.reviewer_role, **evidence,
    )
    # Treat the signed token as a short-lived bearer authorization. Never print
    # it into a public ticket, PR, CI log, or chat.
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
