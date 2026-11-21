"""Operator-only signing of Shopify privacy program attestations.

Run on the operator workstation, never on the server. The private key must
stay outside the repository (password manager or offline storage). Only the
public key is configured in production as SHOPIFY_PRIVACY_ATTESTATION_PUBLIC_KEY.

    python -m tools.shopify_privacy_attestation keygen --out C:/secure/dir
    python -m tools.shopify_privacy_attestation sign --key C:/secure/dir/attestation.key \
        --control legal_holds --determination approved \
        --evidence C:/private/retention-approval.pdf --attestor-role privacy_owner
    python -m tools.shopify_privacy_attestation status --public-key <b64url>

The evidence file itself is never copied: only its SHA-256 enters the
signed attestation, so evidence may contain material that must not be in Git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.shopify_privacy_attestations import (
    ALLOWED_DETERMINATIONS,
    ATTESTATION_DIR,
    MAX_VALIDITY_SECONDS,
    PUBLIC_KEY_ENV,
    SIGNING_CONTEXT,
    Attestation,
    b64encode,
    evaluate_privacy_program_attestations,
)
from app.services.shopify_privacy_execution_authorization import policy_snapshot


def _keygen(out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    key_path = out / "attestation.key"
    if key_path.exists():
        print("REFUSING_TO_OVERWRITE_EXISTING_KEY", file=sys.stderr)
        return 1
    private = Ed25519PrivateKey.generate()
    key_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    print(json.dumps({"private_key_path": str(key_path), PUBLIC_KEY_ENV: b64encode(public)}))
    return 0


def _sign(args: argparse.Namespace) -> int:
    allowed = ALLOWED_DETERMINATIONS.get(args.control)
    if allowed is None:
        print("UNKNOWN_PROGRAM_CONTROL", file=sys.stderr)
        return 1
    if args.determination not in allowed:
        print(f"DETERMINATION_NOT_ALLOWED: {sorted(allowed)}", file=sys.stderr)
        return 1
    validity = args.valid_days * 86400
    if not 1 <= args.valid_days or validity > MAX_VALIDITY_SECONDS:
        print("VALIDITY_OUT_OF_RANGE", file=sys.stderr)
        return 1
    evidence = Path(args.evidence).read_bytes()
    if not evidence:
        print("EMPTY_EVIDENCE", file=sys.stderr)
        return 1
    private = serialization.load_pem_private_key(Path(args.key).read_bytes(), password=None)
    now = int(time.time())
    attestation = Attestation(
        version=1,
        control=args.control,
        determination=args.determination,
        evidence_sha256=hashlib.sha256(evidence).hexdigest(),
        policy_sha256=policy_snapshot()[1],
        attestor_role=args.attestor_role,
        attested_at=now,
        expires_at=now + validity,
    )
    payload = attestation.model_dump_json().encode("utf-8")
    document = {
        "payload": b64encode(payload),
        "signature": b64encode(private.sign(SIGNING_CONTEXT + payload)),
    }
    ATTESTATION_DIR.mkdir(parents=True, exist_ok=True)
    target = ATTESTATION_DIR / f"{args.control}.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(target), **attestation.model_dump()}))
    return 0


def _status(public_key: str) -> int:
    result = evaluate_privacy_program_attestations(
        environment={PUBLIC_KEY_ENV: public_key},
        # Offline view: data contradictions are checked by the production audit.
        active_processor_controls=(),
    )
    states = {name: value["state"] for name, value in result["controls"].items()}
    print(json.dumps({**{k: v for k, v in result.items() if k != "controls"}, "controls": states},
                     indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("--out", required=True)
    sign = sub.add_parser("sign")
    sign.add_argument("--key", required=True)
    sign.add_argument("--control", required=True)
    sign.add_argument("--determination", required=True)
    sign.add_argument("--evidence", required=True)
    sign.add_argument("--attestor-role", required=True)
    sign.add_argument("--valid-days", type=int, default=365)
    status = sub.add_parser("status")
    status.add_argument("--public-key", required=True)
    args = parser.parse_args()
    if args.command == "keygen":
        return _keygen(Path(args.out))
    if args.command == "sign":
        return _sign(args)
    return _status(args.public_key)


if __name__ == "__main__":
    raise SystemExit(main())
