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
    build_local_redaction_manifest, inspect_local_customer_export_counts,
)
from app.services.shopify_privacy_export_provenance import (
    ShopifyExportCoverageError, inspect_shopify_export_provenance,
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


def test_order_items_and_messages_remain_bounded_to_store_and_customer(sandbox):
    from app.models import OrderItem

    db, receipt = sandbox
    orders = db.query(Order).order_by(Order.id).all()
    for idx, order in enumerate(orders):
        db.add(OrderItem(
            order_id=order.id, organization_id=order.organization_id,
            store_id=order.store_id, title=f"PRIVATE_ITEM_{idx}",
            sku=f"SKU_{idx}", quantity=1, unit_price=2, currency="COP",
        ))
    db.commit()
    result = build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)
    data = json.loads(decrypt_shopify_secret(result.encrypted_payload))
    assert result.order_items == 1
    assert result.messages == 1
    assert data["orders"][0]["items"][0]["title"] == "PRIVATE_ITEM_0"
    assert data["conversations"][0]["messages"][0]["text"] == "PRIVATE_MESSAGE_0"
    assert "PRIVATE_ITEM_1" not in str(data)
    assert "PRIVATE_MESSAGE_1" not in str(data)
    assert receipt.completed_at is None


def test_cross_tenant_order_item_link_blocks_export_instead_of_omitting(sandbox):
    from app.models import OrderItem

    db, receipt = sandbox
    orders = db.query(Order).order_by(Order.id).all()
    db.add(OrderItem(
        order_id=orders[0].id, organization_id=receipt.organization_id,
        store_id=orders[1].store_id, title="WRONG_STORE_ITEM",
        quantity=1, unit_price=2, currency="COP",
    ))
    db.commit()
    with pytest.raises(ShopifyLocalPrivacyError,
                       match="ORDER_ITEM_TENANCY_MISMATCH"):
        build_encrypted_local_customer_export(db, request_id=RECEIPT_ID)
    assert receipt.completed_at is None
    assert db.query(OrderItem).count() == 1


def test_redaction_manifest_counts_order_items_by_scoped_order(sandbox):
    from app.models import OrderItem

    db, receipt = sandbox
    orders = db.query(Order).order_by(Order.id).all()
    for idx, order in enumerate(orders):
        db.add(OrderItem(
            order_id=order.id, organization_id=order.organization_id,
            store_id=order.store_id, title=f"ITEM_{idx}",
            quantity=1, unit_price=2, currency="COP",
        ))
    receipt.topic = "customers/redact"
    db.commit()
    manifest = build_local_redaction_manifest(db, request_id=RECEIPT_ID)
    counts = {table: count for table, _, count in manifest.fields_by_table}
    assert counts["order_items"] == 1
    assert counts["messages"] == 1
    assert manifest.mutation_allowed is False
    assert db.query(OrderItem).count() == 2


def test_delivery_readiness_lists_retention_and_transport_blockers_without_pii(sandbox):
    from app.services.shopify_privacy_delivery_readiness import (
        inspect_shopify_privacy_delivery_readiness,
    )

    db, receipt = sandbox
    state = inspect_shopify_privacy_delivery_readiness(
        db, request_id=RECEIPT_ID,
    )
    assert state["signed_intake_verified"] is True
    assert state["shop_scope_verified"] is True
    assert state["retention_controls"]
    assert state["processor_controls"]
    assert state["backup_controls"]
    assert state["delivery_controls"]
    assert len(state["required_delivery_safeguards"]) >= 6
    assert "RETENTION_SCHEDULE_AND_LEGAL_HOLDS_UNAPPROVED" in state["blockers"]
    assert "SECURE_DELIVERY_TRANSPORT_NOT_IMPLEMENTED" in state["blockers"]
    assert state["retention_approved"] is False
    assert state["secure_delivery_enabled"] is False
    assert state["delivery_authorized"] is False
    assert state["fulfillment_complete"] is False
    for private in ("PRIVATE_", "shared@example.com", "private-shop-"):
        assert private not in str(state)
    assert receipt.completed_at is None


def test_submitted_or_manually_marked_verified_evidence_never_releases_data(sandbox):
    from app.models import ShopifyPrivacyControlEvidence
    from app.services.shopify_privacy_controls import ALL_CONTROLS
    from app.services.shopify_privacy_delivery_readiness import (
        inspect_shopify_privacy_delivery_readiness,
    )

    db, receipt = sandbox
    for control in ALL_CONTROLS:
        db.add(ShopifyPrivacyControlEvidence(
            request_id=RECEIPT_ID, control=control,
            artifact_sha256="c" * 64, status="verified",
            created_at=datetime.utcnow(),
        ))
    db.commit()
    state = inspect_shopify_privacy_delivery_readiness(
        db, request_id=RECEIPT_ID,
    )
    all_controls = (
        state["retention_controls"] + state["processor_controls"]
        + state["backup_controls"] + state["delivery_controls"]
    )
    assert all(item["evidence_submitted"] for item in all_controls)
    assert all(item["independently_verified"] is False for item in all_controls)
    assert state["delivery_authorized"] is False
    assert state["fulfillment_complete"] is False
    assert receipt.completed_at is None


def test_delivery_readiness_is_internal_only_and_rejects_other_topics(
    sandbox, monkeypatch,
):
    from unittest.mock import patch
    from app.api.shopify_privacy_backlog import get_shopify_privacy_delivery_readiness
    from app.services.shopify_privacy_controls import ShopifyPrivacyControlError
    from app.services.shopify_privacy_delivery_readiness import (
        inspect_shopify_privacy_delivery_readiness,
    )

    db, receipt = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "delivery-review-test-secret")
    with patch(
        "app.api.shopify_privacy_backlog.inspect_shopify_privacy_delivery_readiness"
    ) as checker:
        with pytest.raises(HTTPException) as error:
            get_shopify_privacy_delivery_readiness(
                request_id=RECEIPT_ID, x_internal_secret="invalid", db=db,
            )
        assert error.value.status_code == 401
        checker.assert_not_called()
    response = get_shopify_privacy_delivery_readiness(
        request_id=RECEIPT_ID,
        x_internal_secret="delivery-review-test-secret", db=db,
    )
    assert response["delivery_authorized"] is False

    receipt.topic = "customers/redact"
    db.commit()
    with pytest.raises(ShopifyPrivacyControlError,
                       match="CUSTOMER_EXPORT_TOPIC_REQUIRED"):
        inspect_shopify_privacy_delivery_readiness(db, request_id=RECEIPT_ID)


def test_delivery_readiness_requires_signed_intake(sandbox):
    from app.services.shopify_privacy_controls import ShopifyPrivacyControlError
    from app.services.shopify_privacy_delivery_readiness import (
        inspect_shopify_privacy_delivery_readiness,
    )

    db, receipt = sandbox
    db.query(ShopifyPrivacyAuditEvent).delete()
    db.commit()
    with pytest.raises(ShopifyPrivacyControlError, match="SIGNED_INTAKE_REQUIRED"):
        inspect_shopify_privacy_delivery_readiness(db, request_id=RECEIPT_ID)
    assert receipt.completed_at is None


def test_delivery_readiness_does_not_trust_mismatched_shop(sandbox):
    from app.services.shopify_privacy_delivery_readiness import (
        inspect_shopify_privacy_delivery_readiness,
    )

    db, receipt = sandbox
    receipt.shop_domain = "unexpected-shop.myshopify.com"
    db.commit()
    readiness = inspect_shopify_privacy_delivery_readiness(
        db, request_id=RECEIPT_ID,
    )
    assert readiness["signed_intake_verified"] is True
    assert readiness["shop_scope_verified"] is False
    assert "SHOPIFY_SUBJECT_OR_SHOP_NOT_VERIFIED" in readiness["blockers"]
    assert readiness["delivery_authorized"] is False
    assert readiness["fulfillment_complete"] is False


@pytest.mark.parametrize("topic", ["customers/redact", "shop/redact"])
def test_redaction_manifest_refuses_cross_store_order_items(sandbox, topic):
    """An incorrectly scoped child row must be investigated, never ignored."""
    from app.models import OrderItem

    db, receipt = sandbox
    receipt.topic = topic
    target_order = db.query(Order).filter(
        Order.store_id == receipt.store_id,
    ).one()
    foreign_order = db.query(Order).filter(
        Order.store_id != receipt.store_id,
    ).one()
    db.add(OrderItem(
        organization_id=receipt.organization_id,
        store_id=foreign_order.store_id,
        order_id=target_order.id,
        title="SYNTHETIC_CROSS_STORE_ITEM",
        quantity=1,
        unit_price=1,
        currency="COP",
    ))
    db.commit()
    with pytest.raises(ShopifyLocalPrivacyError, match="ORDER_ITEM_TENANCY_MISMATCH"):
        build_local_redaction_manifest(db, request_id=RECEIPT_ID)
    assert receipt.completed_at is None
    assert db.query(OrderItem).count() == 1
    assert db.query(Order).count() == 2
    assert db.query(Customer).one().name == "SHARED_PRIVATE_NAME"


def test_operator_inspection_does_not_build_or_encrypt_export(sandbox, monkeypatch):
    """Readiness counts must not create even an in-memory customer artifact."""
    from unittest.mock import patch

    db, _ = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "privacy-test-internal-secret")
    with patch(
        "app.services.shopify_privacy_local_processor.encrypt_shopify_secret",
        side_effect=AssertionError("Operator inspection must not export PII"),
    ) as export:
        result = inspect_shopify_local_customer_export(
            request_id=RECEIPT_ID,
            x_internal_secret="privacy-test-internal-secret",
            db=db,
        )
    export.assert_not_called()
    assert result == {
        "request_id": RECEIPT_ID,
        "profiles": 1,
        "orders": 1,
        "order_items": 0,
        "conversations": 1,
        "messages": 1,
        "checkouts": 0,
        "requested_orders_not_resolved": 0,
        "automation": {
            "audience_members": 0,
            "campaign_recipients": 0,
            "delivery_attempts": 0,
            "flow_recipients": 0,
            "flow_node_executions": 0,
            "attribution": "verified_external_customer_id",
            "export_included": False,
            "coverage": "linked_records_only",
        },
        "complete": False,
        "merchant_delivery_allowed": False,
    }
    assert "PRIVATE" not in str(result)


def test_operator_inspection_reconciles_unresolved_requested_order_without_pii(
    sandbox, monkeypatch,
):
    db, receipt = sandbox
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700}, "orders_requested": [102],
    }))
    db.commit()
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "privacy-test-internal-secret")
    result = inspect_shopify_local_customer_export(
        request_id=RECEIPT_ID,
        x_internal_secret="privacy-test-internal-secret",
        db=db,
    )
    assert result["orders"] == 0
    assert result["requested_orders_not_resolved"] == 1
    assert result["messages"] == 1
    assert result["complete"] is False
    assert "PRIVATE_ORDER" not in str(result)


def test_export_inspection_fails_closed_if_automation_provenance_unavailable(
    sandbox, monkeypatch,
):
    from unittest.mock import patch
    from app.services.shopify_privacy_scope_preview import ShopifyPrivacyScopeError

    db, receipt = sandbox
    with patch(
        "app.services.shopify_privacy_local_processor."
        "inspect_shopify_automation_privacy_impact",
        side_effect=ShopifyPrivacyScopeError("INCONSISTENT_STORE_PROVENANCE"),
    ):
        with pytest.raises(
            ShopifyLocalPrivacyError, match="AUTOMATION_PROVENANCE_UNVERIFIED"
        ):
            inspect_local_customer_export_counts(
                db, request_id=RECEIPT_ID,
            )
    assert receipt.completed_at is None
    assert db.query(Order).count() == 2


def test_export_provenance_reports_counted_vs_uncovered_for_shared_customer(sandbox):
    """One subject across two stores: never infer completeness from counts."""
    db, receipt = sandbox
    report = inspect_shopify_export_provenance(db, request_id=RECEIPT_ID)
    rows = {item["source"]: item for item in report["sources"]}
    assert report["signed_intake_verified"] is True
    assert report["subject_store_scope_verified"] is True
    assert report["counted_local_snapshot_sources"] == 6
    assert report["counted_automation_sources"] == 5
    assert rows["customer_store_profiles"]["matched_subject_store_rows"] == 1
    assert rows["orders"]["matched_subject_store_rows"] == 1
    assert rows["conversations"]["matched_subject_store_rows"] == 1
    assert rows["messages"]["matched_subject_store_rows"] == 1
    assert rows["orders"]["reconciliation_state"] == "partial_snapshot_unapproved"
    assert rows["automation_delivery_attempts"]["reconciliation_state"] == (
        "linked_count_only_not_exported"
    )
    assert rows["customers"]["matched_subject_store_rows"] is None
    assert rows["customers"]["reconciliation_state"] == "not_attributed_or_exported"
    assert rows["agent_chat_messages"]["matched_subject_store_rows"] is None
    assert "UNSCANNED_SENSITIVE_SOURCES_REMAIN" in report["blockers"]
    assert report["shared_customer_records_requiring_review"] >= 1
    assert "SHARED_CUSTOMER_IDENTITY_REQUIRES_REVIEW" in report["blockers"]
    assert report["external_review_areas"]
    assert report["complete"] is False
    assert report["live_export_authorized"] is False
    assert report["merchant_delivery_authorized"] is False
    assert report["shopify_fulfillment_complete"] is False
    serialized = json.dumps(report)
    for forbidden in (
        "SHARED_PRIVATE_NAME", "PRIVATE_GLOBAL_PHONE", "shared@example.com",
        "PRIVATE_ADDRESS_0", "PRIVATE_ADDRESS_1",
        "PRIVATE_MESSAGE_0", "PRIVATE_MESSAGE_1",
        "private-shop-id", "privacy-shop-1.myshopify.com",
    ):
        assert forbidden not in serialized
    assert receipt.status == "pending_policy_review"


def test_export_provenance_missing_order_selection_remains_explicit_blocker(sandbox):
    db, receipt = sandbox
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 700}, "orders_requested": [999],
    }))
    db.commit()
    report = inspect_shopify_export_provenance(db, request_id=RECEIPT_ID)
    by_source = {item["source"]: item for item in report["sources"]}
    assert report["unresolved_requested_order_count"] == 1
    assert by_source["orders"]["matched_subject_store_rows"] == 0
    assert by_source["conversations"]["matched_subject_store_rows"] == 1
    assert "REQUESTED_SHOPIFY_ORDERS_UNRESOLVED" in report["blockers"]
    assert report["complete"] is False


def test_export_provenance_requires_signed_intake_and_exact_subject(sandbox):
    db, receipt = sandbox
    db.query(ShopifyPrivacyAuditEvent).delete()
    db.commit()
    with pytest.raises(ShopifyExportCoverageError, match="SIGNED_INTAKE_REQUIRED"):
        inspect_shopify_export_provenance(db, request_id=RECEIPT_ID)
    db.add(ShopifyPrivacyAuditEvent(
        request_id=RECEIPT_ID, event_type="received",
        from_status=None, to_status="pending_policy_review",
        reason_code="tenant_bound", actor_type="shopify_hmac_verified",
        created_at=datetime.utcnow(),
    ))
    receipt.selector_encrypted = encrypt_shopify_secret(json.dumps({
        "customer": {"id": 999999},
    }))
    db.commit()
    with pytest.raises(
        ShopifyExportCoverageError, match="SHOPIFY_SUBJECT_OR_STORE_UNRESOLVED",
    ):
        inspect_shopify_export_provenance(db, request_id=RECEIPT_ID)


def test_export_provenance_rejects_unknown_case_and_invalid_id(sandbox):
    db, _ = sandbox
    with pytest.raises(ShopifyExportCoverageError, match="INVALID_PRIVACY_REQUEST_ID"):
        inspect_shopify_export_provenance(db, request_id="not-a-request")
    with pytest.raises(ShopifyExportCoverageError, match="PRIVACY_REQUEST_NOT_FOUND"):
        inspect_shopify_export_provenance(db, request_id="a" * 64)


def test_export_provenance_does_not_construct_a_customer_export(sandbox, monkeypatch):
    from app.services import shopify_privacy_local_processor as processor
    def forbid(*args, **kwargs):
        raise AssertionError("export must not be generated by provenance inspection")
    monkeypatch.setattr(processor, "build_encrypted_local_customer_export", forbid)
    db, _ = sandbox
    result = inspect_shopify_export_provenance(db, request_id=RECEIPT_ID)
    assert result["contains_customer_data"] is False


def test_export_provenance_internal_endpoint_authenticates_before_db_query(
    sandbox, monkeypatch,
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.db import get_db
    from app.api.shopify_privacy_backlog import router

    db, _ = sandbox
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-private-admin-key")
    app = FastAPI()
    app.include_router(router)
    def provide_db():
        yield db
    app.dependency_overrides[get_db] = provide_db
    client = TestClient(app)
    url = f"/api/internal/shopify/privacy/cases/{RECEIPT_ID}/export/provenance"

    unauthorized = client.get(url)
    assert unauthorized.status_code == 401
    result = client.get(url, headers={"X-Internal-Secret": "synthetic-private-admin-key"})
    assert result.status_code == 200
    assert result.json()["contains_customer_data"] is False
    assert result.json()["live_export_authorized"] is False
    missing = client.get(
        "/api/internal/shopify/privacy/cases/" + "a" * 64 + "/export/provenance",
        headers={"X-Internal-Secret": "synthetic-private-admin-key"},
    )
    assert missing.status_code == 404
    assert "PRIVATE_MESSAGE" not in result.text
    assert "SHARED_PRIVATE_NAME" not in result.text
