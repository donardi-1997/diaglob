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
    assert result["newly_staged"] == 2
    rows = db.query(ShopifyPrivacySuppression).all()
    assert rows[0].selector_digest != rows[1].selector_digest
    assert all(len(r.selector_digest) == 64 for r in rows)
    assert "email" not in str([r.__dict__ for r in rows])


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
