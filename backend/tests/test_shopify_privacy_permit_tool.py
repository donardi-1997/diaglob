"""The operator permit tool must mint exactly what the server verifies."""
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.shopify_privacy_attestations import b64encode
from app.services.shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError,
    policy_snapshot,
    verify_execution_permit,
)
from tools.shopify_privacy_permit import mint_permit

CASE = dict(
    operation="local_redaction", request_id="a" * 64, organization_id=3,
    store_id=4, scope_sha256="b" * 64,
    restore_checkpoint_hmac="c" * 64, restore_min_records=2,
)


@pytest.fixture
def private(monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    monkeypatch.setenv("SHOPIFY_PRIVACY_PROCESSING_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256", policy_snapshot()[1])
    monkeypatch.setenv("SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY", b64encode(public))
    return key


def _verify(token, **overrides):
    scope = {k: CASE[k] for k in ("request_id", "organization_id", "store_id", "scope_sha256")}
    scope.update(overrides)
    return verify_execution_permit(token, operation=CASE["operation"], **scope)


def test_minted_permit_is_accepted_by_server_verification(private):
    token = mint_permit(private, now=int(time.time()), ttl_seconds=3600, **CASE)
    permit = _verify(token)
    assert permit.restore_min_records == 2
    assert permit.legal_hold is False


def test_permit_is_bound_to_store_and_scope(private):
    token = mint_permit(private, now=int(time.time()), ttl_seconds=3600, **CASE)
    with pytest.raises(ShopifyPrivacyExecutionError):
        _verify(token, store_id=5)
    with pytest.raises(ShopifyPrivacyExecutionError):
        _verify(token, scope_sha256="d" * 64)


def test_expired_or_overlong_permits_are_refused(private):
    expired = mint_permit(private, now=int(time.time()) - 7200, ttl_seconds=3600, **CASE)
    with pytest.raises(ShopifyPrivacyExecutionError):
        _verify(expired)
    with pytest.raises(ValueError):
        mint_permit(private, now=int(time.time()), ttl_seconds=86400, **CASE)


def test_permit_from_another_key_is_refused(private):
    token = mint_permit(Ed25519PrivateKey.generate(), now=int(time.time()), ttl_seconds=3600, **CASE)
    with pytest.raises(ShopifyPrivacyExecutionError):
        _verify(token)
