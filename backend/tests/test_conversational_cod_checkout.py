"""Regression coverage for conversational COD checkout safety rules."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.model_domains.conversational_checkout import ConversationalCheckout
from app.model_domains.sales_attribution import OrderSalesAttribution
from app.models import (
    Agent,
    CommerceConnection,
    Conversation,
    Customer,
    Order,
    Organization,
    Product,
    ProductVariant,
    Store,
)
from app.services.attributed_order_service import create_attributed_shopify_cod_order
from app.services.conversational_checkout_service import (
    normalize_delivery_address,
    process_conversational_checkout_turn,
)
from app.shopify_cod_orders import create_shopify_cod_order

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_conversational_cod_checkout.db"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
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


def _scenario(db):
    org = Organization(
        name="COD Org",
        slug="cod-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="COD Store",
        slug="cod-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
    )
    db.add(store)
    db.flush()
    customer = Customer(
        organization_id=org.id,
        name="Cliente WhatsApp",
        phone="3001234567",
        email="cliente@example.com",
        country_code="CO",
    )
    db.add(customer)
    agent = Agent(
        organization_id=org.id,
        name="Agente Ventas",
        role="sales",
        active=True,
    )
    db.add(agent)
    db.flush()
    agent.stores.append(store)
    product = Product(
        organization_id=org.id,
        store_id=store.id,
        title="Sandalia AT 77",
        description="Sandalia de prueba",
        active=True,
        cost=40,
    )
    db.add(product)
    db.flush()
    variant = ProductVariant(
        product_id=product.id,
        shopify_variant_id="46142401511615",
        title="Talla 40 Marrón",
        sku="AT77-40-MAR",
        price=100,
        currency="COP",
        inventory_quantity=8,
        available=True,
    )
    db.add(variant)
    connection = CommerceConnection(
        organization_id=org.id,
        store_id=store.id,
        provider="shopify",
        external_store_url="diaglob-poc.myshopify.com",
        access_token_encrypted="encrypted-token",
        scopes="write_orders",
        status="connected",
    )
    db.add(connection)
    db.flush()
    conversation = Conversation(
        organization_id=org.id,
        store_id=store.id,
        customer_id=customer.id,
        agent_id=agent.id,
        channel="WhatsApp",
        preview="",
        unread=0,
        mode="ai",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(conversation)
    db.commit()
    return org, store, customer, agent, product, variant, conversation, connection


def _turn(db, conversation, agent, text):
    return process_conversational_checkout_turn(db, conversation, agent, text)


def _advance_to_address_confirmation(db, conversation, agent):
    assert "Cuántas" in _turn(db, conversation, agent, "quiero comprar Sandalia AT 77 talla 40")
    _turn(db, conversation, agent, "1")
    _turn(db, conversation, agent, "Juan Perez")
    _turn(db, conversation, agent, "Cundinamarca")
    _turn(db, conversation, agent, "Bogota")
    _turn(db, conversation, agent, "calle 80 15 24")
    _turn(db, conversation, agent, "El Lago")
    return _turn(db, conversation, agent, "Apto 302")


def _advance_to_final_confirmation(db, conversation, agent):
    _advance_to_address_confirmation(db, conversation, agent)
    _turn(db, conversation, agent, "sí")
    return _turn(db, conversation, agent, "Edificio gris frente al D1")


def test_colombian_address_is_normalized_without_inventing_fields():
    normalized, score = normalize_delivery_address("calle 80 15 24", "CO")
    assert normalized == "Calle 80 # 15-24"
    assert score >= 60


def test_checkout_rejects_vague_address_then_requires_normalized_confirmation(db):
    _, _, _, agent, _, _, conversation, _ = _scenario(db)
    _turn(db, conversation, agent, "quiero comprar Sandalia AT 77 talla 40")
    _turn(db, conversation, agent, "1")
    _turn(db, conversation, agent, "Juan Perez")
    _turn(db, conversation, agent, "Cundinamarca")
    _turn(db, conversation, agent, "Bogota")

    rejected = _turn(db, conversation, agent, "al lado del parque")
    assert "dirección" in rejected.lower()

    _turn(db, conversation, agent, "calle 80 15 24")
    _turn(db, conversation, agent, "El Lago")
    confirmation = _turn(db, conversation, agent, "Apto 302")

    checkout = db.query(ConversationalCheckout).one()
    assert checkout.address_raw == "calle 80 15 24"
    assert checkout.address_line == "Calle 80 # 15-24"
    assert checkout.address_confirmed is False
    assert checkout.status == "awaiting_address_confirmation"
    assert checkout.address_confidence_score >= 75
    assert "Calle 80 # 15-24" in confirmation
    assert "El Lago" in confirmation
    assert "Bogota" in confirmation
    assert "Cundinamarca" in confirmation


def test_address_correction_clears_confirmation_and_requires_reconfirmation(db):
    _, _, _, agent, _, _, conversation, _ = _scenario(db)
    _advance_to_address_confirmation(db, conversation, agent)
    _turn(db, conversation, agent, "sí")
    checkout = db.query(ConversationalCheckout).one()
    assert checkout.address_confirmed is True
    assert checkout.address_confirmed_at is not None

    # Simulate returning to address confirmation after an operator/customer edit.
    checkout.status = "awaiting_address_confirmation"
    db.commit()
    answer = _turn(db, conversation, agent, "no, corregir")
    db.refresh(checkout)

    assert checkout.status == "collecting_address"
    assert checkout.address_confirmed is False
    assert checkout.address_confirmed_at is None
    assert checkout.address_line is None
    assert checkout.neighborhood is None
    assert "volveré a mostrártela" in answer


def test_ambiguous_final_reply_never_creates_order(db, monkeypatch):
    _, _, _, agent, _, _, conversation, _ = _scenario(db)
    summary = _advance_to_final_confirmation(db, conversation, agent)
    assert "CONFIRMO" in summary

    calls = []
    monkeypatch.setattr(
        "app.services.conversational_checkout_service.create_attributed_shopify_cod_order",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    answer = _turn(db, conversation, agent, "dale")
    checkout = db.query(ConversationalCheckout).one()

    assert calls == []
    assert checkout.status == "awaiting_order_confirmation"
    assert checkout.customer_confirmed is False
    assert "ambigua" in answer


def test_live_price_change_forces_second_final_confirmation(db, monkeypatch):
    _, _, _, agent, _, variant, conversation, _ = _scenario(db)
    _advance_to_final_confirmation(db, conversation, agent)

    calls = []
    monkeypatch.setattr(
        "app.services.conversational_checkout_service.create_attributed_shopify_cod_order",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"ok": True, "order_id": 999, "order_number": "#999"},
    )
    variant.price = 120
    db.commit()

    changed = _turn(db, conversation, agent, "CONFIRMO")
    checkout = db.query(ConversationalCheckout).one()
    assert calls == []
    assert checkout.status == "awaiting_order_confirmation"
    assert checkout.customer_confirmed is False
    assert float(checkout.total) == 120.0
    assert "precio cambió" in changed
    assert "COP 120.00" in changed

    created = _turn(db, conversation, agent, "CONFIRMO")
    db.refresh(checkout)
    assert len(calls) == 1
    assert checkout.status == "order_created"
    assert checkout.created_order_id == 999
    assert "#999" in created


def test_attributed_cod_wrapper_records_ai_closer(db, monkeypatch):
    org, store, customer, agent, _, variant, conversation, _ = _scenario(db)

    def fake_create(**kwargs):
        order = Order(
            organization_id=store.organization_id,
            store_id=store.id,
            customer_id=customer.id,
            order_number="#COD1",
            total_amount=100,
            currency="COP",
            financial_status="pending",
            payment_method="cash_on_delivery",
            payment_status="pending",
            lifecycle_status="confirmed",
            source="shopify_chat_cod",
            idempotency_key="chat-cod:wrapper",
            external_creation_status="created",
        )
        db.add(order)
        db.commit()
        return {"ok": True, "order_id": order.id, "order_number": order.order_number}

    monkeypatch.setattr(
        "app.services.attributed_order_service.create_shopify_cod_order",
        fake_create,
    )
    result = create_attributed_shopify_cod_order(
        db,
        org.id,
        store.id,
        customer_id=customer.id,
        variant_local_id=variant.id,
        quantity=1,
        customer_email=customer.email,
        customer_phone=customer.phone,
        shipping_address={"first_name": "Juan", "address1": "Calle 80 # 15-24", "city": "Bogota", "country_code": "CO"},
        note="COD",
        idempotency_key="chat-cod:wrapper",
        ai_agent_id=agent.id,
        conversation_id=conversation.id,
    )

    attribution = db.query(OrderSalesAttribution).filter(OrderSalesAttribution.order_id == result["order_id"]).one()
    assert attribution.actor_type == "ai"
    assert attribution.ai_agent_id == agent.id
    assert attribution.conversation_id == conversation.id
    assert attribution.source == "ai_conversational_checkout"


def test_shopify_cod_order_sends_confirmed_shipping_data(db, monkeypatch):
    _, store, customer, _, _, variant, _, connection = _scenario(db)
    captured = {}

    class FakeClient:
        def __init__(self, shop_domain, access_token):
            captured["domain"] = shop_domain
            captured["token"] = access_token

        def query(self, query, variables):
            captured["variables"] = variables
            return {
                "orderCreate": {
                    "order": {"id": "gid://shopify/Order/123", "name": "#123"},
                    "userErrors": [],
                }
            }

    monkeypatch.setattr("app.shopify_cod_orders.decrypt_shopify_secret", lambda value: "token")
    monkeypatch.setattr("app.shopify_cod_orders.ShopifyGraphQLClient", FakeClient)
    monkeypatch.setattr("app.shopify_cod_orders.safe_emit_event", lambda **kwargs: None)

    result = create_shopify_cod_order(
        db=db,
        store=store,
        connection=connection,
        customer_id=customer.id,
        variant_local_id=variant.id,
        quantity=1,
        customer_email=customer.email,
        customer_phone=customer.phone,
        shipping_address={
            "first_name": "Juan",
            "last_name": "Perez",
            "address1": "Calle 80 # 15-24",
            "address2": "Apto 302 · Barrio El Lago",
            "city": "Bogota",
            "province": "Cundinamarca",
            "country_code": "CO",
            "phone": customer.phone,
        },
        note="Confirmed address",
        idempotency_key="chat-cod:provider",
    )

    payload = captured["variables"]["order"]
    assert payload["shippingAddress"]["address1"] == "Calle 80 # 15-24"
    assert payload["shippingAddress"]["address2"] == "Apto 302 · Barrio El Lago"
    assert payload["shippingAddress"]["province"] == "Cundinamarca"
    assert payload["shippingAddress"]["countryCode"] == "CO"
    assert payload["tags"] == ["DIAGLOB_CHAT", "DIAGLOB_COD"]

    order = db.query(Order).filter(Order.id == result["order_id"]).one()
    assert order.payment_method == "cash_on_delivery"
    assert order.payment_status == "pending"
    assert order.lifecycle_status == "confirmed"
    assert order.customer_id == customer.id
