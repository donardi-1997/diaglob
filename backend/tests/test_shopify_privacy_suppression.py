"""Hashed Shopify privacy suppression: isolation, signed stage, replay guard."""
import json
from datetime import datetime
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    CommerceConnection, Customer, CustomerStoreProfile, Order, Organization,
    ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest, ShopifyPrivacySuppression,
    Store,
)
from app.api.shopify_privacy_backlog import (
    prepare_shopify_privacy_suppression_case,
    get_shopify_privacy_suppression_case,
)
from app.services.shopify_privacy_suppression import (
    ShopifySuppressionError,
    activate_synthetic_privacy_suppressions,
    evaluate_shopify_privacy_suppression,
    inspect_shopify_privacy_suppressions,
    prepare_shopify_privacy_suppressions,
)
from app.services.shopify_webhook_service import (
    ShopifyWebhookError, process_shopify_order_webhook,
)
from app.shopify_security import encrypt_shopify_secret


RECEIPT = "e" * 64


@pytest.fixture
def sandbox(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("SHOPIFY_PRIVACY_SUPPRESSION_KEY", "synthetic-persistent-tombstone-key-test-only-123456789")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Suppression test", slug="suppression-test", plan="starter")
        db.add(org)
        db.flush()
        stores = []
        for n in (1, 2):
            store = Store(
                organization_id=org.id, name=f"Shop {n}",
                slug=f"suppression-shop-{n}", country_code="CO",
                currency="COP", timezone="UTC",
                shopify_domain=f"suppression-shop-{n}.myshopify.com",
            )
            db.add(store)
            stores.append(store)
        db.flush()
        connections = []
        for store in stores:
            conn = CommerceConnection(
                organization_id=org.id, store_id=store.id, provider="shopify",
                external_store_url=store.shopify_domain,
                status="connected",
            )
            db.add(conn)
            connections.append(conn)
        receipt = ShopifyPrivacyRequest(
            request_id=RECEIPT, topic="customers/redact",
            shop_id="synthetic-shopify-shop-id", shop_domain=stores[0].shopify_domain,
            organization_id=org.id, store_id=stores[0].id,
            selector_encrypted=encrypt_shopify_secret(json.dumps({
                "customer": {"id": 700, "email": "private@example.com"},
                "orders_to_redact": [101],
            })),
            status="pending_policy_review",
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        db.add(receipt)
        db.add(ShopifyPrivacyAuditEvent(
            request_id=RECEIPT, event_type="received", from_status=None,
            to_status="pending_policy_review", reason_code="tenant_bound",
            actor_type="shopify_hmac_verified", created_at=datetime.utcnow(),
        ))
        db.commit()
        yield db, receipt, stores, connections
    engine.dispose()


def _payload(order_id=101, customer_id=700, phone="555000", email="private@example.com"):
    customer = {"id": customer_id, "email": email,
                "phone": phone, "first_name": "Secret"}
    return {
        "id": order_id, "customer": customer,
        "total_price": "12.00", "currency": "COP",
        "shipping_address": {"address1": "PRIVATE HOME ADDRESS"},
        "line_items": [],
    }


def _webhook(db, connection, *, order_id=101, customer_id=700, phone="555000", email="private@example.com"):
    with patch("app.services.shopify_webhook_service.safe_emit_event"):
        return process_shopify_order_webhook(
            db, connection=connection, topic="orders/create",
            payload=_payload(order_id=order_id, customer_id=customer_id, phone=phone, email=email),
        )


def test_staging_is_signed_scoped_encrypted_at_rest_and_idempotent(sandbox):
    db, receipt, stores, _ = sandbox
    result = prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    assert result["expected_selectors"] == 3
    assert result["newly_staged"] == 3
    assert result["activated"] is False
    assert result["fulfillment_complete"] is False
    repeat = prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    assert repeat["newly_staged"] == 0
    assert repeat["already_present"] == 3
    rows = db.query(ShopifyPrivacySuppression).all()
    assert len(rows) == 3
    assert all(x.status == "staged" and len(x.selector_digest) == 64 for x in rows)
    assert all(x.organization_id == receipt.organization_id for x in rows)
    assert all(x.store_id == receipt.store_id for x in rows)
    assert all("700" not in x.selector_digest and "101" not in x.selector_digest for x in rows)
    assert all(not x.__table__.foreign_keys for x in rows)
    assert db.query(ShopifyPrivacyAuditEvent).filter(
        ShopifyPrivacyAuditEvent.event_type == "suppression_staged",
    ).count() == 1
    assert inspect_shopify_privacy_suppressions(db, request_id=RECEIPT)["active"] == 0


def test_staged_tombstones_do_not_interrupt_live_ingestion(sandbox):
    db, _, _, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    result = _webhook(db, connections[0])
    assert result["action"] == "created"
    assert db.query(Customer).count() == 1
    assert db.query(Order).count() == 1


def test_synthetic_activation_blocks_replayed_orders_and_customer_data(sandbox, monkeypatch):
    db, receipt, _, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    assert activate_synthetic_privacy_suppressions(db, request_id=RECEIPT) == 3
    assert activate_synthetic_privacy_suppressions(db, request_id=RECEIPT) == 0
    first = _webhook(db, connections[0])
    second = _webhook(db, connections[0], order_id=102)
    assert first["action"] == second["action"] == "suppressed_privacy"
    assert "private" not in str(first)
    assert db.query(Customer).count() == 0
    assert db.query(CustomerStoreProfile).count() == 0
    assert db.query(Order).count() == 0
    assert receipt.completed_at is None
    assert receipt.status == "pending_policy_review"


def test_active_subject_unknown_customer_id_fails_closed(sandbox, monkeypatch):
    db, _, _, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    assert _webhook(db, connections[0], order_id=103, customer_id=None)["action"] == "suppressed_privacy"
    assert db.query(Customer).count() == 0


def test_unrelated_new_shopify_id_cannot_relink_suppressed_contact(sandbox, monkeypatch):
    db, _, _, connections = sandbox
    # Existing profile shares the contact details that Shopify might replay.
    _webhook(db, connections[0], order_id=104, customer_id=700)
    first = db.query(Customer).one()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    # A new Shopify ID with the same signed email is also suppressed.
    result = _webhook(db, connections[0], order_id=105, customer_id=701)
    assert result["action"] == "suppressed_privacy"
    assert db.query(CustomerStoreProfile).count() == 1
    # For a genuinely different email, never reuse an existing customer
    # by a coincidentally shared phone within a store with active tombstones.
    allowed = _webhook(
        db, connections[0], order_id=106, customer_id=701,
        email="different@example.com",
    )
    assert allowed["action"] == "created"
    profiles = db.query(CustomerStoreProfile).order_by(CustomerStoreProfile.id).all()
    assert len(profiles) == 2
    assert profiles[0].customer_id == first.id
    assert profiles[1].customer_id != first.id


def test_tombstones_do_not_block_different_store_or_org(sandbox, monkeypatch):
    db, _, stores, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    assert _webhook(db, connections[0])["action"] == "suppressed_privacy"
    assert _webhook(db, connections[1])["action"] == "created"
    assert db.query(CustomerStoreProfile).one().store_id == stores[1].id
    assert db.query(Order).one().store_id == stores[1].id


def test_shop_redact_tombstone_blocks_all_shop_orders(sandbox, monkeypatch):
    db, receipt, _, connections = sandbox
    receipt.topic = "shop/redact"
    db.commit()
    result = prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    assert result["expected_selectors"] == 1
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    assert activate_synthetic_privacy_suppressions(db, request_id=RECEIPT) == 1
    assert _webhook(db, connections[0], order_id=123, customer_id=999)["action"] == "suppressed_privacy"
    assert db.query(Order).count() == 0


def test_missing_key_blocks_active_suppression_without_mutations(sandbox, monkeypatch):
    db, _, _, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.delenv("SHOPIFY_PRIVACY_SUPPRESSION_KEY")
    with pytest.raises(ShopifyWebhookError, match="PRIVACY_SUPPRESSION_CHECK_UNAVAILABLE"):
        _webhook(db, connections[0])
    assert db.query(Customer).count() == 0
    assert db.query(Order).count() == 0


def test_invalid_domain_or_key_cannot_allow_replay(sandbox, monkeypatch):
    db, _, stores, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    stores[0].shopify_domain = "drifted-store.myshopify.com"
    db.commit()
    with pytest.raises(ShopifyWebhookError, match="PRIVACY_SUPPRESSION_CHECK_UNAVAILABLE"):
        _webhook(db, connections[0])
    assert db.query(Order).count() == 0


def test_unsigned_intake_cannot_stage(sandbox):
    db, _, _, _ = sandbox
    db.query(ShopifyPrivacyAuditEvent).delete()
    db.commit()
    with pytest.raises(ShopifySuppressionError, match="SIGNED_INTAKE_REQUIRED"):
        prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    assert db.query(ShopifyPrivacySuppression).count() == 0


def test_production_activation_not_exposed(sandbox, monkeypatch):
    db, _, _, _ = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.delenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", raising=False)
    with pytest.raises(ShopifySuppressionError, match="SYNTHETIC_TEST_ONLY"):
        activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    assert db.query(ShopifyPrivacySuppression).filter(
        ShopifyPrivacySuppression.status == "active",
    ).count() == 0


def test_internal_api_authentication_before_write(sandbox, monkeypatch):
    db, _, _, _ = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "privacy-test-only-internal-secret")
    with pytest.raises(HTTPException) as err:
        prepare_shopify_privacy_suppression_case(
            request_id=RECEIPT, x_internal_secret="invalid", db=db,
        )
    assert err.value.status_code == 401
    assert db.query(ShopifyPrivacySuppression).count() == 0
    result = prepare_shopify_privacy_suppression_case(
        request_id=RECEIPT,
        x_internal_secret="privacy-test-only-internal-secret", db=db,
    )
    assert result["newly_staged"] == 3
    response = get_shopify_privacy_suppression_case(
        request_id=RECEIPT,
        x_internal_secret="privacy-test-only-internal-secret", db=db,
    )
    assert response["staged"] == 3
    assert "selector_digest" not in str(response)
    assert "private@example.com" not in str(response)


@pytest.mark.parametrize("bad", ["x", "", "E" * 64])
def test_invalid_receipt_id_rejected(sandbox, bad):
    db, _, _, _ = sandbox
    with pytest.raises(ShopifySuppressionError, match="INVALID_REQUEST_ID"):
        prepare_shopify_privacy_suppressions(db, request_id=bad)


def test_hmac_is_bound_to_store_and_resource_kind(sandbox):
    db, _, _, _ = sandbox
    result = prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    assert result["newly_staged"] == 3
    rows = db.query(ShopifyPrivacySuppression).all()
    assert rows[0].selector_digest != rows[1].selector_digest
    assert all(len(r.selector_digest) == 64 for r in rows)
    assert "private@example.com" not in str([r.__dict__ for r in rows])


def test_secret_rotation_must_not_silently_disable_active_tombstones(
    sandbox, monkeypatch,
):
    db, _, _, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv(
        "SHOPIFY_PRIVACY_SUPPRESSION_KEY",
        "rotated-key-that-must-not-deactivate-previous-tombstones-9876543210",
    )
    with pytest.raises(ShopifyWebhookError, match="PRIVACY_SUPPRESSION_CHECK_UNAVAILABLE"):
        _webhook(db, connections[0])
    with pytest.raises(ShopifySuppressionError, match="SUPPRESSION_KEY_MISMATCH"):
        prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    assert db.query(Order).count() == 0


def test_optional_signed_phone_tombstone_prevents_new_id_reingestion(
    sandbox, monkeypatch,
):
    db, receipt, _, connections = sandbox
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700, "phone": "+57 320 111 2233"},
        "orders_to_redact": [101],
    }))
    db.commit()
    staged = prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    assert staged["newly_staged"] == 3
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    assert _webhook(
        db, connections[0], customer_id=999, order_id=999,
        email="different@example.com", phone="+57 (320) 111-2233",
    )["action"] == "suppressed_privacy"
    assert db.query(Customer).count() == 0


def test_active_tombstone_blocks_domain_rebind_even_after_store_update(
    sandbox, monkeypatch,
):
    db, _, stores, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    stores[0].shopify_domain = "new-shop-domain.myshopify.com"
    connections[0].external_store_url = "new-shop-domain.myshopify.com"
    db.commit()
    with pytest.raises(ShopifyWebhookError, match="PRIVACY_SUPPRESSION_CHECK_UNAVAILABLE"):
        _webhook(db, connections[0])
    assert db.query(Customer).count() == 0
    assert db.query(Order).count() == 0


def test_manual_draft_and_cod_cannot_reintroduce_suppressed_buyer(
    sandbox, monkeypatch,
):
    from app.shopify_orders import create_shopify_draft_order
    from app.shopify_cod_orders import create_shopify_cod_order
    db, _, stores, connections = sandbox
    existing = _webhook(db, connections[0])
    assert existing["action"] == "created"
    customer = db.query(Customer).one()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    with pytest.raises(ValueError, match="SHOPIFY_PRIVACY_SUPPRESSED"):
        create_shopify_draft_order(
            db=db, store=stores[0], connection=connections[0],
            items_payload=[], customer_email="private@example.com",
        )
    # The retired COD entrypoint rejects before any provider or DB side effect,
    # independently of the privacy tombstone.
    from app.shopify_client import ShopifyUserError
    with pytest.raises(ShopifyUserError, match="SHOPIFY_CHECKOUT_REQUIRED"):
        create_shopify_cod_order(
            db=db, store=stores[0], connection=connections[0],
            customer_id=customer.id, variant_local_id=123, quantity=1,
            customer_email="private@example.com", customer_phone="555000",
            shipping_address={}, note="test", idempotency_key="privacy-test",
        )
    assert db.query(Order).count() == 1


def test_queued_order_cannot_be_reenqueued_after_suppression(
    sandbox, monkeypatch,
):
    from app.services.auto_fulfillment import enqueue_shopify_order
    db, _, _, connections = sandbox
    _webhook(db, connections[0])
    order = db.query(Order).one()
    order.payment_status = "paid"
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    assert enqueue_shopify_order(db, order.id) is None
    assert db.query(Order).count() == 1


def test_restored_tombstone_ledger_detects_rollback_and_rotation(
    sandbox, monkeypatch,
):
    from app.services.shopify_privacy_restore import (
        ShopifyRestoreVerificationError,
        create_shopify_suppression_checkpoint,
        verify_shopify_suppression_restore,
    )
    db, _, _, _ = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    snapshot = create_shopify_suppression_checkpoint(db)
    assert snapshot["total_records"] == 3
    assert len(snapshot["checkpoint_hmac"]) == 64
    ok = verify_shopify_suppression_restore(
        db, externally_stored_hmac=snapshot["checkpoint_hmac"],
        minimum_records=snapshot["total_records"],
    )
    assert ok["recovery_verified"] is True
    assert ok["provider_erasure_verified"] is False
    db.query(ShopifyPrivacySuppression).filter(
        ShopifyPrivacySuppression.kind == "order",
    ).delete()
    db.commit()
    with pytest.raises(ShopifyRestoreVerificationError, match="SUPPRESSION_LEDGER_ROLLBACK"):
        verify_shopify_suppression_restore(
            db, externally_stored_hmac=snapshot["checkpoint_hmac"],
            minimum_records=snapshot["total_records"],
        )
    with pytest.raises(ShopifyRestoreVerificationError, match="EXTERNAL_LEDGER_REQUIRED"):
        verify_shopify_suppression_restore(
            db, externally_stored_hmac="", minimum_records=0,
        )
    monkeypatch.setenv(
        "SHOPIFY_PRIVACY_SUPPRESSION_KEY", "another-test-key-longer-than-32-bytes-restore-123",
    )
    with pytest.raises(ShopifyRestoreVerificationError, match="SUPPRESSION_KEY_MISMATCH"):
        create_shopify_suppression_checkpoint(db)


def test_privacy_controls_record_evidence_but_cannot_claim_approval(sandbox, monkeypatch):
    from app.models import ShopifyPrivacyControlEvidence
    from app.services.shopify_privacy_controls import (
        inspect_shopify_privacy_closure_controls,
        submit_shopify_privacy_control_evidence,
        ShopifyPrivacyControlError,
    )
    from app.api.shopify_privacy_backlog import (
        PrivacyEvidenceSubmission, get_shopify_privacy_controls,
        submit_shopify_privacy_evidence,
    )
    db, receipt, _, _ = sandbox
    report = inspect_shopify_privacy_closure_controls(db, request_id=RECEIPT)
    assert report["retention_approved"] is False
    assert report["restore_verified"] is False
    assert report["closure_ready"] is False
    assert report["days_remaining_for_shopify_response"] <= 30
    digest = "a" * 64
    first = submit_shopify_privacy_control_evidence(
        db, request_id=RECEIPT, control="financial_orders",
        artifact_sha256=digest,
    )
    second = submit_shopify_privacy_control_evidence(
        db, request_id=RECEIPT, control="financial_orders",
        artifact_sha256=digest,
    )
    assert first["recorded"] is True and second["recorded"] is False
    assert first["verified"] is False
    assert db.query(ShopifyPrivacyControlEvidence).count() == 1
    updated = inspect_shopify_privacy_closure_controls(db, request_id=RECEIPT)
    assert updated["submitted_artifacts"] == 1
    assert updated["validated_artifacts"] == 0
    assert updated["closure_ready"] is False
    with pytest.raises(ShopifyPrivacyControlError, match="UNKNOWN_PRIVACY_CONTROL"):
        submit_shopify_privacy_control_evidence(
            db, request_id=RECEIPT, control="invented",
            artifact_sha256=digest,
        )
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "control-review-test-secret")
    with pytest.raises(HTTPException) as error:
        submit_shopify_privacy_evidence(
            request_id=RECEIPT, control="database_backups",
            body=PrivacyEvidenceSubmission(artifact_sha256=digest),
            x_internal_secret="bad", db=db,
        )
    assert error.value.status_code == 401
    got = get_shopify_privacy_controls(
        request_id=RECEIPT,
        x_internal_secret="control-review-test-secret", db=db,
    )
    assert got["fulfillment_complete"] is False
    assert "private@example.com" not in str(got)


def test_local_privacy_gate_allows_other_contact_but_not_old_identity(
    sandbox, monkeypatch,
):
    from app.services.shopify_privacy_suppression import evaluate_shopify_local_privacy
    db, _, stores, _ = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    assert evaluate_shopify_local_privacy(
        db, organization_id=stores[0].organization_id, store_id=stores[0].id,
        customer_email="private@example.com",
    ) == "email"
    assert evaluate_shopify_local_privacy(
        db, organization_id=stores[0].organization_id, store_id=stores[0].id,
        customer_email="someone-else@example.com",
    ) is None
    assert evaluate_shopify_local_privacy(
        db, organization_id=stores[1].organization_id, store_id=stores[1].id,
        customer_email="private@example.com",
    ) is None


def test_offsite_checkpoint_blocks_empty_restored_ledger(
    sandbox, monkeypatch,
):
    from app.services.shopify_privacy_restore import (
        create_shopify_suppression_checkpoint,
    )
    db, _, stores, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    checkpoint = create_shopify_suppression_checkpoint(db)
    # Simulate restoring a database snapshot from before privacy processing.
    db.query(ShopifyPrivacySuppression).delete()
    db.commit()
    monkeypatch.setenv(
        "SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC", checkpoint["checkpoint_hmac"],
    )
    monkeypatch.setenv(
        "SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS",
        str(checkpoint["total_records"]),
    )
    with pytest.raises(ShopifyWebhookError, match="PRIVACY_SUPPRESSION_CHECK_UNAVAILABLE"):
        _webhook(db, connections[0])
    with pytest.raises(ShopifySuppressionError, match="RESTORE_CHECKPOINT_VERIFICATION_FAILED"):
        from app.services.shopify_privacy_suppression import evaluate_shopify_local_privacy
        evaluate_shopify_local_privacy(
            db, organization_id=stores[0].organization_id,
            store_id=stores[0].id,
            customer_email="private@example.com",
        )
    assert db.query(Customer).count() == 0
    assert db.query(Order).count() == 0


def test_offsite_checkpoint_unchanged_allows_unrelated_store_after_activation(
    sandbox, monkeypatch,
):
    from app.services.shopify_privacy_restore import (
        create_shopify_suppression_checkpoint,
    )
    db, _, _, connections = sandbox
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    checkpoint = create_shopify_suppression_checkpoint(db)
    monkeypatch.setenv("SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC", checkpoint["checkpoint_hmac"])
    monkeypatch.setenv("SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS", str(checkpoint["total_records"]))
    assert _webhook(db, connections[0])["action"] == "suppressed_privacy"
    assert _webhook(db, connections[1])["action"] == "created"


def test_leased_automation_flow_cannot_contact_deleted_customer(
    sandbox, monkeypatch,
):
    from types import SimpleNamespace
    from app.automation_flow_engine import process_flow_recipient
    from app.models import AutomationFlowRecipientExecution, AutomationFlowRun
    db, _, stores, connections = sandbox
    _webhook(db, connections[0])
    customer = db.query(Customer).one()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    recipient = SimpleNamespace(
        id=8001, status="active", claim_token="queued-token",
        claim_expires_at=None, flow_run_id=9001, customer_id=customer.id,
    )
    run = SimpleNamespace(
        id=9001, organization_id=stores[0].organization_id,
        store_id=stores[0].id, total_recipients=1,
        completed_recipients=0, failed_recipients=0, status="running",
        completed_at=None,
    )
    original_get = db.get

    def fake_get(model, obj_id):
        if model is AutomationFlowRecipientExecution and obj_id == recipient.id:
            return recipient
        if model is AutomationFlowRun and obj_id == run.id:
            return run
        return original_get(model, obj_id)

    monkeypatch.setattr(db, "get", fake_get)
    assert process_flow_recipient(
        db, recipient.id, claim_token="queued-token",
    ) == "privacy_suppressed"
    assert recipient.status == "failed"
    assert recipient.error_code == "privacy_suppressed"
    assert run.failed_recipients == 1


def test_legacy_automation_whatsapp_is_blocked_before_provider_call(
    sandbox, monkeypatch,
):
    from app.automations import execute_send_whatsapp_message
    from app.models import Conversation
    db, _, stores, connections = sandbox
    _webhook(db, connections[0])
    customer = db.query(Customer).one()
    conversation = Conversation(
        organization_id=stores[0].organization_id, store_id=stores[0].id,
        customer_id=customer.id,
    )
    db.add(conversation)
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    result = execute_send_whatsapp_message(
        db, stores[0].organization_id, stores[0].id,
        action={"conversation_id": conversation.id},
        payload={}, execution=None,
    )
    assert result["status"] == "skipped"
    assert result["reason"] == "PRIVACY_SUPPRESSED"


def test_whatsapp_inbound_suppression_blocks_pii_before_customer_creation(
    sandbox, monkeypatch,
):
    from app.models import WhatsAppConnection, Message, Conversation
    from app.services.whatsapp_webhooks import process_webhook_payload
    db, receipt, stores, _ = sandbox
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700, "phone": "+57 320 111 2233"},
    }))
    db.add(WhatsAppConnection(
        organization_id=receipt.organization_id, store_id=receipt.store_id,
        phone_number_id="privacy-phone-id",
        business_account_id="privacy-business-id",
        access_token_encrypted="synthetic", verify_token="synthetic",
        status="connected",
    ))
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    response = process_webhook_payload(db, {
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "privacy-phone-id"},
            "messages": [{"from": "573201112233", "id": "private-wa-msg",
                          "type": "text", "text": {"body": "sensitive text"}}],
        }}]}],
    })
    assert response["new_messages"] == []
    assert db.query(Customer).count() == 0
    assert db.query(Conversation).count() == 0
    assert db.query(Message).count() == 0


def test_instagram_redacted_shop_drops_inbound_and_linked_subject(
    sandbox, monkeypatch,
):
    from app.instagram_models import InstagramConnection
    from app.models import Conversation, Message
    from app.services.instagram_webhooks import process_webhook_payload
    db, receipt, stores, _ = sandbox
    db.add(InstagramConnection(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        instagram_account_id="test-ig-account",
        page_id="test-ig-page", username="test",
        access_token_encrypted="synthetic", status="connected",
    ))
    receipt.topic = "shop/redact"
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    payload = {"object": "instagram", "entry": [{
        "id": "test-ig-account", "messaging": [{
            "sender": {"id": "synthetic-ig-sender"},
            "message": {"mid": "private-ig-msg", "text": "private text"},
        }],
    }]}
    response = process_webhook_payload(db, payload)
    assert response["new_messages"] == []
    assert db.query(Customer).count() == 0
    assert db.query(Conversation).count() == 0
    assert db.query(Message).count() == 0


def test_linked_instagram_sender_is_suppressed_without_name_guess(
    sandbox, monkeypatch,
):
    from app.instagram_models import InstagramConnection
    from app.models import CustomerStoreProfile, Message
    from app.services.instagram_webhooks import process_webhook_payload
    db, receipt, stores, _ = sandbox
    customer = Customer(
        organization_id=receipt.organization_id, name="PRIVATE_LINKED_BUYER",
        phone="instagram:private-sender",
    )
    db.add(customer)
    db.flush()
    db.add(CustomerStoreProfile(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        customer_id=customer.id, external_customer_id="700",
        currency="COP",
    ))
    db.add(InstagramConnection(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        instagram_account_id="linked-ig-account", page_id="linked-ig-page",
        username="linked", access_token_encrypted="synthetic",
        status="connected",
    ))
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    result = process_webhook_payload(db, {
        "object": "instagram", "entry": [{
            "id": "linked-ig-account", "messaging": [{
                "sender": {"id": "private-sender"},
                "message": {"mid": "linked-private", "text": "private"},
            }],
        }],
    })
    assert result["new_messages"] == []
    assert db.query(Message).count() == 0
    assert db.query(Customer).count() == 1


def test_ai_agent_tool_excludes_suppressed_customer_and_order(
    sandbox, monkeypatch,
):
    from types import SimpleNamespace
    from app.services.agent_tool_executor import (
        _customers_search, _orders_list, _orders_get,
        AgentToolExecutionError,
    )
    db, receipt, stores, connections = sandbox
    _webhook(db, connections[0])
    buyer = db.query(Customer).one()
    order = db.query(Order).one()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    membership = SimpleNamespace(organization_id=receipt.organization_id)
    assert _customers_search(db, membership, stores[0].id, {})["count"] == 0
    assert _orders_list(db, membership, stores[0].id, {})["count"] == 0
    with pytest.raises(AgentToolExecutionError, match="PRIVACY_SUPPRESSED"):
        _orders_get(db, membership, stores[0].id, {"order_id": order.id})
    assert buyer.name == "Secret"


def test_queued_ai_reply_checks_tombstone_before_llm_or_provider(
    sandbox, monkeypatch,
):
    from app.models import Conversation, Message
    from app.services.checkout_reply_service import generate_checkout_or_auto_reply
    from app.ai_reply_service import generate_auto_reply, _deliver_answer
    db, receipt, stores, connections = sandbox
    _webhook(db, connections[0])
    customer = db.query(Customer).one()
    conversation = Conversation(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        customer_id=customer.id, channel="WhatsApp", mode="ai",
    )
    db.add(conversation)
    db.flush()
    incoming = Message(
        conversation_id=conversation.id, sender="customer", text="private inbound",
    )
    db.add(incoming)
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    with patch("app.ai_reply_service._resolve_agent") as resolve, patch(
        "app.ai_reply_service.send_whatsapp_text_message"
    ) as send:
        generate_checkout_or_auto_reply(conversation.id, db=db)
        generate_auto_reply(conversation.id, db=db)
        resolve.assert_not_called()
        send.assert_not_called()
        ai_message = Message(
            conversation_id=conversation.id, sender="ai", text="never deliver",
        )
        db.add(ai_message)
        db.commit()
        _deliver_answer(db, conversation, ai_message, "never deliver")
        send.assert_not_called()
        assert ai_message.delivery_status == "suppressed"


def test_cj_provider_webhook_cannot_restore_suppressed_tracking(
    sandbox, monkeypatch,
):
    from app.model_domains.supplier_integrations import SupplierConnection
    from app.model_domains.supplier_orders import SupplierOrder
    from app.model_domains.shipments import CJWebhookReceipt, Shipment
    from app.services.cj_webhooks import (
        compute_cj_webhook_signature, process_cj_webhook,
    )
    db, receipt, stores, connections = sandbox
    _webhook(db, connections[0])
    order = db.query(Order).one()
    now = datetime.utcnow()
    supplier_connection = SupplierConnection(
        organization_id=receipt.organization_id,
        store_id=stores[0].id, provider="cj",
        external_account_id="synthetic-cj-privacy-id",
        status="connected", connected_at=now,
        created_at=now, updated_at=now,
    )
    db.add(supplier_connection)
    db.flush()
    supplier_order = SupplierOrder(
        organization_id=receipt.organization_id,
        store_id=stores[0].id, supplier_connection_id=supplier_connection.id,
        order_id=order.id, provider="cj",
        provider_order_number="synthetic-CJ-101",
        external_order_id="CJ-101", supplier_status="SHIPPED",
        creation_status="created", idempotency_key="synthetic-cj-101",
        currency="COP", created_at=now, updated_at=now,
    )
    db.add(supplier_order)
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    webhook = {
        "openId": "synthetic-cj-privacy-id",
        "messageId": "cj-private-replayed",
        "type": "LOGISTIC",
        "params": {
            "orderId": "CJ-101", "trackingNumber": "PRIVATE-TRACKING",
            "trackingStatus": 12,
        },
    }
    raw = json.dumps(webhook).encode()
    sig = compute_cj_webhook_signature(webhook["openId"], raw)
    response = process_cj_webhook(db, raw_body=raw, signature=sig)
    assert response["ignored"] is True
    assert db.query(Shipment).count() == 0
    received = db.query(CJWebhookReceipt).one()
    assert received.error_code == "PRIVACY_SUPPRESSED"
    assert received.processing_status == "ignored"

    from app.services.supplier_orders import (
        SupplierOrderError, create_cj_supplier_order, sync_cj_supplier_order,
    )
    with pytest.raises(SupplierOrderError, match="PRIVACY_SUPPRESSED"):
        create_cj_supplier_order(
            db, receipt.organization_id, stores[0].id,
            order_id=order.id, idempotency_key="new-cj-privacy-order",
            items=[], shipping={}, from_country_code="CO",
            logistic_name="TEST",
        )
    with pytest.raises(SupplierOrderError, match="PRIVACY_SUPPRESSED"):
        sync_cj_supplier_order(
            db, receipt.organization_id, stores[0].id, supplier_order.id,
        )


def test_direct_whatsapp_send_blocked_before_external_provider(
    sandbox, monkeypatch,
):
    from app.models import WhatsAppConnection, Conversation
    from app.services.whatsapp_service import send_message, WhatsAppSendError
    db, receipt, stores, connections = sandbox
    _webhook(db, connections[0])
    buyer = db.query(Customer).one()
    db.add(WhatsAppConnection(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        phone_number_id="wa-privacy-send", business_account_id="wa-test",
        access_token_encrypted="synthetic", verify_token="synthetic",
        status="connected",
    ))
    conversation = Conversation(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        customer_id=buyer.id, channel="WhatsApp",
    )
    db.add(conversation)
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    with patch("app.services.whatsapp_service.send_whatsapp_text_message") as send:
        with pytest.raises(WhatsAppSendError, match="PRIVACY_SUPPRESSED"):
            send_message(
                db, receipt.organization_id, conversation.id,
                "PRIVATE_WHATSAPP_TEXT",
            )
        send.assert_not_called()


def test_instagram_direct_send_blocked_for_linked_shopify_buyer(
    sandbox, monkeypatch,
):
    from app.instagram_models import InstagramConnection
    from app.models import CustomerStoreProfile, Conversation
    from app.services.instagram_service import send_message, InstagramSendError
    db, receipt, stores, _ = sandbox
    customer = Customer(
        organization_id=receipt.organization_id,
        name="PRIVATE_IG_BUYER", phone="instagram:synthig",
    )
    db.add(customer)
    db.flush()
    db.add(CustomerStoreProfile(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        customer_id=customer.id, external_customer_id="700", currency="COP",
    ))
    db.add(InstagramConnection(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        instagram_account_id="ig-privacy-send",
        page_id="ig-test", username="ig-privacy",
        access_token_encrypted="synthetic", status="connected",
    ))
    conversation = Conversation(
        organization_id=receipt.organization_id,
        store_id=stores[0].id, customer_id=customer.id,
        channel="Instagram",
    )
    db.add(conversation)
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    with patch("app.services.instagram_service.instagram_send_message") as send:
        with pytest.raises(InstagramSendError, match="PRIVACY_SUPPRESSED"):
            send_message(
                db, receipt.organization_id, conversation.id,
                "PRIVATE_INSTAGRAM_TEXT",
            )
        send.assert_not_called()


def test_unlinked_whatsapp_message_not_mistaken_for_shopify_customer(
    sandbox, monkeypatch,
):
    from app.models import WhatsAppConnection, Message
    from app.services.whatsapp_webhooks import process_webhook_payload
    db, receipt, stores, _ = sandbox
    db.add(WhatsAppConnection(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        phone_number_id="wa-unlinked-privacy",
        business_account_id="wa-unlinked-account",
        access_token_encrypted="synthetic", verify_token="synthetic",
        status="connected",
    ))
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    result = process_webhook_payload(db, {
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "wa-unlinked-privacy"},
            "messages": [{
                "from": "573220000111", "id": "unlinked-wa-message",
                "type": "text", "text": {"body": "independent user"},
            }],
        }}]}],
    })
    assert len(result["new_messages"]) == 1
    assert db.query(Message).count() == 1
    assert db.query(Customer).one().phone == "573220000111"


def test_telegram_shop_redaction_blocks_ingest_and_unlinked_stays_safe(
    sandbox, monkeypatch,
):
    from app.telegram_models import TelegramConnection
    from app.models import Message
    from app.services.telegram_webhooks import process_webhook_payload
    db, receipt, stores, _ = sandbox
    connection = TelegramConnection(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        bot_id=123456, bot_username="privacy_test_bot",
        bot_token_encrypted="synthetic",
        webhook_secret_encrypted="synthetic", webhook_path_token="privacy-path",
        status="connected",
    )
    db.add(connection)
    receipt.topic = "shop/redact"
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    inbound = {
        "message": {
            "message_id": 22, "chat": {"id": 1234, "type": "private"},
            "from": {"id": 1234, "first_name": "private"},
            "text": "never persist",
        },
    }
    result = process_webhook_payload(db, connection, inbound)
    assert result["new_messages"] == []
    assert db.query(Customer).count() == 0
    assert db.query(Message).count() == 0


def test_telegram_linked_shopify_subject_cannot_ingest_or_send(
    sandbox, monkeypatch,
):
    from app.telegram_models import TelegramConnection
    from app.models import CustomerStoreProfile, Conversation, Message
    from app.services.telegram_webhooks import process_webhook_payload
    from app.services.telegram_service import send_message, TelegramSendError
    db, receipt, stores, _ = sandbox
    customer = Customer(
        organization_id=receipt.organization_id,
        name="PRIVATE_TELEGRAM_BUYER", phone="telegram:442211",
    )
    db.add(customer)
    db.flush()
    db.add(CustomerStoreProfile(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        customer_id=customer.id, external_customer_id="700", currency="COP",
    ))
    connection = TelegramConnection(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        bot_id=999001, bot_username="privacy_telegram_bot",
        bot_token_encrypted="synthetic",
        webhook_secret_encrypted="synthetic", webhook_path_token="privacy-test",
        status="connected",
    )
    db.add(connection)
    conversation = Conversation(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        customer_id=customer.id, channel="Telegram",
    )
    db.add(conversation)
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    inbound = {
        "message": {
            "message_id": 24, "chat": {"id": 442211, "type": "private"},
            "from": {"id": 442211}, "text": "private inbound",
        },
    }
    result = process_webhook_payload(db, connection, inbound)
    assert result["new_messages"] == []
    assert db.query(Message).count() == 0
    with patch("app.services.telegram_service.telegram_send_message") as provider:
        with pytest.raises(TelegramSendError, match="PRIVACY_SUPPRESSED"):
            send_message(
                db, receipt.organization_id, conversation.id, "private outbound",
            )
        provider.assert_not_called()


def test_whatsapp_status_callback_does_not_restore_suppressed_message_metadata(
    sandbox, monkeypatch,
):
    from app.models import WhatsAppConnection, Conversation, Message
    from app.services.whatsapp_webhooks import process_webhook_payload
    db, receipt, stores, connections = sandbox
    _webhook(db, connections[0])
    customer = db.query(Customer).one()
    conversation = Conversation(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        customer_id=customer.id, channel="WhatsApp",
    )
    db.add(conversation)
    db.flush()
    message = Message(
        conversation_id=conversation.id, sender="human", text="PRIVATE_STATUS",
        provider="whatsapp", external_message_id="wamid-private-status",
        delivery_status="sent",
    )
    db.add(message)
    db.add(WhatsAppConnection(
        organization_id=receipt.organization_id, store_id=stores[0].id,
        phone_number_id="privacy-status-business", business_account_id="priv-status",
        access_token_encrypted="synthetic", verify_token="synthetic",
        status="connected",
    ))
    db.commit()
    prepare_shopify_privacy_suppressions(db, request_id=RECEIPT)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    activate_synthetic_privacy_suppressions(db, request_id=RECEIPT)
    process_webhook_payload(db, {
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "privacy-status-business"},
            "statuses": [{"id": "wamid-private-status", "status": "delivered"}],
        }}]}],
    })
    db.refresh(message)
    assert message.delivery_status == "sent"
