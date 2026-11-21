"""Signed, program-level privacy control attestations for Shopify release gates.

An attestation is an operator sign-off made OUTSIDE the application: the
private Ed25519 key never reaches the server, the app only verifies. Each
attestation binds one control to a determination, the SHA-256 of a privately
held evidence artifact, the approved policy digest and an expiry date.

This module never reads customer data, never mutates state and never marks a
privacy request complete. It only decides which program-level release
blockers remain, and it fails closed on any missing, expired, forged,
policy-mismatched or data-contradicted attestation.
"""
from __future__ import annotations

import base64
import json
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .shopify_privacy_controls import PROCESSOR_CONTROLS, RESTORE_CONTROLS, RETENTION_CONTROLS
from .shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError,
    policy_snapshot,
)

ATTESTATION_DIR = Path(__file__).resolve().parents[3] / "config/privacy-attestations"
SIGNING_CONTEXT = b"diaglob.shopify.privacy.attestation.v1\0"
PUBLIC_KEY_ENV = "SHOPIFY_PRIVACY_ATTESTATION_PUBLIC_KEY"
MAX_VALIDITY_SECONDS = 400 * 86400

SUBSCRIPTION_CONTROL = "shopify_compliance_subscriptions"
RETENTION_GROUP = tuple(name for name, _, _ in RETENTION_CONTROLS) + ("legal_holds",)
PROCESSOR_GROUP = tuple(PROCESSOR_CONTROLS)
RESTORE_GROUP = tuple(RESTORE_CONTROLS)

ALLOWED_DETERMINATIONS: dict[str, frozenset[str]] = {
    SUBSCRIPTION_CONTROL: frozenset({"verified"}),
    **{name: frozenset({"approved"}) for name in RETENTION_GROUP},
    **{
        name: frozenset({"erasure_verified", "not_in_use", "no_personal_data_retained"})
        for name in PROCESSOR_GROUP
    },
    **{name: frozenset({"verified"}) for name in RESTORE_GROUP},
}
PROGRAM_CONTROLS = tuple(ALLOWED_DETERMINATIONS)

_HASH = r"^[0-9a-f]{64}$"


class Attestation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1]
    control: str = Field(min_length=3, max_length=64)
    determination: str = Field(min_length=3, max_length=40)
    evidence_sha256: str = Field(pattern=_HASH)
    policy_sha256: str = Field(pattern=_HASH)
    # A role, never a person's name or email: attestations live in Git.
    attestor_role: str = Field(pattern=r"^[a-z][a-z0-9_]{2,40}$")
    attested_at: int = Field(gt=0)
    expires_at: int = Field(gt=0)


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _public_key(environment: Mapping[str, str]) -> Ed25519PublicKey | None:
    raw = environment.get(PUBLIC_KEY_ENV, "")
    if not raw:
        return None
    try:
        return Ed25519PublicKey.from_public_bytes(_b64decode(raw))
    except (ValueError, TypeError):
        return None


def _current_policy_digest() -> str | None:
    try:
        return policy_snapshot()[1]
    except ShopifyPrivacyExecutionError:
        return None


def verify_attestation_document(
    document: Mapping, *, control: str, key: Ed25519PublicKey | None,
    policy_digest: str | None, now: int,
) -> tuple[Attestation | None, str]:
    """Return (attestation, "valid") or (None, stable failure code)."""
    if key is None:
        return None, "ATTESTATION_PUBLIC_KEY_MISSING"
    if policy_digest is None:
        return None, "PRIVACY_POLICY_UNAVAILABLE"
    try:
        payload = _b64decode(document["payload"])
        key.verify(_b64decode(document["signature"]), SIGNING_CONTEXT + payload)
        attestation = Attestation.model_validate_json(payload)
    except (KeyError, TypeError, ValueError, InvalidSignature, ValidationError):
        return None, "ATTESTATION_SIGNATURE_INVALID"
    if attestation.control != control:
        return None, "ATTESTATION_CONTROL_MISMATCH"
    if attestation.determination not in ALLOWED_DETERMINATIONS.get(control, ()):
        return None, "ATTESTATION_DETERMINATION_NOT_ALLOWED"
    if attestation.policy_sha256 != policy_digest:
        return None, "ATTESTATION_POLICY_OUTDATED"
    if not (
        attestation.attested_at <= now < attestation.expires_at
        and attestation.expires_at - attestation.attested_at <= MAX_VALIDITY_SECONDS
    ):
        return None, "ATTESTATION_EXPIRED_OR_NOT_YET_VALID"
    return attestation, "valid"


def load_attestation_documents(directory: Path = ATTESTATION_DIR) -> dict[str, Mapping]:
    documents: dict[str, Mapping] = {}
    for control in PROGRAM_CONTROLS:
        path = directory / f"{control}.json"
        try:
            documents[control] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            documents[control] = {}
    return documents


def evaluate_privacy_program_attestations(
    *,
    environment: Mapping[str, str],
    active_processor_controls: Iterable[str],
    documents: Mapping[str, Mapping] | None = None,
    now: int | None = None,
) -> dict:
    """Per-control state plus the program blockers that remain.

    ``active_processor_controls`` comes from live tenant connections; a
    ``not_in_use`` attestation for an active processor is rejected.
    """
    key = _public_key(environment)
    policy_digest = _current_policy_digest()
    docs = load_attestation_documents() if documents is None else documents
    moment = int(time.time()) if now is None else now
    active = set(active_processor_controls)

    controls: dict[str, dict] = {}
    for control in PROGRAM_CONTROLS:
        document = docs.get(control)
        if document is None:
            controls[control] = {"state": "missing", "determination": None, "expires_at": None}
            continue
        attestation, code = verify_attestation_document(
            document, control=control, key=key, policy_digest=policy_digest, now=moment,
        )
        if attestation is None:
            controls[control] = {"state": code, "determination": None, "expires_at": None}
            continue
        state = "valid"
        if attestation.determination == "not_in_use" and control in active:
            state = "NOT_IN_USE_CONTRADICTED_BY_ACTIVE_CONNECTION"
        controls[control] = {
            "state": state,
            "determination": attestation.determination,
            "expires_at": attestation.expires_at,
        }

    def group_valid(names: Iterable[str]) -> bool:
        return all(controls[name]["state"] == "valid" for name in names)

    return {
        "controls": controls,
        "public_key_configured": key is not None,
        "policy_sha256": policy_digest,
        "subscriptions_verified": controls[SUBSCRIPTION_CONTROL]["state"] == "valid",
        "retention_and_holds_approved": group_valid(RETENTION_GROUP),
        "processors_verified": group_valid(PROCESSOR_GROUP),
        "backup_restore_verified": group_valid(RESTORE_GROUP),
    }


def live_execution_configured(environment: Mapping[str, str], policy_digest: str | None) -> dict:
    """Presence/consistency of execution configuration; values never returned."""
    enabled = environment.get("SHOPIFY_PRIVACY_PROCESSING_ENABLED") == "true"
    policy_bound = bool(policy_digest) and (
        environment.get("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256") == policy_digest
    )
    permit_key = bool(environment.get("SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY"))
    suppression_key = bool(environment.get("SHOPIFY_PRIVACY_SUPPRESSION_KEY"))
    legal_key = environment.get("SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY", "")
    independently_reviewed = bool(legal_key) and legal_key != environment.get("SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY")
    return {
        "export_enabled": enabled and policy_bound and permit_key,
        "redaction_enabled": enabled and policy_bound and permit_key and suppression_key and independently_reviewed,
    }


def privacy_release_blockers(
    *, attestations: dict, execution: dict, signed_receipts: int,
) -> list[str]:
    blockers = []
    if not attestations["subscriptions_verified"]:
        blockers.append("SHOPIFY_ACTIVE_VERSION_SUBSCRIPTIONS_NOT_VERIFIED_BY_THIS_AUDIT")
    if not (attestations["subscriptions_verified"] and signed_receipts > 0):
        blockers.append("REAL_SHOPIFY_DELIVERY_NOT_VERIFIED_BY_THIS_AUDIT")
    if not attestations["retention_and_holds_approved"]:
        blockers.append("LEGAL_RETENTION_AND_HOLDS_NOT_APPROVED")
    if not attestations["processors_verified"]:
        blockers.append("EXTERNAL_PROCESSOR_ERASURE_NOT_VERIFIED")
    if not attestations["backup_restore_verified"]:
        blockers.append("BACKUP_RESTORE_AND_REINGESTION_NOT_VERIFIED")
    if not execution["export_enabled"]:
        blockers.append("LIVE_CUSTOMER_EXPORT_NOT_ENABLED")
    if not execution["redaction_enabled"]:
        blockers.append("LIVE_CUSTOMER_AND_SHOP_REDACTION_NOT_ENABLED")
    return blockers
