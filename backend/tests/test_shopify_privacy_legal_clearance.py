"""Per-case legal clearance must be independently signed and tightly scoped.

Synthetic metadata only. No legal approvals, customer data, or live deletion.
"""
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.shopify_privacy_attestations import b64encode
from app.services.shopify_privacy_execution_authorization import ShopifyPrivacyExecutionError
from app.services.shopify_privacy_legal_clearance import verify_case_legal_clearance
from tools.shopify_privacy_legal_clearance import sign_case_clearance


CASE = dict(
    request_id="a" * 64, organization_id=3, store_id=4,
    scope_sha256="b" * 64,
    merchant_instruction_evidence_sha256="c" * 64,
    legal_review_evidence_sha256="d" * 64,
    reviewer_role="privacy_counsel",
)


def public(key):
    return b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    ))


@pytest.fixture
def reviewer(monkeypatch):
    legal_key, executor = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    monkeypatch.setenv("SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY", public(legal_key))
    monkeypatch.setenv("SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY", public(executor))
    return legal_key, executor


def signed(reviewer, *, now=None, **overrides):
    data = dict(CASE)
    data.update(overrides)
    return sign_case_clearance(
        reviewer[0], now=int(time.time()) if now is None else now,
        ttl_seconds=600, **data,
    )


def verify(token, **overrides):
    scope = {k: CASE[k] for k in ("request_id", "organization_id", "store_id", "scope_sha256")}
    scope.update(overrides)
    return verify_case_legal_clearance(token, **scope)


def test_independently_signed_review_is_accepted_with_two_evidence_hashes(reviewer):
    result = verify(signed(reviewer))
    assert result.legal_hold is False
    assert result.merchant_instruction_evidence_sha256 == "c" * 64
    assert result.legal_review_evidence_sha256 == "d" * 64


def test_wrong_case_store_or_scope_is_rejected(reviewer):
    token = signed(reviewer)
    for changes in ({"request_id": "e" * 64}, {"store_id": 5},
                    {"organization_id": 6}, {"scope_sha256": "f" * 64}):
        with pytest.raises(ShopifyPrivacyExecutionError, match="SCOPE_MISMATCH"):
            verify(token, **changes)


def test_expired_or_overlong_clearance_is_rejected(reviewer):
    token = signed(reviewer, now=int(time.time()) - 3600)
    with pytest.raises(ShopifyPrivacyExecutionError, match="SCOPE_MISMATCH"):
        verify(token)
    with pytest.raises(ValueError, match="TTL_OUT_OF_RANGE"):
        sign_case_clearance(reviewer[0], now=int(time.time()),
                            ttl_seconds=86400, **CASE)


def test_untrusted_signing_key_and_missing_independence_are_rejected(reviewer, monkeypatch):
    other = Ed25519PrivateKey.generate()
    token = sign_case_clearance(other, now=int(time.time()), ttl_seconds=600, **CASE)
    with pytest.raises(ShopifyPrivacyExecutionError, match="CLEARANCE_INVALID"):
        verify(token)

    monkeypatch.setenv("SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY", public(reviewer[1]))
    with pytest.raises(ShopifyPrivacyExecutionError, match="INDEPENDENCE_REQUIRED"):
        verify(signed(reviewer))


def test_missing_evidence_or_clearance_is_rejected(reviewer):
    with pytest.raises(ValueError):
        signed(reviewer, legal_review_evidence_sha256="invalid")
    with pytest.raises(ShopifyPrivacyExecutionError, match="CLEARANCE_REQUIRED"):
        verify(None)
