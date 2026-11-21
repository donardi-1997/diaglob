"""Signed program attestations clear release blockers only when fully valid."""
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.shopify_privacy_operational_audit as audit
from app.db import Base
from app.services import shopify_privacy_attestations as attest
from app.services.shopify_privacy_execution_authorization import policy_snapshot

NOW = 1_800_000_000
POLICY = policy_snapshot()[1]


def _key():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    return private, attest.b64encode(public)


def _doc(private, control, determination=None, **overrides):
    # Processors sort to "erasure_verified"; other groups have one option.
    determination = determination or sorted(attest.ALLOWED_DETERMINATIONS[control])[0]
    body = {
        "version": 1, "control": control, "determination": determination,
        "evidence_sha256": "e" * 64, "policy_sha256": POLICY,
        "attestor_role": "privacy_owner", "attested_at": NOW - 10,
        "expires_at": NOW + 86400,
    }
    body.update(overrides)
    payload = json.dumps(body).encode()
    return {
        "payload": attest.b64encode(payload),
        "signature": attest.b64encode(private.sign(attest.SIGNING_CONTEXT + payload)),
    }


def _all_docs(private):
    return {name: _doc(private, name) for name in attest.PROGRAM_CONTROLS}


def _evaluate(public, docs, active=()):
    return attest.evaluate_privacy_program_attestations(
        environment={attest.PUBLIC_KEY_ENV: public},
        active_processor_controls=active, documents=docs, now=NOW,
    )


def test_policy_digest_is_identical_for_crlf_and_lf_checkouts(tmp_path, monkeypatch):
    from app.services import shopify_privacy_execution_authorization as auth
    body = b'{\n  "schema_version": 1,\n  "policy_id": "x"\n}\n'
    lf, crlf = tmp_path / "lf.json", tmp_path / "crlf.json"
    lf.write_bytes(body)
    crlf.write_bytes(body.replace(b"\n", b"\r\n"))
    monkeypatch.setattr(auth, "POLICY_PATH", lf)
    lf_digest = auth.policy_snapshot()[1]
    monkeypatch.setattr(auth, "POLICY_PATH", crlf)
    assert auth.policy_snapshot()[1] == lf_digest


def test_complete_valid_set_verifies_every_group():
    private, public = _key()
    result = _evaluate(public, _all_docs(private))
    assert result["subscriptions_verified"] is True
    assert result["retention_and_holds_approved"] is True
    assert result["processors_verified"] is True
    assert result["backup_restore_verified"] is True


def test_missing_public_key_or_attestation_fails_closed():
    private, public = _key()
    assert _evaluate("", _all_docs(private))["processors_verified"] is False
    docs = _all_docs(private)
    docs.pop("legal_holds")
    result = _evaluate(public, docs)
    assert result["controls"]["legal_holds"]["state"] == "missing"
    assert result["retention_and_holds_approved"] is False


@pytest.mark.parametrize("overrides, code", [
    ({"expires_at": NOW - 1}, "ATTESTATION_EXPIRED_OR_NOT_YET_VALID"),
    ({"attested_at": NOW + 100}, "ATTESTATION_EXPIRED_OR_NOT_YET_VALID"),
    ({"expires_at": NOW + 500 * 86400}, "ATTESTATION_EXPIRED_OR_NOT_YET_VALID"),
    ({"policy_sha256": "0" * 64}, "ATTESTATION_POLICY_OUTDATED"),
    ({"control": "cj_supplier"}, "ATTESTATION_CONTROL_MISMATCH"),
    ({"determination": "approved"}, "ATTESTATION_DETERMINATION_NOT_ALLOWED"),
    ({"attestor_role": "Jane Doe <jane@example.com>"}, "ATTESTATION_SIGNATURE_INVALID"),
])
def test_invalid_attestations_are_rejected(overrides, code):
    private, public = _key()
    docs = _all_docs(private)
    fields = {"determination": "not_in_use", **overrides}
    signed_control = fields.pop("control", "whatsapp_provider")
    document = _doc(private, signed_control, **fields)
    docs["whatsapp_provider"] = document
    result = _evaluate(public, docs)
    assert result["controls"]["whatsapp_provider"]["state"] == code
    assert result["processors_verified"] is False


def test_signature_from_another_key_is_rejected():
    private, public = _key()
    other, _ = _key()
    docs = _all_docs(private)
    docs[attest.SUBSCRIPTION_CONTROL] = _doc(other, attest.SUBSCRIPTION_CONTROL)
    result = _evaluate(public, docs)
    assert result["controls"][attest.SUBSCRIPTION_CONTROL]["state"] == "ATTESTATION_SIGNATURE_INVALID"


def test_not_in_use_is_contradicted_by_live_connection():
    private, public = _key()
    docs = _all_docs(private)
    docs["aws_bedrock"] = _doc(private, "aws_bedrock", determination="not_in_use")
    result = _evaluate(public, docs, active={"aws_bedrock"})
    assert result["controls"]["aws_bedrock"]["state"] == (
        "NOT_IN_USE_CONTRADICTED_BY_ACTIVE_CONNECTION"
    )
    assert result["processors_verified"] is False
    # An erasure determination is valid for an active processor.
    docs["aws_bedrock"] = _doc(private, "aws_bedrock", determination="erasure_verified")
    assert _evaluate(public, docs, active={"aws_bedrock"})["processors_verified"] is True


def _env(public, **extra):
    return {
        "SHOPIFY_CLIENT_SECRET": "synthetic",
        "SHOPIFY_TOKEN_ENCRYPTION_KEY": "synthetic",
        attest.PUBLIC_KEY_ENV: public,
        **extra,
    }


def _audit(monkeypatch, docs, env):
    monkeypatch.setattr(attest, "load_attestation_documents", lambda: docs)
    monkeypatch.setattr(attest.time, "time", lambda: NOW)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            return audit.summarize_shopify_privacy_operations(db, environment=env)
    finally:
        engine.dispose()


def test_attestations_without_execution_config_keep_live_blockers(monkeypatch):
    private, public = _key()
    report = _audit(monkeypatch, _all_docs(private), _env(public))
    assert report["released_shopify_subscription_verified"] is True
    # No signed receipts exist yet, so real delivery stays unverified.
    assert report["privacy_fulfillment_release_blockers"] == [
        "REAL_SHOPIFY_DELIVERY_NOT_VERIFIED_BY_THIS_AUDIT",
        "LIVE_CUSTOMER_EXPORT_NOT_ENABLED",
        "LIVE_CUSTOMER_AND_SHOP_REDACTION_NOT_ENABLED",
    ]
    assert report["privacy_fulfillment_release_ready"] is False
    assert report["data_export_or_erasure_fulfilled"] is False


def test_execution_requires_the_exact_approved_policy_digest(monkeypatch):
    private, public = _key()
    env = _env(
        public,
        SHOPIFY_PRIVACY_PROCESSING_ENABLED="true",
        SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256="0" * 64,
        SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY="synthetic",
        SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY="independent-synthetic",
        SHOPIFY_PRIVACY_SUPPRESSION_KEY="synthetic",
    )
    blockers = _audit(monkeypatch, _all_docs(private), env)["privacy_fulfillment_release_blockers"]
    assert "LIVE_CUSTOMER_EXPORT_NOT_ENABLED" in blockers
    env["SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256"] = POLICY
    blockers = _audit(monkeypatch, _all_docs(private), env)["privacy_fulfillment_release_blockers"]
    assert blockers == ["REAL_SHOPIFY_DELIVERY_NOT_VERIFIED_BY_THIS_AUDIT"]
    env.pop("SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY")
    blockers = _audit(monkeypatch, _all_docs(private), env)["privacy_fulfillment_release_blockers"]
    assert "LIVE_CUSTOMER_AND_SHOP_REDACTION_NOT_ENABLED" in blockers
    env["SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY"] = env["SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY"]
    blockers = _audit(monkeypatch, _all_docs(private), env)["privacy_fulfillment_release_blockers"]
    assert "LIVE_CUSTOMER_AND_SHOP_REDACTION_NOT_ENABLED" in blockers
