"""Build an owner-authenticated, PII-free review manifest for one case.

The manifest makes the immutable case fields needed by the merchant and legal
templates available without exposing Shopify selectors or minting either of
the two required authorizations. It never represents fulfillment.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from collections.abc import Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyRequest
from .shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError,
    policy_snapshot,
)
from .shopify_privacy_local_execution import preview_local_privacy_execution

_POLICY_DOCUMENT = "DIAGLOB-PRIV-RET-001 v2.0"
_DOCUMENT_PREFIXES = {
    "reviewer_designation": "DIAGLOB-PRIV-DES-001",
    "merchant_instruction": "DIAGLOB-PRIV-INST",
    "legal_review": "DIAGLOB-PRIV-JUR",
}
_KEY_ENVIRONMENTS = {
    "execution": "SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY",
    "legal_review": "SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY",
    "attestation": "SHOPIFY_PRIVACY_ATTESTATION_PUBLIC_KEY",
}
_OPERATIONS = {
    "customers/data_request": "local_export",
    "customers/redact": "local_redaction",
    "shop/redact": "local_redaction",
}


def _decode_public_key(value: str) -> bytes | None:
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True,
        )
        Ed25519PublicKey.from_public_bytes(decoded)
        return decoded
    except (TypeError, ValueError):
        return None


def _key_state(environment: Mapping[str, str], variable: str) -> dict:
    value = environment.get(variable, "")
    if not value:
        return {"state": "missing", "sha256_fingerprint": None}
    decoded = _decode_public_key(value)
    if decoded is None:
        return {"state": "malformed", "sha256_fingerprint": None}
    return {
        "state": "valid",
        "sha256_fingerprint": hashlib.sha256(decoded).hexdigest(),
    }


def _configuration(environment: Mapping[str, str], policy_digest: str) -> dict:
    keys = {
        name: _key_state(environment, variable)
        for name, variable in _KEY_ENVIRONMENTS.items()
    }
    blockers = []
    for name, details in keys.items():
        if details["state"] != "valid":
            blockers.append(f"{name.upper()}_PUBLIC_KEY_{details['state'].upper()}")

    execution_fingerprint = keys["execution"]["sha256_fingerprint"]
    legal_fingerprint = keys["legal_review"]["sha256_fingerprint"]
    independently_reviewed = bool(
        execution_fingerprint and legal_fingerprint
        and execution_fingerprint != legal_fingerprint
    )
    if execution_fingerprint and legal_fingerprint and not independently_reviewed:
        blockers.append("LEGAL_REVIEW_PUBLIC_KEY_NOT_INDEPENDENT")
    if environment.get("SHOPIFY_PRIVACY_PROCESSING_ENABLED") != "true":
        blockers.append("LIVE_PRIVACY_PROCESSING_DISABLED")
    if environment.get("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256") != policy_digest:
        blockers.append("PRIVACY_OPERATOR_POLICY_NOT_BOUND")

    return {
        "key_fingerprints": keys,
        "legal_review_key_independent": independently_reviewed,
        "processing_enabled": environment.get("SHOPIFY_PRIVACY_PROCESSING_ENABLED") == "true",
        "operator_policy_bound": (
            environment.get("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256")
            == policy_digest
        ),
        "blockers": blockers,
        "review_configuration_ready": not blockers,
    }


def build_shopify_privacy_review_manifest(
    db: Session, *, request_id: str, organization_id: int, store_id: int,
    user_id: int, environment: Mapping[str, str] | None = None,
) -> dict:
    """Return review fields and counts, never selectors, PII, or permission."""
    preview = preview_local_privacy_execution(
        db, request_id=request_id, organization_id=organization_id,
        store_id=store_id, user_id=user_id,
    )
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
        ShopifyPrivacyRequest.organization_id == organization_id,
        ShopifyPrivacyRequest.store_id == store_id,
    ).one()
    policy, policy_digest = policy_snapshot()
    try:
        operation = _OPERATIONS[receipt.topic]
    except KeyError as exc:
        raise ShopifyPrivacyExecutionError("PRIVACY_CASE_TOPIC_UNSUPPORTED") from exc
    case_suffix = request_id
    document_ids = {
        "reviewer_designation": _DOCUMENT_PREFIXES["reviewer_designation"],
        "merchant_instruction": f"{_DOCUMENT_PREFIXES['merchant_instruction']}-{case_suffix}",
        "legal_review": f"{_DOCUMENT_PREFIXES['legal_review']}-{case_suffix}",
    }
    manifest = {
        "schema_version": 1,
        "case": {
            "request_id": request_id,
            "organization_id": organization_id,
            "store_id": store_id,
            "topic": receipt.topic,
            "local_operation": operation,
            "shopify_hmac_intake_verified": True,
        },
        "scope": {
            "scope_sha256": preview["scope_sha256"],
            "source_counts": preview["source_counts"],
            "external_processors_verified": False,
        },
        "policy": {
            "document_reference": _POLICY_DOCUMENT,
            "technical_policy_id": policy["policy_id"],
            "sha256": policy_digest,
        },
        "documents": document_ids,
        "configuration": _configuration(
            os.environ if environment is None else environment, policy_digest,
        ),
        "safety": {
            "contains_personal_data": False,
            "contains_shopify_selectors": False,
            "authorizes_execution": False,
            "authorizes_legal_clearance": False,
        },
        "fulfillment_complete": False,
    }
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    manifest["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return manifest
