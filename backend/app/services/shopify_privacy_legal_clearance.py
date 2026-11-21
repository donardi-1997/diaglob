"""Verify an independently signed, per-case legal clearance for Shopify redaction.

A signed clearance binds reviewed evidence references to exactly one verified
receipt/store/manifest. The signer and evidence owner remain responsible for
the truth of the legal decision; cryptography only verifies provenance/scope.
No secret signing keys or unredacted legal evidence belong on this server.
"""
from __future__ import annotations

import base64
import binascii
import os
import time
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError,
    policy_snapshot,
)

_SIGNING_CONTEXT = b"diaglob.shopify.privacy.legal-clearance.v1\0"
_SHA = r"^[0-9a-f]{64}$"
MAX_TTL_SECONDS = 86400


class CaseLegalClearance(BaseModel):
    """Minimal non-PII legal decision whose signature can be checked offline."""
    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    request_id: str = Field(pattern=_SHA)
    organization_id: int = Field(gt=0)
    store_id: int = Field(gt=0)
    scope_sha256: str = Field(pattern=_SHA)
    policy_sha256: str = Field(pattern=_SHA)
    merchant_instruction_evidence_sha256: str = Field(pattern=_SHA)
    legal_review_evidence_sha256: str = Field(pattern=_SHA)
    reviewer_role: Literal["privacy_counsel", "merchant_controller", "authorized_privacy_reviewer"]
    issued_at: int = Field(gt=0)
    expires_at: int = Field(gt=0)
    legal_hold: Literal[False]

    @field_validator("legal_hold", mode="before")
    @classmethod
    def legal_hold_must_be_explicit_false(cls, value):
        if value is not False:
            raise ValueError("Explicit legal clearance required")
        return value


def _decode(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def verify_case_legal_clearance(
    token: str | None, *, request_id: str, organization_id: int,
    store_id: int, scope_sha256: str,
) -> CaseLegalClearance:
    """Fail closed on absent, forged, stale, wrong-scope or self-approved decisions."""
    if not isinstance(token, str) or not 1 <= len(token) <= 4096:
        raise ShopifyPrivacyExecutionError("PRIVACY_CASE_LEGAL_CLEARANCE_REQUIRED")
    review_key = os.getenv("SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY", "")
    execution_key = os.getenv("SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY", "")
    if not review_key or not execution_key:
        raise ShopifyPrivacyExecutionError("PRIVACY_LEGAL_REVIEW_KEY_REQUIRED")
    try:
        review_bytes = _decode(review_key)
        execution_bytes = _decode(execution_key)
        if review_bytes == execution_bytes:
            raise ShopifyPrivacyExecutionError("PRIVACY_LEGAL_REVIEW_INDEPENDENCE_REQUIRED")
        public = Ed25519PublicKey.from_public_bytes(review_bytes)
        encoded, signed = token.split(".")
        raw = _decode(encoded)
        public.verify(_decode(signed), _SIGNING_CONTEXT + raw)
        clearance = CaseLegalClearance.model_validate_json(raw)
    except ShopifyPrivacyExecutionError:
        raise
    except (ValueError, TypeError, binascii.Error, InvalidSignature, ValidationError) as exc:
        raise ShopifyPrivacyExecutionError("PRIVACY_CASE_LEGAL_CLEARANCE_INVALID") from exc

    _, policy_digest = policy_snapshot()
    now = int(time.time())
    if (
        clearance.request_id != request_id
        or clearance.organization_id != organization_id
        or clearance.store_id != store_id
        or clearance.scope_sha256 != scope_sha256
        or clearance.policy_sha256 != policy_digest
        or not clearance.issued_at <= now < clearance.expires_at
        or not 60 <= clearance.expires_at - clearance.issued_at < MAX_TTL_SECONDS
    ):
        raise ShopifyPrivacyExecutionError("PRIVACY_CASE_LEGAL_CLEARANCE_SCOPE_MISMATCH")
    return clearance
