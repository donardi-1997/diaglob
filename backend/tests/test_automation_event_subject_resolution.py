"""Regression tests for trusted automation origin from Shopify and messaging."""
import importlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    Conversation, Customer, CustomerStoreProfile, Message, Order,
    Organization, Store,
)
from app.services.automation_event_subject_resolution import (
    resolve_conversation_event_customer,
    resolve_shopify_order_event_customer,
)


@pytest.fixture()
def scope():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            org = Organization(name="Synthetic merchant", slug="event-provenance-synthetic")
            other = Organization(name="Unrelated merchant", slug="event-provenance-other")
            db.add_all([org, other])
            db.flush()
            store = Store(
                organization_id=org.id, name="Shopify shop", slug="event-shopify",
                country_code="CO", currency="COP", timezone="America/Bogota",
            )
            store2 = Store(
                organization_id=org.id, name="Second shop", slug="event-second",
                country_code="CO", currency="COP", timezone="America/Bogota",
            )
            outside = Store(
                organization_id=other.id, name="Foreign", slug="event-foreign",
                country_code="CO", currency="COP", timezone="America/Bogota",
            )
            db.add_all([store, store2, outside])
            db.flush()
            customer = Customer(
                organization_id=org.id, name="PRIVATE_BUYER_NAME",
                phone="PRIVATE_BUYER_PHONE",
            )
            other_customer = Customer(
                organization_id=org.id, name="OTHER_PRIVATE_NAME",
                phone="OTHER_PRIVATE_PHONE",
            )
            db.add_all([customer, other_customer])
            db.flush()
            db.add_all([
                CustomerStoreProfile(
                    organization_id=org.id, store_id=store.id,
                    customer_id=customer.id, external_customer_id="shopify-501",
                    currency="COP",
                ),
                CustomerStoreProfile(
                    organization_id=org.id, store_id=store2.id,
                    customer_id=customer.id, external_customer_id="shopify-999",
                    currency="COP",
                ),
            ])
            order = Order(
                organization_id=org.id, store_id=store.id, customer_id=customer.id,
                order_number="ORD-1", total_amount=110, currency="COP",
                source="shopify", shopify_order_id="501",
            )
            conversation = Conversation(
                organization_id=org.id, store_id=store.id,
                customer_id=customer.id, channel="WhatsApp", preview="PRIVATE_TEXT",
            )
            unrelated = Conversation(
                organization_id=org.id, store_id=store2.id,
                customer_id=customer.id, channel="Telegram", preview="PRIVATE_TEXT_OTHER",
            )
            no_profile = Conversation(
                organization_id=org.id, store_id=store.id,
                customer_id=other_customer.id, channel="Instagram", preview="PRIVATE_TEXT_2",
            )
            db.add_all([order, conversation, unrelated, no_profile])
            db.flush()
            message = Message(
                conversation_id=conversation.id, sender="customer", text="PRIVATE_MESSAGE",
                provider="whatsapp", external_message_id="synthetic-mid",
            )
            db.add(message)
            db.commit()
            yield db, org, store, store2, outside, customer, other_customer, order, conversation, unrelated, no_profile, message
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_signed_shopify_order_must_match_both_persisted_store_and_external_subject(scope):
    db, org, store, store2, outside, customer, other_customer, order, *_ = scope
    kwargs = dict(db=db, organization_id=org.id, store_id=store.id, order_id=order.id)
    assert resolve_shopify_order_event_customer(
        **kwargs, external_shopify_customer_id="shopify-501",
    ) == customer.id
    for ext in ("shopify-999", "not-same-shopify-buyer", None, ""):
        assert resolve_shopify_order_event_customer(
            **kwargs, external_shopify_customer_id=ext,
        ) is None
    assert resolve_shopify_order_event_customer(
        db, organization_id=org.id, store_id=store2.id,
        order_id=order.id, external_shopify_customer_id="shopify-501",
    ) is None
    assert resolve_shopify_order_event_customer(
        db, organization_id=outside.organization_id, store_id=outside.id,
        order_id=order.id, external_shopify_customer_id="shopify-501",
    ) is None
    assert resolve_shopify_order_event_customer(
        db, organization_id=org.id, store_id=store.id,
        order_id=True, external_shopify_customer_id="shopify-501",
    ) is None
    assert other_customer.id != customer.id


def test_ambiguous_shopify_external_id_does_not_claim_customer(scope):
    db, org, store, _, _, customer, other_customer, order, *_ = scope
    db.add(CustomerStoreProfile(
        organization_id=org.id, store_id=store.id,
        customer_id=other_customer.id, external_customer_id="shopify-501",
        currency="COP",
    ))
    db.commit()
    assert resolve_shopify_order_event_customer(
        db, organization_id=org.id, store_id=store.id,
        order_id=order.id, external_shopify_customer_id="shopify-501",
    ) is None
    assert customer.id != other_customer.id


def test_conversation_can_assert_only_explicitly_store_linked_local_customer(scope):
    db, org, store, store2, outside, customer, _, _, conversation, unrelated, no_profile, _ = scope
    assert resolve_conversation_event_customer(
        db, organization_id=org.id, store_id=store.id,
        conversation_id=conversation.id,
    ) == customer.id
    assert resolve_conversation_event_customer(
        db, organization_id=org.id, store_id=store2.id,
        conversation_id=conversation.id,
    ) is None
    assert resolve_conversation_event_customer(
        db, organization_id=org.id, store_id=store.id,
        conversation_id=unrelated.id,
    ) is None
    assert resolve_conversation_event_customer(
        db, organization_id=org.id, store_id=store.id,
        conversation_id=no_profile.id,
    ) is None
    assert resolve_conversation_event_customer(
        db, organization_id=outside.organization_id, store_id=outside.id,
        conversation_id=conversation.id,
    ) is None


@pytest.mark.parametrize("module_name", (
    "app.services.whatsapp_webhooks",
    "app.services.instagram_webhooks",
    "app.services.telegram_webhooks",
))
def test_message_emitters_use_database_relation_not_message_payload(
    scope, monkeypatch, module_name,
):
    db, org, store, _, _, customer, _, _, conversation, _, no_profile, message = scope
    module = importlib.import_module(module_name)
    calls = []
    monkeypatch.setattr(
        module, "safe_emit_event", lambda *args, **kwargs: calls.append(kwargs),
    )
    if module_name.endswith("whatsapp_webhooks"):
        import app.services.product_analytics as metrics
        monkeypatch.setattr(metrics, "track_first_whatsapp_inbound", lambda **kwargs: None)

    module.emit_webhook_events(
        db,
        [(conversation, None)],
        [(message, conversation, None)],
    )
    assert len(calls) == 2
    assert all(call["subject_customer_id"] == customer.id for call in calls)
    assert all(
        "PRIVATE" not in str(call["subject_customer_id"]) for call in calls
    )
    calls.clear()
    module.emit_webhook_events(
        db,
        [(no_profile, None)],
        [(message, no_profile, None)],
    )
    assert len(calls) == 2
    assert all(call["subject_customer_id"] is None for call in calls)
