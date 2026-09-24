"""Customer-scoped conversational order intelligence tests."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.shipments import Shipment, TrackingEvent
from app.model_domains.supplier_orders import SupplierOrder
from app.models import Customer, Order, Organization, Store
from app.services.order_intelligence import (
    build_customer_order_context,
    is_order_intent,
)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def data(db):
    org = Organization(
        name="Chat Orders Org",
        slug="chat-orders-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="US Store",
        slug="chat-orders-store",
        country_code="US",
        currency="USD",
        timezone="America/New_York",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.flush()
    alice = Customer(
        organization_id=org.id,
        name="Alice",
        phone="+15550000001",
        email="alice@example.com",
        country_code="US",
        created_at=datetime.utcnow(),
    )
    bob = Customer(
        organization_id=org.id,
        name="Bob",
        phone="+15550000002",
        email="bob@example.com",
        country_code="US",
        created_at=datetime.utcnow(),
    )
    db.add_all([alice, bob])
    db.flush()

    alice_old = Order(
        organization_id=org.id,
        store_id=store.id,
        customer_id=alice.id,
        order_number="#1001",
        total_amount=30,
        currency="USD",
        financial_status="paid",
        fulfillment_status="fulfilled",
        source="shopify",
        created_at=datetime(2026, 9, 20, 10, 0, 0),
        updated_at=datetime(2026, 9, 20, 10, 0, 0),
    )
    alice_new = Order(
        organization_id=org.id,
        store_id=store.id,
        customer_id=alice.id,
        order_number="#1002",
        total_amount=45,
        currency="USD",
        financial_status="paid",
        fulfillment_status="fulfilled",
        source="shopify",
        created_at=datetime(2026, 9, 23, 10, 0, 0),
        updated_at=datetime(2026, 9, 23, 10, 0, 0),
    )
    bob_order = Order(
        organization_id=org.id,
        store_id=store.id,
        customer_id=bob.id,
        order_number="#2001",
        total_amount=99,
        currency="USD",
        financial_status="paid",
        fulfillment_status="fulfilled",
        source="shopify",
        created_at=datetime(2026, 9, 24, 8, 0, 0),
        updated_at=datetime(2026, 9, 24, 8, 0, 0),
    )
    db.add_all([alice_old, alice_new, bob_order])
    db.flush()

    supplier = SupplierOrder(
        organization_id=org.id,
        store_id=store.id,
        order_id=alice_new.id,
        provider="cj",
        provider_order_number="DG-1-1",
        external_order_id="SECRET-CJ-ID",
        supplier_status="SHIPPED",
        supplier_substatus=None,
        creation_status="created",
        idempotency_key="alice-1002",
        product_amount=7.25,
        postage_amount=5.75,
        order_amount=13,
        actual_payment=13,
        currency="USD",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(supplier)
    db.flush()

    shipment = Shipment(
        organization_id=org.id,
        store_id=store.id,
        order_id=alice_new.id,
        supplier_order_id=supplier.id,
        provider="cj",
        tracking_number="TRACK-ALICE-1002",
        tracking_provider="USPS",
        normalized_status="OUT_FOR_DELIVERY",
        last_event_at=datetime(2026, 9, 24, 9, 0, 0),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(shipment)
    db.flush()
    db.add(
        TrackingEvent(
            shipment_id=shipment.id,
            provider_event_key="event-1",
            provider_status_code=10,
            normalized_status="OUT_FOR_DELIVERY",
            description="Out for delivery",
            location="New York, NY",
            event_at=datetime(2026, 9, 24, 9, 0, 0),
            created_at=datetime.utcnow(),
        )
    )
    db.commit()
    return org, store, alice, bob


def test_order_intent_does_not_trigger_on_generic_shipping_question():
    assert is_order_intent("Do you offer free shipping?") is False
    assert is_order_intent("Where is my order?") is True
    assert is_order_intent("tracking number please") is True
    assert is_order_intent("pedido #1002") is True


def test_latest_customer_order_includes_real_tracking_only(db, data):
    org, store, alice, _bob = data

    context = build_customer_order_context(
        db,
        organization_id=org.id,
        store_id=store.id,
        customer_id=alice.id,
        question="Where is my order?",
    )

    assert context["requested"] is True
    assert context["orders"][0]["order_number"] == "#1002"
    shipment = context["orders"][0]["shipment"]
    assert shipment["status"] == "OUT_FOR_DELIVERY"
    assert shipment["tracking_number"] == "TRACK-ALICE-1002"
    assert shipment["carrier"] == "USPS"
    assert shipment["events"][0]["description"] == "Out for delivery"

    rendered = repr(context)
    assert "SECRET-CJ-ID" not in rendered
    assert "7.25" not in rendered
    assert "5.75" not in rendered


def test_explicit_order_reference_selects_requested_order(db, data):
    org, store, alice, _bob = data

    context = build_customer_order_context(
        db,
        organization_id=org.id,
        store_id=store.id,
        customer_id=alice.id,
        question="What happened with order #1001?",
    )

    assert len(context["orders"]) == 1
    assert context["orders"][0]["order_number"] == "#1001"


def test_customer_scope_never_exposes_another_customers_order(db, data):
    org, store, alice, _bob = data

    context = build_customer_order_context(
        db,
        organization_id=org.id,
        store_id=store.id,
        customer_id=alice.id,
        question="Where is order #2001?",
    )

    assert context["orders"] == []


def test_non_order_question_has_no_order_context(db, data):
    org, store, alice, _bob = data

    context = build_customer_order_context(
        db,
        organization_id=org.id,
        store_id=store.id,
        customer_id=alice.id,
        question="Do you have the blue version in stock?",
    )

    assert context is None
