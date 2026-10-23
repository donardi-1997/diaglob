"""Regression coverage for conversational COD checkout safety rules."""
from datetime import datetime, timedelta

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
    OrderItem,
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
from app.shopify_orders import create_shopify_draft_order, build_draft_order_input
from app.shopify_client import ShopifyUserError
from app.services.shopify_chat_draft_reconciliation import (
    ShopifyDraftConversionNotReady,
    verified_chat_draft_for_order,
)
from app.services.shopify_webhook_service import process_shopify_order_webhook

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


def test_zero_price_is_not_offered_for_conversational_checkout(db):
    _, _, _, agent, _, variant, conversation, _ = _scenario(db)
    variant.price = 0
    db.commit()
    _turn(db, conversation, agent, "quiero comprar Sandalia AT 77 talla 40")
    assert db.query(ConversationalCheckout).count() == 0


def test_price_becoming_zero_blocks_final_confirmation(db, monkeypatch):
    _, _, _, agent, _, variant, conversation, _ = _scenario(db)
    _advance_to_final_confirmation(db, conversation, agent)
    calls = []
    monkeypatch.setattr(
        "app.services.conversational_checkout_service.create_attributed_shopify_cod_order",
        lambda *args, **kwargs: calls.append(kwargs),
    )
    variant.price = 0
    db.commit()
    _turn(db, conversation, agent, "CONFIRMO")
    checkout = db.query(ConversationalCheckout).one()
    assert calls == []
    assert checkout.status == "failed"
    assert checkout.customer_confirmed is False


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


def test_chat_checkout_draft_has_shipping_link_without_premature_order_event(db, monkeypatch):
    """Buyer has a Shopify checkout link; no Shopify Order exists yet."""
    _, store, customer, _, _, variant, _, connection = _scenario(db)
    captured = {"calls": 0, "events": []}

    class FakeClient:
        def __init__(self, shop_domain, access_token):
            assert shop_domain == "diaglob-poc.myshopify.com"

        def query(self, query, variables):
            captured["calls"] += 1
            captured["input"] = variables["input"]
            assert "draftOrderCreate" in query
            return {
                "draftOrderCreate": {
                    "draftOrder": {
                        "id": "gid://shopify/DraftOrder/987",
                        "name": "#D987",
                        "invoiceUrl": "https://diaglob-poc.myshopify.com/123456/invoices/draft-token",
                        "totalPriceSet": {"shopMoney": {"amount": "100.00", "currencyCode": "COP"}},
                    },
                    "userErrors": [],
                }
            }

    monkeypatch.setattr("app.shopify_orders.decrypt_shopify_secret", lambda value: "synthetic")
    monkeypatch.setattr("app.shopify_orders.ShopifyGraphQLClient", FakeClient)
    monkeypatch.setattr(
        "app.shopify_orders.safe_emit_event",
        lambda **kwargs: captured["events"].append(kwargs["event_type"]),
    )
    shipping = {
        "firstName": "Cliente",
        "lastName": "Sintético",
        "address1": "Calle 80 # 15-24",
        "address2": "Apto 302",
        "city": "Bogota",
        "countryCode": "CO",
        "phone": customer.phone,
    }
    params = {
        "db": db,
        "store": store,
        "connection": connection,
        "items_payload": [{"variant_local_id": variant.id, "quantity": 1}],
        "customer_email": customer.email,
        "customer_name": customer.name,
        "customer_phone": customer.phone,
        "customer_id": customer.id,
        "shipping_address": shipping,
        "note": "Synthetic conversational checkout",
        "idempotency_key": "chat-checkout:987:123",
        "source": "shopify_chat_checkout",
    }
    result = create_shopify_draft_order(**params)
    assert result["invoice_url"].startswith("https://diaglob-poc.myshopify.com/")
    assert result["shopify_draft_order_id"] == "gid://shopify/DraftOrder/987"
    assert result["status"] == "pending"
    assert captured["input"]["shippingAddress"] == shipping
    assert captured["input"]["phone"] == customer.phone
    assert {"key": "diaglob_checkout_ref", "value": "chat-checkout:987:123"} in captured["input"]["customAttributes"]
    assert "name" not in captured["input"]
    assert captured["events"] == []
    order = db.query(Order).filter(Order.id == result["order_id"]).one()
    assert order.shopify_order_id is None
    assert order.source == "shopify_chat_checkout"
    assert order.payment_status == "pending"
    assert order.customer_id == customer.id

    replay = create_shopify_draft_order(**params)
    assert replay["idempotent"] is True
    assert captured["calls"] == 1
    assert db.query(Order).count() == 1


@pytest.mark.parametrize(
    "invoice_url",
    [
        "http://unsafe.example.invalid/checkout",
        "https://evil.example.invalid/123456/invoices/draft-token",
        "https://diaglob-poc.myshopify.com.evil.invalid/123456/invoices/token",
        "https://diaglob-poc.myshopify.com:444/123456/invoices/token",
        "https://diaglob-poc.myshopify.com/redirect?next=/invoices/token",
    ],
)
def test_chat_checkout_draft_rejects_insecure_link_without_duplicate_order(
    db, monkeypatch, invoice_url
):
    _, store, customer, _, _, variant, _, connection = _scenario(db)

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def query(self, query, variables):
            return {
                "draftOrderCreate": {
                    "draftOrder": {
                        "id": "gid://shopify/DraftOrder/55",
                        "invoiceUrl": invoice_url,
                        "totalPriceSet": {"shopMoney": {"amount": "100.00", "currencyCode": "COP"}},
                    },
                    "userErrors": [],
                }
            }

    monkeypatch.setattr("app.shopify_orders.decrypt_shopify_secret", lambda value: "synthetic")
    monkeypatch.setattr("app.shopify_orders.ShopifyGraphQLClient", FakeClient)
    monkeypatch.setattr("app.shopify_orders.safe_emit_event", lambda **kwargs: None)
    with pytest.raises(ShopifyUserError, match="SHOPIFY_CHECKOUT_LINK_UNAVAILABLE"):
        create_shopify_draft_order(
            db=db, store=store, connection=connection,
            items_payload=[{"variant_local_id": variant.id, "quantity": 1}],
            customer_id=customer.id,
            customer_email=customer.email,
            idempotency_key="chat-checkout:55:123",
            source="shopify_chat_checkout",
        )
    order = db.query(Order).one()
    assert order.external_creation_status == "unknown"
    assert order.shopify_order_id is None


def test_draft_shipping_input_rejects_unsupported_shopify_fields():
    with pytest.raises(ValueError, match="SHOPIFY_DRAFT_SHIPPING_ADDRESS_INVALID"):
        build_draft_order_input(
            line_items=[],
            note=None,
            customer_email=None,
            customer_name=None,
            shipping_address={
                "address1": "Calle 80 # 15-24", "countryCode": "CO",
                "province": "Cundinamarca",
            },
        )


def _stage_synthetic_checkout_draft(db, store, customer):
    order = Order(
        organization_id=store.organization_id,
        store_id=store.id,
        customer_id=customer.id,
        order_number="#D987",
        total_amount=100,
        currency="COP",
        financial_status="pending",
        payment_status="pending",
        source="shopify_chat_checkout",
        idempotency_key="chat-checkout:987:123",
        shopify_draft_order_id="gid://shopify/DraftOrder/987",
        external_creation_status="created",
    )
    db.add(order)
    db.flush()
    db.add(OrderItem(
        order_id=order.id,
        organization_id=store.organization_id,
        store_id=store.id,
        title="Pending draft line",
        quantity=1,
        unit_price=100,
        currency="COP",
    ))
    db.commit()
    return order


def test_draft_reconciliation_requires_shopify_verified_order_relationship(db, monkeypatch):
    _, store, customer, _, _, _, _, connection = _scenario(db)
    pending = _stage_synthetic_checkout_draft(db, store, customer)
    called = []

    class FakeClient:
        def __init__(self, shop_domain, access_token):
            assert shop_domain == "diaglob-poc.myshopify.com"
            assert access_token == "synthetic-token"

        def query(self, query, variables):
            called.append(variables)
            return {
                "draftOrder": {
                    "id": variables["draftId"],
                    "order": {"id": "gid://shopify/Order/456"},
                }
            }

    monkeypatch.setattr(
        "app.services.shopify_chat_draft_reconciliation.connection_access_token",
        lambda *args, **kwargs: "synthetic-token",
    )
    monkeypatch.setattr(
        "app.services.shopify_chat_draft_reconciliation.ShopifyGraphQLClient",
        FakeClient,
    )
    attrs = [{"name": "diaglob_checkout_ref", "value": "chat-checkout:987:123"}]
    assert verified_chat_draft_for_order(
        db, connection=connection, shopify_order_id="456", note_attributes=attrs,
    ).id == pending.id
    assert called == [{"draftId": "gid://shopify/DraftOrder/987"}]

    # A copied or buyer-supplied marker cannot claim an unrelated order.
    assert verified_chat_draft_for_order(
        db, connection=connection, shopify_order_id="789", note_attributes=attrs,
    ) is None
    assert verified_chat_draft_for_order(
        db, connection=connection, shopify_order_id="456",
        note_attributes=attrs + attrs,
    ) is None


def test_draft_reconciliation_cannot_claim_another_store(db, monkeypatch):
    org, store, customer, _, _, _, _, connection = _scenario(db)
    _stage_synthetic_checkout_draft(db, store, customer)

    def no_provider(*args, **kwargs):
        raise AssertionError("must not access Shopify for foreign tenant/store")

    monkeypatch.setattr(
        "app.services.shopify_chat_draft_reconciliation.ShopifyGraphQLClient",
        no_provider,
    )
    foreign_connection = CommerceConnection(
        organization_id=org.id, store_id=store.id + 1000,
        provider="shopify", external_store_url="other.myshopify.com",
        status="connected",
    )
    assert verified_chat_draft_for_order(
        db, connection=foreign_connection, shopify_order_id="456",
        note_attributes=[{"name": "diaglob_checkout_ref", "value": "chat-checkout:987:123"}],
    ) is None


def test_signed_shopify_order_webhook_converts_chat_draft_without_duplicate(db, monkeypatch):
    _, store, customer, _, _, variant, _, connection = _scenario(db)
    draft = _stage_synthetic_checkout_draft(db, store, customer)
    events = []

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def query(self, query, variables):
            return {
                "draftOrder": {
                    "id": "gid://shopify/DraftOrder/987",
                    "order": {"id": "gid://shopify/Order/456"},
                }
            }

    monkeypatch.setattr(
        "app.services.shopify_chat_draft_reconciliation.connection_access_token",
        lambda *args, **kwargs: "synthetic-token",
    )
    monkeypatch.setattr(
        "app.services.shopify_chat_draft_reconciliation.ShopifyGraphQLClient",
        FakeClient,
    )
    monkeypatch.setattr(
        "app.services.shopify_webhook_service.evaluate_shopify_privacy_suppression",
        lambda *args, **kwargs: (None, False),
    )
    monkeypatch.setattr(
        "app.services.shopify_webhook_service._upsert_customer",
        lambda *args, **kwargs: customer,
    )
    monkeypatch.setattr(
        "app.services.shopify_webhook_service._refresh_customer_store_profile",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.shopify_webhook_service.resolve_shopify_order_event_customer",
        lambda *args, **kwargs: customer.id,
    )
    monkeypatch.setattr(
        "app.services.shopify_webhook_service.safe_emit_event",
        lambda **kwargs: events.append(kwargs["event_type"]),
    )

    payload = {
        "id": 456, "name": "#456", "current_total_price": "100.00",
        "currency": "COP", "financial_status": "pending",
        "fulfillment_status": None,
        "note_attributes": [
            {"name": "diaglob_checkout_ref", "value": "chat-checkout:987:123"},
        ],
        "line_items": [
            {"id": 999, "variant_id": int(variant.shopify_variant_id),
             "title": variant.title, "sku": variant.sku,
             "price": "100.00", "quantity": 1},
        ],
    }
    first = process_shopify_order_webhook(
        db, connection=connection, topic="orders/create", payload=payload,
    )
    assert first["order_id"] == draft.id
    assert first["action"] == "created"
    db.refresh(draft)
    assert draft.shopify_order_id == "456"
    assert draft.source == "shopify_chat_checkout"
    assert db.query(Order).count() == 1
    assert db.query(OrderItem).filter(OrderItem.order_id == draft.id).count() == 1
    assert events == ["order.created"]

    repeated = process_shopify_order_webhook(
        db, connection=connection, topic="orders/create", payload=payload,
    )
    assert repeated["order_id"] == draft.id
    assert db.query(Order).count() == 1
    assert len(events) == 1


def test_draft_reconciliation_waits_for_shopify_conversion_without_duplicate(db, monkeypatch):
    _, store, customer, _, _, _, _, connection = _scenario(db)
    pending = _stage_synthetic_checkout_draft(db, store, customer)

    class ShopifyStillIndexing:
        def __init__(self, **kwargs):
            pass

        def query(self, query, variables):
            return {
                "draftOrder": {
                    "id": "gid://shopify/DraftOrder/987",
                    "order": None,
                }
            }

    monkeypatch.setattr(
        "app.services.shopify_chat_draft_reconciliation.connection_access_token",
        lambda *args, **kwargs: "synthetic-token",
    )
    monkeypatch.setattr(
        "app.services.shopify_chat_draft_reconciliation.ShopifyGraphQLClient",
        ShopifyStillIndexing,
    )
    with pytest.raises(ShopifyDraftConversionNotReady):
        verified_chat_draft_for_order(
            db, connection=connection, shopify_order_id="456",
            note_attributes=[
                {"name": "diaglob_checkout_ref", "value": "chat-checkout:987:123"},
            ],
        )
    assert db.query(Order).count() == 1
    db.refresh(pending)
    assert pending.shopify_order_id is None


def test_shopify_checkout_handoff_is_opt_in_and_never_declares_an_order_complete(
    db, monkeypatch
):
    org, store, customer, agent, _, _, conversation, _ = _scenario(db)
    _advance_to_final_confirmation(db, conversation, agent)
    drafts_created = []

    def fake_checkout_draft(**kwargs):
        drafts_created.append(kwargs)
        order = Order(
            organization_id=org.id, store_id=store.id, customer_id=customer.id,
            order_number="#D98", total_amount=100, currency="COP",
            financial_status="pending", payment_status="pending",
            shopify_draft_order_id="gid://shopify/DraftOrder/98",
            invoice_url="https://diaglob-poc.myshopify.com/1/invoices/test-token",
            idempotency_key=kwargs["idempotency_key"],
            source="shopify_chat_checkout", external_creation_status="created",
        )
        db.add(order)
        db.commit()
        return {
            "ok": True, "order_id": order.id,
            "shopify_draft_order_id": order.shopify_draft_order_id,
            "invoice_url": order.invoice_url,
            "external_creation_status": "created",
        }

    monkeypatch.setenv("SHOPIFY_CHAT_CHECKOUT_VIA_DRAFT", "true")
    monkeypatch.setattr(
        "app.services.conversational_checkout_service.create_shopify_draft_order",
        fake_checkout_draft,
    )
    result = _turn(db, conversation, agent, "CONFIRMO")
    checkout = db.query(ConversationalCheckout).one()
    assert checkout.status == "awaiting_shopify_checkout"
    assert checkout.created_order_id is not None
    assert len(drafts_created) == 1
    assert drafts_created[0]["idempotency_key"] == (
        f"chat-checkout:{checkout.id}:{conversation.id}"
    )
    assert "invoices/test-token" in result
    assert "solo se confirma cuando termines el checkout" in result
    assert db.query(Order).one().shopify_order_id is None

    repeated = _turn(db, conversation, agent, "CONFIRMO")
    assert "invoices/test-token" in repeated
    assert len(drafts_created) == 1
    assert checkout.status == "awaiting_shopify_checkout"

    cancellation = _turn(db, conversation, agent, "CANCELAR")
    db.refresh(checkout)
    assert checkout.status == "awaiting_shopify_checkout"
    assert "no se ha cancelado" in cancellation
    assert len(drafts_created) == 1


def test_shopify_checkout_pending_state_is_allowed_by_sqlalchemy_constraint(db):
    org, store, customer, agent, _, _, conversation, _ = _scenario(db)
    checkout = ConversationalCheckout(
        organization_id=org.id, store_id=store.id,
        conversation_id=conversation.id, customer_id=customer.id,
        ai_agent_id=agent.id, status="awaiting_shopify_checkout",
        quantity=1, currency="COP", country_code="CO",
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(checkout)
    db.commit()
    assert checkout.status == "awaiting_shopify_checkout"
