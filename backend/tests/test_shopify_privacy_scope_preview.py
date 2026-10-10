"""Synthetic-only privacy scope preview tests."""
import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Customer, CustomerStoreProfile, Organization, Order,
    ShopifyPrivacyRequest, Store,
)
from app.services.shopify_privacy_scope_preview import (
    ShopifyPrivacyScopeError, preview_shopify_privacy_scope,
)
from app.shopify_security import encrypt_shopify_secret


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic", slug="synthetic", plan="starter")
        db.add(org)
        db.flush()
        stores = []
        for num in (1, 2):
            store = Store(
                organization_id=org.id, name=f"S{num}", slug=f"s{num}",
                country_code="CO", currency="COP", timezone="UTC",
                shopify_domain=f"s{num}.myshopify.com",
            )
            db.add(store)
            stores.append(store)
        db.flush()
        customer = Customer(organization_id=org.id, name="Test", phone="0")
        db.add(customer)
        db.flush()
        for store in stores:
            db.add(CustomerStoreProfile(
                organization_id=org.id, store_id=store.id,
                customer_id=customer.id, external_customer_id="700",
                currency="COP",
            ))
            db.add(Order(
                organization_id=org.id, store_id=store.id,
                customer_id=customer.id, order_number=str(store.id),
                total_amount=1, currency="COP",
            ))
        db.flush()
        receipt = ShopifyPrivacyRequest(
            request_id="r" * 64, topic="customers/redact",
            shop_id="1", shop_domain=stores[0].shopify_domain,
            organization_id=org.id, store_id=stores[0].id,
            selector_encrypted=encrypt_shopify_secret(
                json.dumps({"customer": {"id": 700}})
            ),
        )
        db.add(receipt)
        db.commit()
        yield db, receipt


def test_preview_counts_scoped_records_without_changes(setup):
    db, receipt = setup
    result = preview_shopify_privacy_scope(db, receipt)
    assert result.matched_customer_profiles == 1
    assert result.matched_store_orders == 1
    assert result.shared_customers_protected == 1
    assert db.query(CustomerStoreProfile).count() == 2
    assert db.query(Order).count() == 2


def test_preview_rejects_invalid_store_binding(setup):
    db, receipt = setup
    receipt.shop_domain = "wrong.myshopify.com"
    with pytest.raises(ShopifyPrivacyScopeError, match="STORE_MISMATCH"):
        preview_shopify_privacy_scope(db, receipt)


def test_synthetic_export_encrypts_only_requested_store_data(setup, monkeypatch):
    from app.models import Conversation, Message, OrderItem
    from app.services.shopify_privacy_synthetic_processor import (
        build_synthetic_customer_export,
    )
    from app.shopify_security import decrypt_shopify_secret

    db, receipt = setup
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    receipt.topic = "customers/data_request"
    orders = db.query(Order).order_by(Order.id).all()
    orders[0].note = "SCOPED_ORDER_PRIVATE"
    orders[0].shipping_address = {"address1": "SCOPED_ADDRESS"}
    orders[1].note = "FOREIGN_STORE_PRIVATE"
    db.add(OrderItem(
        organization_id=orders[0].organization_id,
        store_id=orders[0].store_id,
        order_id=orders[0].id,
        title="Synthetic product",
        quantity=1,
        unit_price=4,
        currency="COP",
    ))
    profile = db.query(CustomerStoreProfile).filter(
        CustomerStoreProfile.store_id == receipt.store_id
    ).one()
    convo = Conversation(
        organization_id=receipt.organization_id,
        store_id=receipt.store_id,
        customer_id=profile.customer_id,
        preview="SCOPED_PREVIEW",
    )
    db.add(convo)
    db.flush()
    db.add(Message(
        conversation_id=convo.id,
        sender="customer",
        text="SCOPED_MESSAGE_PRIVATE",
    ))
    db.commit()

    result = build_synthetic_customer_export(db, receipt)
    assert result.completeness == "partial_requires_review"
    assert (result.profile_count, result.order_count) == (1, 1)
    assert (result.conversation_count, result.message_count) == (1, 1)
    assert result.item_count == 1
    assert "SCOPED_ADDRESS" not in result.encrypted_payload
    assert "SCOPED_MESSAGE_PRIVATE" not in result.encrypted_payload

    data = json.loads(decrypt_shopify_secret(result.encrypted_payload))
    plaintext = json.dumps(data)
    assert data["complete"] is False
    assert data["scope"] == "single_verified_shop"
    assert data["orders"][0]["shipping_address"]["address1"] == "SCOPED_ADDRESS"
    assert len(data["orders"][0]["items"]) == 1
    assert data["conversations"][0]["messages"][0]["text"] == "SCOPED_MESSAGE_PRIVATE"
    assert "FOREIGN_STORE_PRIVATE" not in plaintext
    assert db.query(Order).count() == 2
    assert db.query(CustomerStoreProfile).count() == 2


def test_synthetic_export_and_planner_fail_closed_without_test_gate(setup, monkeypatch):
    from app.services.shopify_privacy_synthetic_processor import (
        ShopifyPrivacySyntheticError,
        build_synthetic_customer_export,
        plan_synthetic_redaction,
    )

    db, receipt = setup
    monkeypatch.delenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", raising=False)
    with pytest.raises(ShopifyPrivacySyntheticError, match="SYNTHETIC_TEST_ONLY"):
        plan_synthetic_redaction(db, receipt)
    receipt.topic = "customers/data_request"
    with pytest.raises(ShopifyPrivacySyntheticError, match="SYNTHETIC_TEST_ONLY"):
        build_synthetic_customer_export(db, receipt)


def test_synthetic_redaction_plan_never_modifies_shared_customer(setup, monkeypatch):
    from app.services.shopify_privacy_synthetic_processor import (
        plan_synthetic_redaction,
    )

    db, receipt = setup
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    result = plan_synthetic_redaction(db, receipt)
    assert result.topic == "customers/redact"
    assert result.profile_candidates == 1
    assert result.order_candidates == 1
    assert result.global_customer_records_protected == 1
    assert result.action == "review_only_no_mutations"
    assert result.legal_hold_clearance is False
    assert db.query(Customer).count() == 1
    assert db.query(Order).count() == 2
    assert db.query(CustomerStoreProfile).count() == 2


def test_shop_scope_isolated_from_other_store_in_plan(setup, monkeypatch):
    from app.services.shopify_privacy_synthetic_processor import (
        plan_synthetic_redaction,
    )

    db, receipt = setup
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    receipt.topic = "shop/redact"
    result = plan_synthetic_redaction(db, receipt)
    assert result.profile_candidates == 1
    assert result.order_candidates == 1
    assert result.global_customer_records_protected == 1
    assert db.query(Order).count() == 2


def test_synthetic_export_fails_on_untrusted_scope(setup, monkeypatch):
    from app.services.shopify_privacy_synthetic_processor import (
        build_synthetic_customer_export,
    )

    db, receipt = setup
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    receipt.topic = "customers/data_request"
    receipt.shop_domain = "other.myshopify.com"
    with pytest.raises(ShopifyPrivacyScopeError, match="STORE_MISMATCH"):
        build_synthetic_customer_export(db, receipt)


def test_synthetic_export_unresolved_customer_is_incomplete(setup, monkeypatch):
    from app.services.shopify_privacy_synthetic_processor import (
        build_synthetic_customer_export,
    )
    from app.shopify_security import decrypt_shopify_secret

    db, receipt = setup
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    receipt.topic = "customers/data_request"
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"id": 123456789}})
    )
    result = build_synthetic_customer_export(db, receipt)
    data = json.loads(decrypt_shopify_secret(result.encrypted_payload))
    assert data["complete"] is False
    assert data["orders"] == []
    assert result.order_count == 0


def test_sqlite_redaction_changes_only_target_store_fixture(setup, monkeypatch):
    from app.models import Conversation, Message
    from app.services.shopify_privacy_synthetic_processor import (
        execute_synthetic_field_redaction,
    )

    db, receipt = setup
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    orders = db.query(Order).order_by(Order.id).all()
    source = next(o for o in orders if o.store_id == receipt.store_id)
    other = next(o for o in orders if o.store_id != receipt.store_id)
    source.note = "SOURCE_PII_PRIVATE"
    source.shipping_address = {"address1": "SOURCE_ADDRESS"}
    other.note = "OTHER_SHOP_PII_PRIVATE"
    other.shipping_address = {"address1": "OTHER_ADDRESS"}
    shared = db.query(Customer).one()
    convo = Conversation(
        organization_id=receipt.organization_id,
        store_id=receipt.store_id,
        customer_id=shared.id,
        preview="SOURCE_PREVIEW_PRIVATE",
    )
    db.add(convo)
    db.flush()
    msg = Message(
        conversation_id=convo.id,
        sender="customer",
        text="SOURCE_MESSAGE_PRIVATE",
    )
    db.add(msg)
    db.commit()

    outcome = execute_synthetic_field_redaction(db, receipt)
    assert outcome.complete is False
    assert outcome.redacted_profiles == outcome.redacted_orders == 1
    assert outcome.redacted_conversations == outcome.redacted_messages == 1
    assert outcome.remaining_shared_customer_records == 1
    db.commit()

    db.refresh(source)
    db.refresh(other)
    db.refresh(convo)
    db.refresh(msg)
    db.refresh(shared)
    assert (source.note, source.shipping_address) == (None, None)
    assert convo.preview == ""
    assert msg.text == "[redacted]"
    assert other.note == "OTHER_SHOP_PII_PRIVATE"
    assert other.shipping_address["address1"] == "OTHER_ADDRESS"
    assert shared.name == "Test"
    other_profile = db.query(CustomerStoreProfile).filter(
        CustomerStoreProfile.store_id == other.store_id
    ).one()
    source_profile = db.query(CustomerStoreProfile).filter(
        CustomerStoreProfile.store_id == receipt.store_id
    ).one()
    assert other_profile.external_customer_id == "700"
    assert source_profile.external_customer_id is None


def test_sqlite_redaction_requires_opt_in_and_never_marks_receipt_complete(
    setup, monkeypatch
):
    from app.services.shopify_privacy_synthetic_processor import (
        ShopifyPrivacySyntheticError,
        execute_synthetic_field_redaction,
    )

    db, receipt = setup
    monkeypatch.delenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", raising=False)
    with pytest.raises(ShopifyPrivacySyntheticError, match="SYNTHETIC_TEST_ONLY"):
        execute_synthetic_field_redaction(db, receipt)
    assert db.query(CustomerStoreProfile).filter(
        CustomerStoreProfile.external_customer_id == "700"
    ).count() == 2

    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    result = execute_synthetic_field_redaction(db, receipt)
    assert result.complete is False
    assert receipt.status == "pending_policy_review"
    assert db.query(Customer).one().name == "Test"


def test_synthetic_field_redaction_rejects_data_request_topic(setup, monkeypatch):
    from app.services.shopify_privacy_synthetic_processor import (
        ShopifyPrivacySyntheticError,
        execute_synthetic_field_redaction,
    )

    db, receipt = setup
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    receipt.topic = "customers/data_request"
    with pytest.raises(ShopifyPrivacySyntheticError, match="TOPIC_NOT_REDACTION"):
        execute_synthetic_field_redaction(db, receipt)
    assert db.query(CustomerStoreProfile).filter(
        CustomerStoreProfile.external_customer_id == "700"
    ).count() == 2


def _add_two_synthetic_checkouts(db, receipt):
    """Shared organization customer, different Shopify stores, distinct PII."""
    from datetime import datetime, timedelta
    from app.models import ConversationalCheckout, Conversation, Store

    customer = db.query(Customer).one()
    stores = db.query(Store).order_by(Store.id).all()
    added = []
    for index, store in enumerate(stores):
        convo = Conversation(
            organization_id=receipt.organization_id,
            store_id=store.id,
            customer_id=customer.id,
            preview=f"checkout_convo_{index}",
        )
        db.add(convo)
        db.flush()
        checkout = ConversationalCheckout(
            organization_id=receipt.organization_id,
            store_id=store.id,
            conversation_id=convo.id,
            customer_id=customer.id,
            status="collecting_address",
            currency="COP",
            country_code="CO",
            expires_at=datetime.utcnow() + timedelta(hours=1),
            customer_name=f"NAME_PRIVATE_STORE_{index}",
            phone=f"PHONE_PRIVATE_STORE_{index}",
            address_raw=f"ADDRESS_PRIVATE_STORE_{index}",
            address_line=f"LINE_PRIVATE_STORE_{index}",
            address_complement=f"COMPLEMENT_PRIVATE_STORE_{index}",
            neighborhood=f"NEIGHBORHOOD_PRIVATE_STORE_{index}",
            city=f"CITY_PRIVATE_STORE_{index}",
            region=f"REGION_PRIVATE_STORE_{index}",
            postal_code=f"POSTAL_PRIVATE_STORE_{index}",
            delivery_reference=f"REFERENCE_PRIVATE_STORE_{index}",
            failure_reason=f"FAILURE_PRIVATE_STORE_{index}",
        )
        db.add(checkout)
        added.append(checkout)
    db.commit()
    return added


def test_synthetic_customer_checkout_export_is_encrypted_and_scoped(
    setup, monkeypatch
):
    from app.services.shopify_privacy_synthetic_processor import (
        build_synthetic_customer_export,
        plan_synthetic_redaction,
    )
    from app.shopify_security import decrypt_shopify_secret

    db, receipt = setup
    rows = _add_two_synthetic_checkouts(db, receipt)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    receipt.topic = "customers/data_request"
    preview = preview_shopify_privacy_scope(db, receipt)
    assert preview.matched_conversational_checkouts == 1
    result = build_synthetic_customer_export(db, receipt)
    assert result.checkout_count == 1
    assert "NAME_PRIVATE_STORE_0" not in result.encrypted_payload
    assert "PHONE_PRIVATE_STORE_0" not in result.encrypted_payload
    exported = json.loads(decrypt_shopify_secret(result.encrypted_payload))
    checkouts = exported["conversational_checkouts"]
    assert len(checkouts) == 1
    assert checkouts[0]["customer_name"] == "NAME_PRIVATE_STORE_0"
    assert checkouts[0]["phone"] == "PHONE_PRIVATE_STORE_0"
    assert checkouts[0]["delivery_reference"] == "REFERENCE_PRIVATE_STORE_0"
    assert exported["complete"] is False
    assert "NAME_PRIVATE_STORE_1" not in json.dumps(exported)
    assert "ADDRESS_PRIVATE_STORE_1" not in json.dumps(exported)
    assert rows[0].customer_name == "NAME_PRIVATE_STORE_0"

    receipt.topic = "customers/redact"
    plan = plan_synthetic_redaction(db, receipt)
    assert plan.checkout_candidates == 1
    assert plan.global_customer_records_protected == 1


def test_synthetic_checkout_redaction_preserves_other_store_and_shared_customer(
    setup, monkeypatch
):
    from app.services.shopify_privacy_synthetic_processor import (
        execute_synthetic_field_redaction,
    )

    db, receipt = setup
    source, other = _add_two_synthetic_checkouts(db, receipt)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    result = execute_synthetic_field_redaction(db, receipt)
    assert result.redacted_checkouts == 1
    assert result.complete is False
    assert receipt.status == "pending_policy_review"
    db.commit()
    db.refresh(source)
    db.refresh(other)
    for field in (
        "customer_name", "phone", "address_raw", "address_line",
        "address_complement", "neighborhood", "city", "region",
        "postal_code", "delivery_reference", "failure_reason",
    ):
        assert getattr(source, field) is None
        assert getattr(other, field) is not None
    assert source.country_code == "CO"
    assert source.status == "collecting_address"
    assert db.query(Customer).one().name == "Test"


def test_shop_redaction_includes_all_store_checkouts_not_other_stores(
    setup, monkeypatch
):
    from app.services.shopify_privacy_synthetic_processor import (
        execute_synthetic_field_redaction, plan_synthetic_redaction,
    )

    db, receipt = setup
    source, other = _add_two_synthetic_checkouts(db, receipt)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    receipt.topic = "shop/redact"
    plan = plan_synthetic_redaction(db, receipt)
    assert plan.checkout_candidates == 1
    result = execute_synthetic_field_redaction(db, receipt)
    assert result.redacted_checkouts == 1
    assert result.complete is False
    db.commit()
    db.refresh(source)
    db.refresh(other)
    assert source.customer_name is None
    assert other.customer_name == "NAME_PRIVATE_STORE_1"


def test_checkout_protection_stays_disabled_without_synthetic_gate(
    setup, monkeypatch
):
    from app.services.shopify_privacy_synthetic_processor import (
        ShopifyPrivacySyntheticError, execute_synthetic_field_redaction,
    )

    db, receipt = setup
    source, other = _add_two_synthetic_checkouts(db, receipt)
    monkeypatch.delenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", raising=False)
    with pytest.raises(ShopifyPrivacySyntheticError, match="SYNTHETIC_TEST_ONLY"):
        execute_synthetic_field_redaction(db, receipt)
    assert source.phone == "PHONE_PRIVATE_STORE_0"
    assert other.phone == "PHONE_PRIVATE_STORE_1"


def test_unknown_external_customer_id_never_selects_shared_checkouts(
    setup, monkeypatch
):
    from app.services.shopify_privacy_synthetic_processor import (
        build_synthetic_customer_export,
    )
    from app.shopify_security import decrypt_shopify_secret

    db, receipt = setup
    _add_two_synthetic_checkouts(db, receipt)
    monkeypatch.setenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS", "1")
    receipt.topic = "customers/data_request"
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"id": 99999999}})
    )

    scope = preview_shopify_privacy_scope(db, receipt)
    assert scope.scope_status == "subject_unresolved"
    assert scope.matched_conversational_checkouts == 0
    result = build_synthetic_customer_export(db, receipt)
    assert result.checkout_count == 0
    data = json.loads(decrypt_shopify_secret(result.encrypted_payload))
    assert data["conversational_checkouts"] == []
    assert data["complete"] is False
