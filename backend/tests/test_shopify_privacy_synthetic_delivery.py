"""Synthetic privacy artifact lifecycle: no live delivery or public route."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json

import pytest
from cryptography.fernet import Fernet

from app.services.shopify_privacy_synthetic_delivery import (
    SyntheticPrivacyDeliveryError,
    SyntheticPrivacyDeliveryVault,
)
from app.services.shopify_privacy_synthetic_export import (
    build_encrypted_synthetic_export,
)

REQUEST = "d" * 64
CONTEXT = {
    "request_id": REQUEST,
    "organization_id": 11,
    "store_id": 22,
    "recipient_binding": "authenticated_test_subject_1",
}


@pytest.fixture
def fixture_export():
    key = Fernet.generate_key()
    manifest = {
        "request_id": REQUEST,
        "topic": "customers/data_request",
        "scope_status": "scope_preview_only",
        "export_generated": False,
        "delivery_authorized": False,
        "fulfillment_complete": False,
        "sources": [
            {"name": name, "matching_records": int(name == "orders"),
             "status": "review_required"}
            for name in (
                "customer_store_profiles", "orders", "conversations",
                "conversational_checkouts",
            )
        ],
    }
    artifact = build_encrypted_synthetic_export(
        manifest=manifest,
        records=[
            {"source": "orders", "record": "SYNTHETIC",
             "fields": {"order_number": "SYNTHETIC_DELIVERY_101"}}
        ],
        encryption_key=key,
    )
    return artifact, key


def test_one_time_delivery_returns_only_ciphertext_and_cannot_replay(fixture_export):
    artifact, key = fixture_export
    vault = SyntheticPrivacyDeliveryVault()
    ticket = vault.issue(
        artifact=artifact, fixture_authorized=True, **CONTEXT,
    )
    assert ticket.synthetic_only is True
    assert ticket.merchant_delivery_allowed is False
    assert ticket.expires_in_seconds == 300
    assert ticket.token not in repr(ticket)
    assert "SYNTHETIC_DELIVERY_101" not in repr(ticket)
    received = vault.redeem(
        token=ticket.token, fixture_authorized=True, **CONTEXT,
    )
    assert received.synthetic_only is True
    assert received.fulfillment_complete is False
    assert received.merchant_delivery_allowed is False
    assert received.ciphertext == artifact.ciphertext
    assert received.sha256 == hashlib.sha256(received.ciphertext).hexdigest()
    assert received.ciphertext not in repr(received).encode()
    decoded = json.loads(Fernet(key).decrypt(received.ciphertext))
    assert artifact.request_id == REQUEST
    assert decoded["request_id"] == REQUEST
    assert decoded["records"][0]["fields"]["order_number"] == (
        "SYNTHETIC_DELIVERY_101"
    )
    with pytest.raises(
        SyntheticPrivacyDeliveryError, match="SYNTHETIC_DELIVERY_UNAVAILABLE",
    ):
        vault.redeem(token=ticket.token, fixture_authorized=True, **CONTEXT)


@pytest.mark.parametrize("override", [
    {"request_id": "e" * 64},
    {"organization_id": 999},
    {"store_id": 999},
    {"recipient_binding": "authenticated_test_subject_2"},
])
def test_wrong_subject_tenant_shop_or_request_cannot_consume_token(
    fixture_export, override,
):
    artifact, _ = fixture_export
    vault = SyntheticPrivacyDeliveryVault()
    token = vault.issue(
        artifact=artifact, fixture_authorized=True, **CONTEXT,
    ).token
    bad = dict(CONTEXT, **override)
    with pytest.raises(
        SyntheticPrivacyDeliveryError, match="SYNTHETIC_DELIVERY_UNAVAILABLE",
    ):
        vault.redeem(token=token, fixture_authorized=True, **bad)
    assert vault.redeem(
        token=token, fixture_authorized=True, **CONTEXT,
    ).sha256 == artifact.sha256


def test_expiry_removes_ciphertext_and_cannot_be_recovered(fixture_export):
    artifact, _ = fixture_export
    ticks = [100.0]
    vault = SyntheticPrivacyDeliveryVault(clock=lambda: ticks[0])
    token = vault.issue(
        artifact=artifact, fixture_authorized=True, ttl_seconds=60, **CONTEXT,
    ).token
    ticks[0] = 160.0
    assert vault.purge_expired() == 1
    with pytest.raises(
        SyntheticPrivacyDeliveryError, match="SYNTHETIC_DELIVERY_UNAVAILABLE",
    ):
        vault.redeem(token=token, fixture_authorized=True, **CONTEXT)
    assert vault.purge_expired() == 0


def test_revocation_is_scoped_and_permanent(fixture_export):
    artifact, _ = fixture_export
    vault = SyntheticPrivacyDeliveryVault()
    token = vault.issue(
        artifact=artifact, fixture_authorized=True, **CONTEXT,
    ).token
    assert vault.revoke(
        token=token, fixture_authorized=True,
        **dict(CONTEXT, store_id=999),
    ) is False
    assert vault.revoke(
        token=token, fixture_authorized=True, **CONTEXT,
    ) is True
    assert vault.revoke(
        token=token, fixture_authorized=True, **CONTEXT,
    ) is False
    with pytest.raises(SyntheticPrivacyDeliveryError):
        vault.redeem(token=token, fixture_authorized=True, **CONTEXT)


def test_fixture_must_be_explicitly_authorized_and_never_live(fixture_export):
    artifact, _ = fixture_export
    vault = SyntheticPrivacyDeliveryVault()
    with pytest.raises(SyntheticPrivacyDeliveryError, match="LIVE_DELIVERY_DISABLED"):
        vault.issue(artifact=artifact, **CONTEXT)
    token = vault.issue(
        artifact=artifact, fixture_authorized=True, **CONTEXT,
    ).token
    with pytest.raises(SyntheticPrivacyDeliveryError, match="LIVE_DELIVERY_DISABLED"):
        vault.redeem(token=token, **CONTEXT)
    with pytest.raises(SyntheticPrivacyDeliveryError, match="LIVE_DELIVERY_DISABLED"):
        vault.revoke(token=token, **CONTEXT)


@pytest.mark.parametrize("override", [
    {"synthetic_only": False},
    {"delivery_authorized": True},
    {"fulfillment_complete": True},
    {"sha256": "0" * 64},
    {"ciphertext": b""},
])
def test_invalid_or_tampered_artifact_rejected(fixture_export, override):
    artifact, _ = fixture_export
    with pytest.raises(
        SyntheticPrivacyDeliveryError, match="INVALID_SYNTHETIC_DELIVERY_ARTIFACT",
    ):
        SyntheticPrivacyDeliveryVault().issue(
            artifact=replace(artifact, **override),
            fixture_authorized=True, **CONTEXT,
        )


@pytest.mark.parametrize("ttl", [-1, 0, 59, 901, True, "300"])
def test_ttl_bounds_prevent_permanent_access(fixture_export, ttl):
    artifact, _ = fixture_export
    with pytest.raises(
        SyntheticPrivacyDeliveryError, match="INVALID_SYNTHETIC_DELIVERY_TTL",
    ):
        SyntheticPrivacyDeliveryVault().issue(
            artifact=artifact, fixture_authorized=True,
            ttl_seconds=ttl, **CONTEXT,
        )


def test_bounded_volatile_vault_rejects_unlimited_artifacts(fixture_export):
    artifact, _ = fixture_export
    vault = SyntheticPrivacyDeliveryVault()
    for _ in range(16):
        vault.issue(artifact=artifact, fixture_authorized=True, **CONTEXT)
    with pytest.raises(
        SyntheticPrivacyDeliveryError, match="SYNTHETIC_DELIVERY_CAPACITY_REACHED",
    ):
        vault.issue(artifact=artifact, fixture_authorized=True, **CONTEXT)


def test_concurrent_redeem_has_one_winner(fixture_export):
    artifact, _ = fixture_export
    vault = SyntheticPrivacyDeliveryVault()
    token = vault.issue(
        artifact=artifact, fixture_authorized=True, **CONTEXT,
    ).token

    def attempt(_):
        try:
            vault.redeem(token=token, fixture_authorized=True, **CONTEXT)
        except SyntheticPrivacyDeliveryError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(attempt, range(16)))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 15


def test_invalid_binding_rejected_without_token_lookup(fixture_export):
    artifact, _ = fixture_export
    with pytest.raises(
        SyntheticPrivacyDeliveryError, match="INVALID_SYNTHETIC_DELIVERY_BINDING",
    ):
        SyntheticPrivacyDeliveryVault().issue(
            artifact=artifact, fixture_authorized=True,
            **dict(CONTEXT, recipient_binding="merchant@example.com"),
        )
