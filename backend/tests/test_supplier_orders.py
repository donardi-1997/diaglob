"""CJ supplier-order lifecycle tests."""

from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.integrations.cj.client import CJTemporaryError
from app.model_domains.supplier_integrations import SupplierConnection
from app.model_domains.supplier_orders import SupplierOrder
from app.models import Order, OrderItem, Organization, Store
from app.services import supplier_orders as service
from app.supplier_security import encrypt_supplier_secret


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def schema(monkeypatch):
    monkeypatch.setenv(
        "SUPPLIER_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode("utf-8"),
    )
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
        name="Supplier Orders Org",
        slug="supplier-orders-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="US Store",
        slug="supplier-us-store",
        country_code="US",
        currency="USD",
        timezone="America/New_York",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.flush()
    commerce_order = Order(
        organization_id=org.id,
        store_id=store.id,
        order_number="#1001",
        total_amount=39.99,
        currency="USD",
        financial_status="paid",
        fulfillment_status="unfulfilled",
        source="shopify",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(commerce_order)
    db.flush()
    item = OrderItem(
        order_id=commerce_order.id,
        organization_id=org.id,
        store_id=store.id,
        title="Test Product",
        sku="STORE-SKU-1",
        quantity=2,
        unit_price=19.995,
        currency="USD",
    )
    db.add(item)
    db.flush()
    connection = SupplierConnection(
        organization_id=org.id,
        store_id=store.id,
        provider="cj",
        external_account_id="77",
        api_key_encrypted=encrypt_supplier_secret("api-key"),
        access_token_encrypted=encrypt_supplier_secret("access"),
        refresh_token_encrypted=encrypt_supplier_secret("refresh"),
        access_token_expires_at=datetime.utcnow() + timedelta(days=30),
        refresh_token_expires_at=datetime.utcnow() + timedelta(days=60),
        status="connected",
        connected_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(connection)
    db.commit()
    return org, store, commerce_order, item, connection


def payload(item):
    return {
        "order_id": item.order_id,
        "idempotency_key": "fulfill-1001",
        "items": [
            {
                "order_item_id": item.id,
                "external_variant_id": "CJ-VID-1",
                "quantity": 2,
            }
        ],
        "shipping": {
            "customer_name": "Jane Doe",
            "country_code": "US",
            "country": "United States",
            "province": "New York",
            "city": "New York",
            "address1": "123 Main St",
            "zip": "10001",
            "email": "jane@example.com",
        },
        "from_country_code": "CN",
        "logistic_name": "USPS+",
        "remark": "Diaglob test",
        "is_sandbox": True,
    }


def test_create_order_persists_intent_and_is_idempotent(db, data, monkeypatch):
    org, store, _order, item, _connection = data
    monkeypatch.setattr(
        service,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "access",
    )
    calls = []

    def create(_token, body):
        calls.append(body)
        return {
            "orderId": "CJ-ORDER-1",
            "shipmentOrderId": "SHIP-1",
            "orderStatus": "CREATED",
            "productAmount": "10.00",
            "postageAmount": "5.00",
            "orderAmount": "15.00",
            "actualPayment": "0",
            "productInfoList": [
                {
                    "storeLineItemId": str(item.id),
                    "lineItemId": "CJ-LINE-1",
                    "variantId": "CJ-VID-1",
                    "quantity": 2,
                }
            ],
        }

    monkeypatch.setattr(service.cj_client, "create_order_v3", create)

    first = service.create_cj_supplier_order(
        db,
        org.id,
        store.id,
        **payload(item),
    )
    second = service.create_cj_supplier_order(
        db,
        org.id,
        store.id,
        **payload(item),
    )

    assert first["creation_status"] == "created"
    assert first["external_order_id"] == "CJ-ORDER-1"
    assert first["shipment_order_id"] == "SHIP-1"
    assert first["order_amount"] == 15.0
    assert first["items"][0]["provider_line_item_id"] == "CJ-LINE-1"
    assert second["idempotent"] is True
    assert len(calls) == 1
    assert calls[0]["payType"] == 3
    assert calls[0]["isSandbox"] == 1


def test_ambiguous_failure_reconciles_before_retry(db, data, monkeypatch):
    org, store, _order, item, _connection = data
    monkeypatch.setattr(
        service,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "access",
    )
    create_calls = []

    def temporary(_token, _body):
        create_calls.append(1)
        raise CJTemporaryError("timeout")

    monkeypatch.setattr(service.cj_client, "create_order_v3", temporary)

    with pytest.raises(CJTemporaryError):
        service.create_cj_supplier_order(
            db,
            org.id,
            store.id,
            **payload(item),
        )

    row = db.query(SupplierOrder).one()
    assert row.creation_status == "unknown"

    monkeypatch.setattr(
        service.cj_client,
        "get_order",
        lambda *_args, **_kwargs: {
            "orderId": "CJ-RECOVERED",
            "orderStatus": "CREATED",
            "orderAmount": "15.00",
        },
    )

    recovered = service.create_cj_supplier_order(
        db,
        org.id,
        store.id,
        **payload(item),
    )

    assert recovered["external_order_id"] == "CJ-RECOVERED"
    assert recovered["idempotent"] is True
    assert len(create_calls) == 1


def test_cancel_refuses_shipped_order(db, data, monkeypatch):
    org, store, commerce_order, item, connection = data
    supplier_order = SupplierOrder(
        organization_id=org.id,
        store_id=store.id,
        order_id=commerce_order.id,
        supplier_connection_id=connection.id,
        provider="cj",
        provider_order_number="DG-X",
        external_order_id="CJ-X",
        supplier_status="CREATED",
        creation_status="created",
        idempotency_key="cancel-x",
        currency="USD",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(supplier_order)
    db.commit()

    monkeypatch.setattr(
        service,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "access",
    )
    monkeypatch.setattr(
        service.cj_client,
        "get_order",
        lambda *_args, **_kwargs: {
            "orderId": "CJ-X",
            "orderStatus": "SHIPPED",
        },
    )
    delete_calls = []
    monkeypatch.setattr(
        service.cj_client,
        "delete_order",
        lambda *_args, **_kwargs: delete_calls.append(1) or True,
    )

    with pytest.raises(service.SupplierOrderError, match="CJ_ORDER_NOT_CANCELLABLE"):
        service.cancel_cj_supplier_order(
            db,
            org.id,
            store.id,
            supplier_order.id,
        )

    assert delete_calls == []


def test_cross_tenant_order_is_not_visible(db, data):
    _org, store, commerce_order, item, _connection = data
    other = Organization(
        name="Other",
        slug="other-supplier-orders",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(other)
    db.commit()

    with pytest.raises(service.SupplierOrderNotFound, match="STORE_NOT_FOUND"):
        service.create_cj_supplier_order(
            db,
            other.id,
            store.id,
            order_id=commerce_order.id,
            idempotency_key="cross",
            items=[
                {
                    "order_item_id": item.id,
                    "external_variant_id": "CJ-VID",
                    "quantity": 1,
                }
            ],
            shipping={
                "customer_name": "X",
                "country_code": "US",
                "country": "United States",
                "province": "NY",
                "city": "NY",
                "address1": "Street",
            },
            from_country_code="CN",
            logistic_name="USPS+",
        )


def test_idempotency_key_cannot_be_reused_with_different_items(
    db, data, monkeypatch
):
    org, store, _order, item, _connection = data
    monkeypatch.setattr(
        service,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "access",
    )
    monkeypatch.setattr(
        service.cj_client,
        "create_order_v3",
        lambda *_args, **_kwargs: {
            "orderId": "CJ-ORDER-1",
            "orderStatus": "CREATED",
        },
    )
    service.create_cj_supplier_order(
        db,
        org.id,
        store.id,
        **payload(item),
    )

    changed = payload(item)
    changed["items"][0]["external_variant_id"] = "DIFFERENT-VID"

    with pytest.raises(
        service.SupplierOrderError,
        match="IDEMPOTENCY_PAYLOAD_MISMATCH",
    ):
        service.create_cj_supplier_order(
            db,
            org.id,
            store.id,
            **changed,
        )


def test_sync_preserves_unshipped_substatus(db, data, monkeypatch):
    org, store, commerce_order, _item, connection = data
    supplier_order = SupplierOrder(
        organization_id=org.id,
        store_id=store.id,
        order_id=commerce_order.id,
        supplier_connection_id=connection.id,
        provider="cj",
        provider_order_number="DG-SUB",
        external_order_id="CJ-SUB",
        supplier_status="CREATED",
        creation_status="created",
        idempotency_key="substatus",
        currency="USD",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(supplier_order)
    db.commit()

    monkeypatch.setattr(
        service,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "access",
    )
    monkeypatch.setattr(
        service.cj_client,
        "get_order",
        lambda *_args, **_kwargs: {
            "orderId": "CJ-SUB",
            "orderStatus": "UNSHIPPED",
            "subStatus": "PROCESSING",
        },
    )

    result = service.sync_cj_supplier_order(
        db,
        org.id,
        store.id,
        supplier_order.id,
    )

    assert result["supplier_status"] == "UNSHIPPED"
    assert result["supplier_substatus"] == "PROCESSING"
