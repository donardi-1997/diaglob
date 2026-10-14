"""Encrypted customer access and field-level redaction manifest remain fail closed."""
import json
from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Conversation, Customer, CustomerStoreProfile, Message, Order, Organization,
    ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest, Store,
)
from app.shopify_security import decrypt_shopify_secret, encrypt_shopify_secret
from app.services.shopify_privacy_local_processor import (
    ShopifyLocalPrivacyError, build_encrypted_local_customer_export,
    build_local_redaction_manifest,
)
from app.api.shopify_privacy_backlog import (
    get_shopify_local_redaction_manifest,
    inspect_shopify_local_customer_export,
)

RECEIPT_ID = "b" * 64


@pytest.fixture
def sandbox(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic export", slug="synthetic-export", plan="starter")
        db.add(org)
        db.flush()
        stores = []
        for index in (1, 2):
            shop = Store(
                organization_id=org.id, name=f"Store{index}",
                slug=f"privacy-shop-{index}", country_code="CO",
                currency="COP", timezone="UTC",
                shopify_domain=f"privacy-shop-{index}.myshopify.com",
            )
            db.add(shop)
            stores.append(shop)
        db.flush()
        customer = Customer(organization_id=org.id, name="SHARED_PRIVATE_NAME",
                            phone="PRIVATE_GLOBAL_PHONE", email="shared@example.com")
        db.add(customer)
        db.flush()
        for index, shop in enumerate(stores):
            db.add(CustomerStoreProfile(
                organization_id=org.id, store_id=shop.id, customer_id=customer.id,
                external_customer_id="700", currency="COP",
            ))
            db.add(Order(
                organization_id=org.id, store_id=shop.id, customer_id=customer.id,
                shopify_order_id=str(index + 101),
                order_number=f"PRIVATE_ORDER_{index}",
                total_amount=1, currency="COP",
                note=f"PRIVATE_NOTE_{index}",
                shipping_address={"address1": f"PRIVATE_ADDRESS_{index}"},
            ))
            convo = Conversation(
                organization_id=org.id, store_id=shop.id, customer_id=customer.id,
                preview=f"PRIVATE_PREVIEW_{index}",
            )
            db.add(convo)
            db.flush()
            db.add(Message(
                conversation_id=convo.id, sender="customer",
                text=f"PRIVATE_MESSAGE_{index}",
            ))
        receipt = ShopifyPrivacyRequest(
            request_id=RECEIPT_ID, topic="customers/data_request",
            shop_id="private-shop-id", shop_domain=stores[0].shopify_domain,
            organization_id=org.id, store_id=stores[0].id,
            selector_encrypted=encrypt_shopify_secret(json.dumps({
                "customer": {"id": 700, "email": "shared@example.com"},
                "orders_requested": [101],
            })),
            status="pending_policy_review", created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(receipt)
        db.add(ShopifyPrivacyAuditEvent(
            request_id=RECEIPT_ID, event_type="received",
            from_status=None, to_status="pending_policy_review",
            reason_code="tenant_bound", actor_type="shopify_hmac_verified",
            created_at=datetime.utcnow(),
        ))
        db.commit()
        yield db, receipt
    engine.dispose()


def test_encrypted_export_exact_store_subject_and_requested_order(sandbox):
    db, receipt = sandbox
    result = build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)
    assert result.complete is False and result.merchant_delivery_allowed is False
    assert (result.profiles, result.orders, result.conversations, result.messages) == (1, 1, 1, 1)
    assert result.requested_orders_not_resolved == 0
    assert "PRIVATE_NOTE" not in result.encrypted_payload
    data = json.loads(decrypt_shopify_secret(result.encrypted_payload))
    assert data["complete"] is False
    assert data["orders"][0]["shopify_order_id"] == "101"
    assert data["orders"][0]["shipping_address"]["address1"] == "PRIVATE_ADDRESS_0"
    assert data["conversations"][0]["messages"][0]["text"] == "PRIVATE_MESSAGE_0"
    assert "PRIVATE_ADDRESS_1" not in str(data)
    assert "PRIVATE_MESSAGE_1" not in str(data)
    assert "SHARED_PRIVATE_NAME" not in str(data)
    assert receipt.status == "pending_policy_review" and receipt.completed_at is None
    assert db.query(Order).count() == 2


def test_unmatched_requested_order_never_exports_other_order(sandbox):
    db, receipt = sandbox
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700}, "orders_requested": [102],
    }))
    db.commit()
    result = build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)
    decoded = json.loads(decrypt_shopify_secret(result.encrypted_payload))
    assert result.orders == 0
    assert decoded["orders"] == []
    assert result.requested_orders_not_resolved == 1
    assert db.query(Order).count() == 2


def test_email_only_request_is_held_without_identity_guess(sandbox):
    db, receipt = sandbox
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"email": "shared@example.com"},
    }))
    db.commit()
    with pytest.raises(ShopifyLocalPrivacyError):
        build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)


def test_unsigned_request_cannot_export(sandbox):
    db, _ = sandbox
    db.query(ShopifyPrivacyAuditEvent).delete()
    db.commit()
    with pytest.raises(ShopifyLocalPrivacyError, match="SIGNED_INTAKE_REQUIRED"):
        build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)


def test_shop_domain_mismatch_cannot_export(sandbox):
    db, receipt = sandbox
    receipt.shop_domain = "different.myshopify.com"
    db.commit()
    with pytest.raises(ShopifyLocalPrivacyError, match="SHOP_SCOPE_UNVERIFIED"):
        build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)


def test_multiple_store_customer_ids_fails_closed(sandbox):
    db, receipt = sandbox
    other_customer = Customer(
        organization_id=receipt.organization_id,
        name="PRIVATE_OTHER_BUYER", phone="999",
    )
    db.add(other_customer)
    db.flush()
    db.add(CustomerStoreProfile(
        organization_id=receipt.organization_id,
        store_id=receipt.store_id, customer_id=other_customer.id,
        external_customer_id="700", currency="COP",
    ))
    db.commit()
    with pytest.raises(ShopifyLocalPrivacyError,
                       match="SHOPIFY_SUBJECT_UNRESOLVED_OR_AMBIGUOUS"):
        build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)


@pytest.mark.parametrize("topic", ["customers/redact", "shop/redact"])
def test_redaction_manifest_identifies_fields_but_changes_no_data(sandbox, topic):
    db, receipt = sandbox
    receipt.topic = topic
    db.commit()
    outcome = build_local_redaction_manifest(db, request_id=RECEIPT_ID)
    assert outcome.mutation_allowed is False
    assert outcome.complete is False
    assert outcome.shared_customer_records_protected == 1
    names = {name for name, _, _ in outcome.fields_by_table}
    assert "orders" in names and "messages" in names
    assert "customer_store_profiles" in names
    assert db.query(Customer).one().name == "SHARED_PRIVATE_NAME"
    assert db.query(Order).count() == 2
    assert db.query(Message).count() == 2


def test_api_never_exposes_export_ciphertext_or_personal_data(sandbox, monkeypatch):
    db, receipt = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "privacy-test-internal-secret")
    with pytest.raises(HTTPException) as exc:
        inspect_shopify_local_customer_export(
            request_id=RECEIPT_ID, x_internal_secret="bad", db=db,
        )
    assert exc.value.status_code == 401
    result = inspect_shopify_local_customer_export(
        request_id=RECEIPT_ID,
        x_internal_secret="privacy-test-internal-secret",
        db=db,
    )
    assert result["orders"] == 1
    assert result["complete"] is False
    for forbidden in ("encrypted_payload", "payload_sha256", "PRIVATE", "email", "phone"):
        assert forbidden not in str(result)
    receipt.topic = "customers/redact"
    db.commit()
    preview = get_shopify_local_redaction_manifest(
        request_id=RECEIPT_ID,
        x_internal_secret="privacy-test-internal-secret",
        db=db,
    )
    assert preview["mutation_allowed"] is False
    assert "PRIVATE_NOTE" not in str(preview)
    assert db.query(Order).count() == 2


@pytest.mark.parametrize("value", ["x", "B" * 64, "", "b" * 63])
def test_invalid_receipt_id_rejected(sandbox, value):
    db, _ = sandbox
    with pytest.raises(ShopifyLocalPrivacyError, match="INVALID_PRIVACY_REQUEST_ID"):
        build_encrypted_local_customer_export(db, request_id=value)


def test_no_redaction_execution_path_and_no_customer_mutation(sandbox):
    db, receipt = sandbox
    receipt.topic = "customers/redact"
    db.commit()
    outcome = build_local_redaction_manifest(db, request_id=RECEIPT_ID)
    assert outcome.mutation_allowed is False
    assert not hasattr(outcome, "execute")
    assert db.query(Order).filter(Order.note == "PRIVATE_NOTE_0").count() == 1


def test_customer_redaction_manifest_respects_explicit_order_scope(sandbox):
    db, receipt = sandbox
    receipt.topic = "customers/redact"
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700}, "orders_to_redact": [101],
    }))
    db.commit()
    manifest = build_local_redaction_manifest(db, request_id=RECEIPT_ID)
    rows = {name: count for name, _, count in manifest.fields_by_table}
    assert rows["orders"] == 1
    assert rows["conversations"] == 1
    assert rows["messages"] == 1
    assert manifest.mutation_allowed is False


def test_customer_redaction_manifest_rejects_other_store_order_id(sandbox):
    db, receipt = sandbox
    receipt.topic = "customers/redact"
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700}, "orders_to_redact": [102],
    }))
    db.commit()
    with pytest.raises(ShopifyLocalPrivacyError,
                       match="REQUESTED_ORDER_SCOPE_UNRESOLVED"):
        build_local_redaction_manifest(db, request_id=RECEIPT_ID)
    assert db.query(Order).filter(Order.note == "PRIVATE_NOTE_0").count() == 1


def test_store_redaction_manifest_counts_all_store_records_only(sandbox):
    db, receipt = sandbox
    receipt.topic = "shop/redact"
    db.commit()
    result = build_local_redaction_manifest(db, request_id=RECEIPT_ID)
    counts = {name: count for name, _, count in result.fields_by_table}
    assert counts["orders"] == 1
    assert counts["conversations"] == 1
    assert counts["messages"] == 1
    assert counts["customer_store_profiles"] == 1


def test_synthetic_redaction_honors_requested_order_subset(sandbox, monkeypatch):
    from app.services.shopify_privacy_synthetic_processor import (
        execute_synthetic_field_redaction,
    )
    db, receipt = sandbox
    receipt.topic = "customers/redact"
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700}, "orders_to_redact": [101],
    }))
    original_order = db.query(Order).filter(Order.shopify_order_id == "101").one()
    other_order = Order(
        organization_id=receipt.organization_id, store_id=receipt.store_id,
        customer_id=original_order.customer_id, shopify_order_id="103",
        order_number="ANOTHER_LOCAL_ORDER", total_amount=2, currency="COP",
        note="UNREQUESTED_ORDER_PRIVATE",
    )
    db.add(other_order)
    db.commit()
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    result = execute_synthetic_field_redaction(db, receipt)
    assert result.complete is False
    assert result.redacted_orders == 1
    db.refresh(original_order)
    db.refresh(other_order)
    assert original_order.note is None
    assert other_order.note == "UNREQUESTED_ORDER_PRIVATE"
    assert receipt.completed_at is None


def test_synthetic_redaction_does_not_mutate_if_requested_order_missing(
    sandbox, monkeypatch,
):
    from app.services.shopify_privacy_synthetic_processor import (
        ShopifyPrivacySyntheticError,
        execute_synthetic_field_redaction,
    )
    db, receipt = sandbox
    receipt.topic = "customers/redact"
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700}, "orders_to_redact": [102],
    }))
    db.commit()
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    with pytest.raises(ShopifyPrivacySyntheticError,
                       match="REQUESTED_ORDER_SCOPE_UNRESOLVED"):
        execute_synthetic_field_redaction(db, receipt)
    assert db.query(Order).filter(Order.note == "PRIVATE_NOTE_0").count() == 1
    assert db.query(Message).filter(Message.text == "PRIVATE_MESSAGE_0").count() == 1


def test_graphql_order_gid_matches_shopify_numeric_payload(sandbox):
    db, receipt = sandbox
    target = db.query(Order).filter(Order.shopify_order_id == "101").one()
    target.shopify_order_id = "gid://shopify/Order/101"
    db.commit()
    export = build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)
    assert export.orders == 1
    assert export.requested_orders_not_resolved == 0
    receipt.topic = "customers/redact"
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700}, "orders_to_redact": [101],
    }))
    db.commit()
    manifest = build_local_redaction_manifest(db, request_id=RECEIPT_ID)
    assert dict((name, count) for name, _, count in manifest.fields_by_table)["orders"] == 1


def test_duplicate_numeric_and_gid_representation_blocks_export(sandbox):
    db, receipt = sandbox
    target = db.query(Order).filter(Order.shopify_order_id == "101").one()
    db.add(Order(
        organization_id=target.organization_id, store_id=target.store_id,
        customer_id=target.customer_id, shopify_order_id="gid://shopify/Order/101",
        order_number="DUPLICATE_GID", total_amount=3, currency="COP",
        note="DUPLICATE_GID_PRIVATE",
    ))
    db.commit()
    with pytest.raises(ShopifyLocalPrivacyError,
                       match="DUPLICATE_SHOPIFY_ORDER_ID"):
        build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)
    assert db.query(Order).count() == 3
