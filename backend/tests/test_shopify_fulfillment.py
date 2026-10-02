"""Shopify fulfillment creation from CJ tracking tests."""

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.shipments import Shipment
from app.model_domains.supplier_integrations import SupplierConnection  # noqa: F401
from app.model_domains.supplier_orders import SupplierOrder, SupplierOrderItem
from app.models import CommerceConnection, Order, OrderItem, Organization, Store
from app.services import shopify_fulfillment as service


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def seed(db):
    org = Organization(
        name="Shopify Fulfillment Org",
        slug="shopify-fulfillment-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Shopify Fulfillment Store",
        slug="shopify-fulfillment-store",
        country_code="US",
        currency="USD",
        timezone="UTC",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.flush()
    order = Order(
        organization_id=org.id,
        store_id=store.id,
        shopify_order_id="9001",
        order_number="1001",
        total_amount=20,
        currency="USD",
        payment_status="paid",
        fulfillment_status="unfulfilled",
        lifecycle_status="paid",
        source="shopify",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    db.flush()
    item = OrderItem(
        order_id=order.id,
        organization_id=org.id,
        store_id=store.id,
        shopify_line_item_id="555",
        title="Tracked Product",
        quantity=1,
        unit_price=20,
        currency="USD",
    )
    db.add(item)
    db.flush()
    connection = CommerceConnection(
        organization_id=org.id,
        store_id=store.id,
        provider="shopify",
        external_store_url="tracked.myshopify.com",
        access_token_encrypted="encrypted",
        scopes=(
            "read_orders,write_orders,"
            "read_merchant_managed_fulfillment_orders,"
            "write_merchant_managed_fulfillment_orders"
        ),
        status="connected",
        connected_at=datetime.utcnow(),
    )
    db.add(connection)
    supplier_order = SupplierOrder(
        organization_id=org.id,
        store_id=store.id,
        order_id=order.id,
        provider="cj",
        provider_order_number="DG-1",
        external_order_id="CJ-1",
        creation_status="created",
        idempotency_key="auto-cj-1",
        currency="USD",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(supplier_order)
    db.flush()
    db.add(
        SupplierOrderItem(
            supplier_order_id=supplier_order.id,
            order_item_id=item.id,
            external_variant_id="CJ-V-1",
            quantity=1,
            created_at=datetime.utcnow(),
        )
    )
    shipment = Shipment(
        organization_id=org.id,
        store_id=store.id,
        supplier_order_id=supplier_order.id,
        order_id=order.id,
        provider="cj",
        tracking_number="TRACK-123",
        logistic_name="CJPacket",
        tracking_url="https://tracking.example/TRACK-123",
        normalized_status="IN_TRANSIT",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(shipment)
    db.commit()
    return supplier_order, shipment


def setup_function():
    Base.metadata.create_all(bind=engine)


def teardown_function():
    Base.metadata.drop_all(bind=engine)


def test_creates_shopify_fulfillment_for_matching_line_item(monkeypatch):
    db = TestingSessionLocal()
    try:
        supplier_order, shipment = seed(db)
        monkeypatch.setattr(
            service,
            "decrypt_shopify_secret",
            lambda _value: "token",
        )
        calls = []

        def query(_self, graphql, variables=None):
            calls.append((graphql, variables))
            if len(calls) == 1:
                return {
                    "order": {
                        "id": "gid://shopify/Order/9001",
                        "fulfillments": [],
                        "fulfillmentOrders": {
                            "nodes": [
                                {
                                    "id": "gid://shopify/FulfillmentOrder/77",
                                    "status": "OPEN",
                                    "lineItems": {
                                        "nodes": [
                                            {
                                                "id": "gid://shopify/FulfillmentOrderLineItem/88",
                                                "remainingQuantity": 1,
                                                "lineItem": {
                                                    "id": "gid://shopify/LineItem/555"
                                                },
                                            }
                                        ]
                                    },
                                }
                            ]
                        },
                    }
                }
            return {
                "fulfillmentCreate": {
                    "fulfillment": {
                        "id": "gid://shopify/Fulfillment/99",
                        "status": "SUCCESS",
                        "trackingInfo": [
                            {
                                "number": "TRACK-123",
                                "company": "CJPacket",
                                "url": "https://tracking.example/TRACK-123",
                            }
                        ],
                    },
                    "userErrors": [],
                }
            }

        monkeypatch.setattr(service.ShopifyGraphQLClient, "query", query)

        result = service.create_shopify_fulfillment_from_shipment(
            db,
            supplier_order=supplier_order,
            shipment=shipment,
            notify_customer=True,
        )

        assert result["fulfillment_id"] == "gid://shopify/Fulfillment/99"
        assert result["idempotent"] is False
        mutation_variables = calls[1][1]
        fulfillment = mutation_variables["fulfillment"]
        assert fulfillment["notifyCustomer"] is True
        assert fulfillment["trackingInfo"]["number"] == "TRACK-123"
        assert fulfillment["lineItemsByFulfillmentOrder"] == [
            {
                "fulfillmentOrderId": "gid://shopify/FulfillmentOrder/77",
                "fulfillmentOrderLineItems": [
                    {
                        "id": "gid://shopify/FulfillmentOrderLineItem/88",
                        "quantity": 1,
                    }
                ],
            }
        ]
    finally:
        db.close()


def test_existing_tracking_is_idempotent(monkeypatch):
    db = TestingSessionLocal()
    try:
        supplier_order, shipment = seed(db)
        monkeypatch.setattr(
            service,
            "decrypt_shopify_secret",
            lambda _value: "token",
        )

        def query(_self, _graphql, variables=None):
            return {
                "order": {
                    "id": "gid://shopify/Order/9001",
                    "fulfillments": [
                        {
                            "id": "gid://shopify/Fulfillment/99",
                            "status": "SUCCESS",
                            "trackingInfo": [
                                {
                                    "number": "TRACK-123",
                                    "company": "CJPacket",
                                    "url": None,
                                }
                            ],
                        }
                    ],
                    "fulfillmentOrders": {"nodes": []},
                }
            }

        monkeypatch.setattr(service.ShopifyGraphQLClient, "query", query)

        result = service.create_shopify_fulfillment_from_shipment(
            db,
            supplier_order=supplier_order,
            shipment=shipment,
            notify_customer=True,
        )

        assert result["idempotent"] is True
        assert result["fulfillment_id"] == "gid://shopify/Fulfillment/99"
    finally:
        db.close()
