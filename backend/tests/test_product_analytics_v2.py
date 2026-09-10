"""Regression coverage for Product Analytics V2."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    Order,
    OrderItem,
    Organization,
    Product,
    ProductVariant,
    Store,
)
from app.services.dropshipping_analytics import (
    get_product_detail,
    get_product_profitability,
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_product_analytics_v2.db"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


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


@pytest.fixture()
def org_store(db):
    org = Organization(
        name="Product Analytics Org",
        slug="product-analytics-v2-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Product Analytics Store",
        slug="product-analytics-v2-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(store)
    db.flush()
    return org, store


def _product(db, org, store, title: str, cost: float = 20) -> Product:
    product = Product(
        organization_id=org.id,
        store_id=store.id,
        title=title,
        description="",
        cost=cost,
    )
    db.add(product)
    db.flush()
    return product


def _variant(
    db,
    product: Product,
    *,
    title: str,
    sku: str,
    stock: int,
) -> ProductVariant:
    variant = ProductVariant(
        product_id=product.id,
        title=title,
        sku=sku,
        price=100,
        currency="COP",
        inventory_quantity=stock,
        available=stock > 0,
    )
    db.add(variant)
    db.flush()
    return variant


def _order_item(
    db,
    org,
    store,
    product: Product,
    *,
    number: str,
    status: str,
    created_at: datetime,
    price: float,
    cost: float | None,
    quantity: int = 1,
    variant: ProductVariant | None = None,
):
    order = Order(
        organization_id=org.id,
        store_id=store.id,
        order_number=number,
        total_amount=price * quantity,
        currency=store.currency,
        source="shopify",
        lifecycle_status=status,
        created_at=created_at,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            organization_id=org.id,
            store_id=store.id,
            product_id=product.id,
            variant_id=variant.id if variant else None,
            title=product.title,
            sku=variant.sku if variant else f"SKU-{product.id}",
            quantity=quantity,
            unit_price=price,
            unit_cost=cost,
            currency=store.currency,
        )
    )
    db.flush()
    return order


def test_product_performance_exposes_lifecycle_profit_and_contribution(db, org_store):
    org, store = org_store
    winner = _product(db, org, store, "Winner")
    other = _product(db, org, store, "Other")
    _variant(db, winner, title="Winner / M", sku="WIN-M", stock=7)

    _order_item(
        db, org, store, winner,
        number="W-DEL", status="delivered",
        created_at=datetime(2026, 9, 9, 9), price=100, cost=40,
    )
    _order_item(
        db, org, store, winner,
        number="W-SHIP", status="shipped",
        created_at=datetime(2026, 9, 9, 10), price=80, cost=30,
    )
    _order_item(
        db, org, store, winner,
        number="W-CAN", status="cancelled",
        created_at=datetime(2026, 9, 9, 11), price=60, cost=20,
    )
    _order_item(
        db, org, store, winner,
        number="W-RET", status="returned",
        created_at=datetime(2026, 9, 9, 12), price=50, cost=20,
    )
    _order_item(
        db, org, store, other,
        number="O-DEL", status="delivered",
        created_at=datetime(2026, 9, 9, 13), price=100, cost=50,
    )
    db.commit()

    result = get_product_profitability(
        db,
        org.id,
        store.id,
        datetime(2026, 9, 9),
        datetime(2026, 9, 10),
        200,
    )

    item = next(row for row in result if row["product_id"] == winner.id)
    assert item["total_orders"] == 4
    assert item["confirmed_orders"] == 2
    assert item["shipped_orders"] == 2
    assert item["delivered_orders"] == 1
    assert item["cancelled_orders"] == 1
    assert item["returned_orders"] == 1
    assert item["delivery_rate"] == 50.0
    assert item["cancellation_rate"] == 25.0
    assert item["return_rate"] == 50.0
    assert item["units_delivered"] == 1
    assert item["delivered_revenue"] == 100.0
    assert item["gross_profit"] == 60.0
    assert item["gross_margin"] == 60.0
    assert item["profit_per_unit"] == 60.0
    assert item["revenue_share_pct"] == 50.0
    assert item["profit_share_pct"] == 54.5
    assert item["inventory_quantity"] == 7


def test_product_detail_returns_comparison_timeseries_and_variants(db, org_store):
    org, store = org_store
    product = _product(db, org, store, "Detail Product")
    red = _variant(db, product, title="Red / M", sku="RED-M", stock=12)
    blue = _variant(db, product, title="Blue / L", sku="BLUE-L", stock=4)

    _order_item(
        db, org, store, product,
        number="PREVIOUS", status="delivered",
        created_at=datetime(2026, 9, 8, 10),
        price=50, cost=20, variant=red,
    )
    _order_item(
        db, org, store, product,
        number="CURRENT", status="delivered",
        created_at=datetime(2026, 9, 9, 10),
        price=100, cost=40, quantity=2, variant=red,
    )
    db.commit()

    detail = get_product_detail(
        db,
        org.id,
        store.id,
        product.id,
        datetime(2026, 9, 9),
        datetime(2026, 9, 10),
    )

    assert detail is not None
    assert detail["metrics"]["delivered_revenue"] == 200.0
    assert detail["metrics"]["gross_profit"] == 120.0
    assert detail["metrics"]["profit_per_unit"] == 60.0
    assert detail["comparison"]["delivered_revenue_pct"] == 300.0
    assert detail["comparison"]["gross_profit_pct"] == 300.0
    assert detail["timeseries"] == [
        {
            "date": "2026-09-09",
            "total_orders": 1,
            "delivered_orders": 1,
            "units_delivered": 2,
            "delivered_revenue": 200.0,
            "gross_profit": 120.0,
        }
    ]

    variants = {row["variant_id"]: row for row in detail["variants"]}
    assert variants[red.id]["title"] == "Red / M"
    assert variants[red.id]["inventory_quantity"] == 12
    assert variants[red.id]["units_delivered"] == 2
    assert variants[red.id]["gross_profit"] == 120.0
    assert variants[blue.id]["inventory_quantity"] == 4
    assert variants[blue.id]["total_orders"] == 0


def test_product_detail_is_strictly_scoped_to_store(db, org_store):
    org, store = org_store
    product = _product(db, org, store, "Store One Product")

    other_store = Store(
        organization_id=org.id,
        name="Other Store",
        slug="product-analytics-other-store",
        country_code="MX",
        currency="MXN",
        timezone="America/Mexico_City",
        default_language="es",
    )
    db.add(other_store)
    db.flush()
    other_product = _product(db, org, other_store, "Other Store Product")
    _order_item(
        db, org, other_store, other_product,
        number="OTHER-DEL", status="delivered",
        created_at=datetime(2026, 9, 9, 10), price=999, cost=1,
    )
    db.commit()

    own_detail = get_product_detail(
        db, org.id, store.id, product.id, None, None
    )
    foreign_detail = get_product_detail(
        db, org.id, store.id, other_product.id, None, None
    )

    assert own_detail is not None
    assert own_detail["metrics"]["total_orders"] == 0
    assert foreign_detail is None
