"""Synthetic-only encrypted privacy export contract and rejection tests."""
import json
import pytest
from cryptography.fernet import Fernet

from app.services.shopify_privacy_synthetic_export import (
    SyntheticPrivacyExportError,
    build_encrypted_synthetic_export,
)


@pytest.fixture
def manifest():
    return {
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


def test_encrypted_fixture_is_not_plaintext_or_delivery(manifest):
    key = Fernet.generate_key()
    fixture = [{"source": "orders", "record": "SYNTHETIC",
                "fields": {"order_number": "SYNTHETIC_1001"}}]
    result = build_encrypted_synthetic_export(
        manifest=manifest, records=fixture, encryption_key=key,
    )
    assert result.synthetic_only is True
    assert result.delivery_authorized is False
    assert result.fulfillment_complete is False
    assert result.record_count == 1
    assert len(result.sha256) == 64
    assert b"SYNTHETIC_1001" not in result.ciphertext
    decoded = json.loads(Fernet(key).decrypt(result.ciphertext))
    assert decoded["synthetic_only"] is True
    assert decoded["records"] == fixture


@pytest.mark.parametrize("override", [
    {"topic": "customers/redact"},
    {"scope_status": "subject_unresolved"},
    {"delivery_authorized": True},
    {"fulfillment_complete": True},
    {"export_generated": True},
])
def test_reject_invalid_manifest(manifest, override):
    manifest.update(override)
    with pytest.raises(SyntheticPrivacyExportError):
        build_encrypted_synthetic_export(
            manifest=manifest, records=[], encryption_key=Fernet.generate_key(),
        )


def test_reject_real_data_even_if_record_marked_synthetic(manifest):
    with pytest.raises(SyntheticPrivacyExportError, match="NON_SYNTHETIC_EXPORT_BLOCKED"):
        build_encrypted_synthetic_export(
            manifest=manifest,
            records=[{"source": "orders", "record": "SYNTHETIC",
                      "fields": {"email": "buyer@example.com"}}],
            encryption_key=Fernet.generate_key(),
        )


def test_reject_partial_records_and_unknown_source(manifest):
    key = Fernet.generate_key()
    with pytest.raises(SyntheticPrivacyExportError, match="EXPORT_COUNT_MISMATCH"):
        build_encrypted_synthetic_export(manifest=manifest, records=[], encryption_key=key)
    with pytest.raises(SyntheticPrivacyExportError):
        build_encrypted_synthetic_export(
            manifest=manifest,
            records=[{"source": "customers", "record": "SYNTHETIC",
                      "fields": {"name": "SYNTHETIC_TEST"}}],
            encryption_key=key,
        )


def test_reject_incomplete_manifest_and_invalid_key(manifest):
    manifest["sources"].pop()
    with pytest.raises(SyntheticPrivacyExportError, match="INCOMPLETE_EXPORT_MANIFEST"):
        build_encrypted_synthetic_export(
            manifest=manifest, records=[], encryption_key=Fernet.generate_key(),
        )
    manifest["sources"].append({
        "name": "conversational_checkouts", "matching_records": 0,
        "status": "review_required",
    })
    with pytest.raises(SyntheticPrivacyExportError, match="INVALID_EXPORT_ENCRYPTION_KEY"):
        build_encrypted_synthetic_export(
            manifest=manifest,
            records=[{"source": "orders", "record": "SYNTHETIC",
                      "fields": {"id": "SYNTHETIC_1"}}],
            encryption_key=b"invalid",
        )
