"""Verify independent, scoped operator permits; never mint or self-approve one.

Private signing keys remain OUTSIDE this application. Execution is off by
default and a permit cannot certify external erasure or global GDPR completion.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

POLICY_PATH = Path(__file__).resolve().parents[3] / "config/shopify-privacy-policy.json"
_HASH = r"^[0-9a-f]{64}$"


class ShopifyPrivacyExecutionError(ValueError):
    """Opaque, non-PII operational errors only."""


class ExecutionPermit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: Literal[1]
    operation: Literal["local_export", "local_redaction"]
    request_id: str = Field(pattern=_HASH)
    organization_id: int = Field(gt=0)
    store_id: int = Field(gt=0)
    policy_sha256: str = Field(pattern=_HASH)
    scope_sha256: str = Field(pattern=_HASH)
    expires_at: int
    legal_hold: Literal[False]
    restore_checkpoint_hmac: str | None = Field(default=None, pattern=_HASH)
    restore_min_records: int | None = Field(default=None, ge=0)

    @field_validator("legal_hold", mode="before")
    @classmethod
    def no_coerced_legal_clearance(cls, value):
        if value is not False:
            raise ValueError("Explicit case clearance required")
        return value


def policy_snapshot() -> tuple[dict, str]:
    try:
        raw = POLICY_PATH.read_bytes()
        return json.loads(raw), hashlib.sha256(raw).hexdigest()
    except (OSError, ValueError, UnicodeError) as exc:
        raise ShopifyPrivacyExecutionError("PRIVACY_POLICY_UNAVAILABLE") from exc


def require_execution_policy() -> dict:
    if os.getenv("SHOPIFY_PRIVACY_PROCESSING_ENABLED") != "true":
        raise ShopifyPrivacyExecutionError("LIVE_PRIVACY_PROCESSING_DISABLED")
    policy, digest = policy_snapshot()
    if os.getenv("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256") != digest:
        raise ShopifyPrivacyExecutionError("PRIVACY_OPERATOR_POLICY_REQUIRED")
    return policy


def _decode(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def verify_execution_permit(
    token: str, *, operation: str, request_id: str, organization_id: int,
    store_id: int, scope_sha256: str,
) -> ExecutionPermit:
    require_execution_policy()
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 4096:
            raise ValueError
        encoded, signature = token.split(".")
        payload = _decode(encoded)
        key = Ed25519PublicKey.from_public_bytes(_decode(
            os.environ.get("SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY", ""),
        ))
        key.verify(_decode(signature), b"diaglob.shopify.privacy.execution.v1\0" + payload)
        permit = ExecutionPermit.model_validate_json(payload)
    except (ValueError, TypeError, InvalidSignature, ValidationError) as exc:
        raise ShopifyPrivacyExecutionError("PRIVACY_EXECUTION_PERMIT_INVALID") from exc
    _, policy_digest = policy_snapshot()
    now = int(time.time())
    if (
        permit.operation != operation or permit.request_id != request_id
        or permit.organization_id != organization_id or permit.store_id != store_id
        or permit.scope_sha256 != scope_sha256 or permit.policy_sha256 != policy_digest
        or not now < permit.expires_at <= now + 86400
    ):
        raise ShopifyPrivacyExecutionError("PRIVACY_EXECUTION_PERMIT_SCOPE_MISMATCH")
    return permit
