"""Automatic Shopify -> CJ fulfillment orchestration tests."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.fulfillment_automation import AutoFulfillmentJob
from app.model_domains.shipments import Shipment
from app.model_domains.supplier_integrations import SupplierConnection
from app.model_domains.supplier_orders import SupplierOrder  # noqa: F401
from app.model_domains.supplier_variant_mappings import SupplierVariantMapping
from app.models import (
    CommerceConnection,
    Order,
    OrderItem,
    Organization,
    Product,
    ProductVariant,
    Store,
)
from app.services import auto_fulfillment as service


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


def seed(db, *, mapped=True, fulfillment_scopes=True):
    org = Organization(
        name="Auto Fulfillment Org",
        slug="auto-fulfillment-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Auto Store",
        slug="auto-store",
        country_code="US",
        currency="USD",
        timezone="UTC",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.flush()
    product = Product(
        organization_id=org.id,
        store_id=store.id,
        shopify_product_id="100",
        title="Auto Product",
        description="",
        active=True,
    )
    db.add(product)
    db.flush()
    variant = ProductVariant(
        product_id=product.id,
        shopify_variant_id="101",
        title="Default",
        sku="SHOP-101",
        price=49.99,
        currency="USD",
        inventory_quantity=10,
        available=True,
    )
    db.add(variant)
    db.flush()
    order = Order(
        organization_id=org.id,
        store_id=store.id,
        shopify_order_id="9001",
        external_order_id="9001",
        order_number="1001",
        total_amount=49.99,
        currency="USD",
        financial_status="paid",
        payment_status="paid",
        fulfillment_status="unfulfilled",
        lifecycle_status="paid",
        source="shopify",
        shipping_address={
            "customer_name": "Jane Doe",
            "country_code": "US",
            "country": "United States",
            "province": "Florida",
            "city": "Miami",
            "address1": "123 Main St",
            "zip": "33101",
            "email": "jane@example.com",
        },
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    db.flush()
    item = OrderItem(
        order_id=order.id,
        organization_id=org.id,
        store_id=store.id,
        product_id=product.id,
        variant_id=variant.id,
        shopify_variant_id="101",
        shopify_line_item_id="555",
        title="Auto Product",
        sku="SHOP-101",
        quantity=2,
        unit_price=24.995,
        currency="USD",
    )
    db.add(item)
    scopes = "read_orders,write_orders"
    if fulfillment_scopes:
        scopes += (
            ",read_merchant_managed_fulfillment_orders"
            ",write_merchant_managed_fulfillment_orders"
        )
    db.add(
        CommerceConnection(
            organization_id=org.id,
            store_id=store.id,
            provider="shopify",
            external_store_url="auto-store.myshopify.com",
            access_token_encrypted="encrypted",
            scopes=scopes,
            status="connected",
            connected_at=datetime.utcnow(),
        )
    )
    db.add(
        SupplierConnection(
            organization_id=org.id,
            store_id=store.id,
            provider="cj",
            status="connected",
            connected_at=datetime.utcnow(),
            auto_fulfillment_enabled=True,
            auto_origin_country_code="CN",
            auto_notify_customer=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
    )
    if mapped:
        db.add(
            SupplierVariantMapping(
                organization_id=org.id,
                store_id=store.id,
                product_variant_id=variant.id,
                provider="cj",
                external_product_id="CJ-P-1",
                external_variant_id="CJ-V-1",
                external_sku="CJ-SKU-1",
                active=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
    db.commit()
    return org, store, order, item


def seed_supplier_shipment(db, org, store, order):
    supplier_order = SupplierOrder(
        organization_id=org.id,
        store_id=store.id,
        order_id=order.id,
        provider="cj",
        provider_order_number=f"CJ-{order.id}",
        external_order_id=f"CJ-EXT-{order.id}",
        creation_status="created",
        idempotency_key=f"auto-cj-{order.id}",
        currency="USD",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(supplier_order)
    db.flush()
    shipment = Shipment(
        organization_id=org.id,
        store_id=store.id,
        order_id=order.id,
        supplier_order_id=supplier_order.id,
        provider="cj",
        tracking_number=f"TRACK-{order.id}",
        normalized_status="IN_TRANSIT",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(shipment)
    job = AutoFulfillmentJob(
        organization_id=org.id,
        store_id=store.id,
        order_id=order.id,
        supplier_order_id=supplier_order.id,
        provider="cj",
        status="supplier_created",
        attempts=1,
        origin_country_code="CN",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    return supplier_order, shipment, job


def test_paid_mapped_order_creates_supplier_order_with_cheapest_logistics(
    db,
    monkeypatch,
):
    _org, _store, order, item = seed(db)
    job = service.enqueue_shopify_order(db, order.id)
    assert job is not None

    captured = {}

    def quote(*_args, **kwargs):
        captured["quote"] = kwargs
        return {
            "options": [
                {"logistics_name": "Fast", "price_usd": "12.00"},
                {"logistics_name": "Economy", "price_usd": "5.50"},
            ]
        }

    def create(*_args, **kwargs):
        captured["create"] = kwargs
        return {"id": 321, "creation_status": "created"}

    monkeypatch.setattr(service, "quote_cj_freight", quote)
    monkeypatch.setattr(service, "create_cj_supplier_order", create)

    result = service.process_auto_fulfillment_job(db, job.id)

    assert result["status"] == "supplier_created"
    assert result["supplier_order_id"] == 321
    assert result["logistic_name"] == "Economy"
    assert captured["quote"]["items"] == [
        {"variant_id": "CJ-V-1", "quantity": 2}
    ]
    assert captured["create"]["items"] == [
        {"order_item_id": item.id, "quantity": 2}
    ]
    assert captured["create"]["idempotency_key"] == f"auto-cj-{order.id}"
    assert captured["create"]["is_sandbox"] is False


def test_missing_mapping_waits_without_calling_cj(db, monkeypatch):
    _org, _store, order, _item = seed(db, mapped=False)
    job = service.enqueue_shopify_order(db, order.id)
    assert job is not None

    monkeypatch.setattr(
        service,
        "quote_cj_freight",
        lambda *_args, **_kwargs: pytest.fail("CJ freight should not be called"),
    )

    result = service.process_auto_fulfillment_job(db, job.id)

    assert result["status"] == "waiting_mapping"
    assert "CJ_VARIANT_MAPPING_REQUIRED" in result["last_error"]


def test_enable_requires_shopify_fulfillment_scopes(db):
    org, store, _order, _item = seed(db, fulfillment_scopes=False)
    connection = (
        db.query(SupplierConnection)
        .filter(SupplierConnection.store_id == store.id)
        .one()
    )
    connection.auto_fulfillment_enabled = False
    db.commit()

    with pytest.raises(
        service.AutoFulfillmentError,
        match="SHOPIFY_FULFILLMENT_SCOPES_REQUIRED",
    ):
        service.configure_cj_auto_fulfillment(
            db,
            org.id,
            store.id,
            enabled=True,
            origin_country_code="CN",
            notify_customer=True,
        )

    assert db.query(AutoFulfillmentJob).count() == 0


def test_shipment_sync_rechecks_payment_and_order_state_before_fulfillment(
    db, monkeypatch,
):
    org, store, order, _item = seed(db)
    _supplier_order, shipment, job = seed_supplier_shipment(
        db, org, store, order,
    )
    order.payment_status = "refunded"
    order.lifecycle_status = "refunded"
    db.commit()

    monkeypatch.setattr(
        service,
        "create_shopify_fulfillment_from_shipment",
        lambda *_args, **_kwargs: pytest.fail(
            "must not publish fulfillment for a refunded order"
        ),
    )

    result = service.sync_shopify_from_shipment(db, shipment.id)

    assert result["id"] == job.id
    assert result["status"] == "skipped"
    assert result["last_error"] == "ORDER_NOT_ELIGIBLE"
    assert order.fulfillment_status == "unfulfilled"
    assert order.lifecycle_status == "refunded"


def test_eligible_paid_supplier_shipment_still_syncs_fulfillment(db, monkeypatch):
    org, store, order, _item = seed(db)
    _supplier_order, shipment, job = seed_supplier_shipment(
        db, org, store, order,
    )
    calls = []

    def publish(_db, *, supplier_order, shipment, notify_customer):
        calls.append((supplier_order.id, shipment.id, notify_customer))
        return {
            "ok": True,
            "idempotent": False,
            "fulfillment_id": "gid://shopify/Fulfillment/99",
            "status": "SUCCESS",
        }

    monkeypatch.setattr(
        service, "create_shopify_fulfillment_from_shipment", publish,
    )

    result = service.sync_shopify_from_shipment(db, shipment.id)

    assert result["id"] == job.id
    assert result["status"] == "shopify_fulfilled"
    assert result["shopify_fulfillment_id"] == "gid://shopify/Fulfillment/99"
    assert calls == [(_supplier_order.id, shipment.id, True)]
    assert order.fulfillment_status == "fulfilled"
    assert order.lifecycle_status == "fulfilled"


def test_shipment_sync_rechecks_privacy_suppression_before_fulfillment(
    db, monkeypatch,
):
    org, store, order, _item = seed(db)
    _supplier_order, shipment, job = seed_supplier_shipment(
        db, org, store, order,
    )
    monkeypatch.setattr(
        service,
        "evaluate_shopify_local_privacy",
        lambda *_args, **_kwargs: "customer_suppressed",
    )
    monkeypatch.setattr(
        service,
        "create_shopify_fulfillment_from_shipment",
        lambda *_args, **_kwargs: pytest.fail(
            "must not publish fulfillment after a privacy suppression"
        ),
    )

    result = service.sync_shopify_from_shipment(db, shipment.id)

    assert result["id"] == job.id
    assert result["status"] == "skipped"
    assert result["last_error"] == "PRIVACY_SUPPRESSED"
    assert order.fulfillment_status == "unfulfilled"
    assert order.lifecycle_status == "paid"


def test_shipment_sync_rejects_cross_store_supplier_order(db, monkeypatch):
    org, store, order, _item = seed(db)
    foreign_store = Store(
        organization_id=org.id,
        name="Other Store",
        slug="other-auto-store",
        country_code="US",
        currency="USD",
        timezone="UTC",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add(foreign_store)
    db.flush()
    foreign_supplier_order = SupplierOrder(
        organization_id=org.id,
        store_id=foreign_store.id,
        order_id=order.id,
        provider="cj",
        provider_order_number="CJ-FOREIGN",
        external_order_id="CJ-EXT-FOREIGN",
        creation_status="created",
        idempotency_key="auto-cj-foreign",
        currency="USD",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(foreign_supplier_order)
    db.flush()
    shipment = Shipment(
        organization_id=org.id,
        store_id=store.id,
        order_id=order.id,
        supplier_order_id=foreign_supplier_order.id,
        provider="cj",
        tracking_number="TRACK-CROSS-STORE",
        normalized_status="IN_TRANSIT",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(shipment)
    db.commit()

    monkeypatch.setattr(
        service,
        "create_shopify_fulfillment_from_shipment",
        lambda *_args, **_kwargs: pytest.fail(
            "cross-store supplier order must not reach Shopify"
        ),
    )

    assert service.sync_shopify_from_shipment(db, shipment.id) is None
    assert order.fulfillment_status == "unfulfilled"


def test_shipment_sync_rejects_cross_organization_supplier_order(db, monkeypatch):
    org, store, order, _item = seed(db)
    foreign_org = Organization(
        name="Foreign Auto Fulfillment Org",
        slug="foreign-auto-fulfillment-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(foreign_org)
    db.flush()
    foreign_store = Store(
        organization_id=foreign_org.id,
        name="Foreign Auto Store",
        slug="foreign-auto-store",
        country_code="US",
        currency="USD",
        timezone="UTC",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add(foreign_store)
    db.flush()
    foreign_supplier_order = SupplierOrder(
        organization_id=foreign_org.id,
        store_id=foreign_store.id,
        # Deliberately mismatched row lineage to characterize fail-closed joins.
        order_id=order.id,
        provider="cj",
        provider_order_number="CJ-FOREIGN-ORG",
        external_order_id="CJ-EXT-FOREIGN-ORG",
        creation_status="created",
        idempotency_key="auto-cj-foreign-org",
        currency="USD",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(foreign_supplier_order)
    db.flush()
    shipment = Shipment(
        organization_id=org.id,
        store_id=store.id,
        order_id=order.id,
        supplier_order_id=foreign_supplier_order.id,
        provider="cj",
        tracking_number="TRACK-CROSS-ORG",
        normalized_status="IN_TRANSIT",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(shipment)
    db.commit()

    monkeypatch.setattr(
        service,
        "create_shopify_fulfillment_from_shipment",
        lambda *_args, **_kwargs: pytest.fail(
            "cross-organization supplier order must not reach Shopify"
        ),
    )

    assert service.sync_shopify_from_shipment(db, shipment.id) is None
    assert order.fulfillment_status == "unfulfilled"
