"""Regression tests for dropshipping profitability analytics."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dropshipping_analytics import _parse_date
from app.db import Base
from app.models import Order, OrderItem, Organization, Product, Store
from app.services.dropshipping_analytics import (
    _percentage_change,
    _safe_percentage,
    get_dropshipping_overview,
    get_product_profitability,
    get_profitability,
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_dropshipping_analytics.db"

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


@pytest.fixture()
def org_store(db):
    org = Organization(
        name="Dropshipping Analytics Org",
        slug="dropshipping-analytics-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Analytics Store",
        slug="analytics-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(store)
    db.flush()
    return org, store


def _add_order(
    db,
    org,
    store,
    *,
    number: str,
    status: str,
    total: float,
    created_at: datetime,
    costs: list[float | None],
    product_id: int | None = None,
    sku: str | None = None,
):
    order = Order(
        organization_id=org.id,
        store_id=store.id,
        order_number=number,
        total_amount=total,
        currency=store.currency,
        source="shopify",
        lifecycle_status=status,
        created_at=created_at,
    )
    db.add(order)
    db.flush()
    for index, cost in enumerate(costs, start=1):
        db.add(
            OrderItem(
                order_id=order.id,
                organization_id=org.id,
                store_id=store.id,
                product_id=product_id,
                title=f"Item {number}-{index}",
                sku=sku,
                quantity=1,
                unit_price=total / max(len(costs), 1),
                unit_cost=cost,
                currency=store.currency,
            )
        )
    db.flush()
    return order


def test_date_only_end_boundary_includes_entire_day():
    assert _parse_date("2026-09-09", inclusive_end=True) == datetime(2026, 9, 10)


def test_percentage_returns_percentage_not_fraction():
    assert _safe_percentage(1, 2) == 50.0
    assert _safe_percentage(3, 4) == 75.0


def test_percentage_change_is_undefined_when_previous_is_zero():
    assert _percentage_change(100, 0) is None
    assert _percentage_change(0, 0) is None


def test_overview_returns_revenue_and_delivered_aov(db, org_store):
    org, store = org_store
    _add_order(db, org, store, number="DELIVERED-1", status="delivered", total=120, created_at=datetime(2026, 9, 9, 9), costs=[30])
    _add_order(db, org, store, number="DELIVERED-2", status="delivered", total=80, created_at=datetime(2026, 9, 9, 10), costs=[20])
    _add_order(db, org, store, number="CANCELLED", status="cancelled", total=300, created_at=datetime(2026, 9, 9, 11), costs=[100])
    db.commit()
    result = get_dropshipping_overview(db, org.id, store.id, datetime(2026, 9, 9), datetime(2026, 9, 10))
    assert result["total_orders"] == 3
    assert result["delivered_orders"] == 2
    assert result["gross_order_value"] == 500.0
    assert result["delivered_revenue"] == 200.0
    assert result["delivered_aov"] == 100.0


def test_overview_compares_with_immediately_previous_equal_period(db, org_store):
    org, store = org_store
    _add_order(db, org, store, number="PREV-DELIVERED", status="delivered", total=100, created_at=datetime(2026, 9, 8, 10), costs=[40])
    _add_order(db, org, store, number="PREV-CANCELLED", status="cancelled", total=50, created_at=datetime(2026, 9, 8, 11), costs=[10])
    _add_order(db, org, store, number="CURR-DELIVERED-1", status="delivered", total=120, created_at=datetime(2026, 9, 9, 10), costs=[30])
    _add_order(db, org, store, number="CURR-DELIVERED-2", status="delivered", total=80, created_at=datetime(2026, 9, 9, 11), costs=[20])
    db.commit()
    result = get_dropshipping_overview(db, org.id, store.id, datetime(2026, 9, 9), datetime(2026, 9, 10))
    comparison = result["comparison"]
    assert comparison is not None
    assert comparison["previous_date_from"] == "2026-09-08T00:00:00"
    assert comparison["previous_date_to"] == "2026-09-09T00:00:00"
    assert comparison["total_orders_pct"] == 0.0
    assert comparison["delivered_orders_pct"] == 100.0
    assert comparison["delivered_revenue_pct"] == 100.0
    assert comparison["delivered_aov_pct"] == 0.0
    assert comparison["delivery_rate_pp"] == 0.0
    assert comparison["cancellation_rate_pp"] == -50.0
    assert comparison["gross_profit_pct"] == 150.0
    assert comparison["gross_margin_pp"] == 15.0


def test_overview_without_complete_range_has_no_comparison(db, org_store):
    org, store = org_store
    assert get_dropshipping_overview(db, org.id, store.id, None, None)["comparison"] is None


def test_profitability_uses_only_delivered_orders_in_range(db, org_store):
    org, store = org_store
    _add_order(db, org, store, number="DELIVERED-IN-RANGE", status="delivered", total=100, created_at=datetime(2026, 9, 9, 15, 30), costs=[20, 10])
    _add_order(db, org, store, number="CANCELLED-IN-RANGE", status="cancelled", total=500, created_at=datetime(2026, 9, 9, 16), costs=[300])
    _add_order(db, org, store, number="DELIVERED-OUTSIDE-RANGE", status="delivered", total=250, created_at=datetime(2026, 9, 8, 23, 59), costs=[100])
    db.commit()
    result = get_profitability(db, org.id, store.id, datetime(2026, 9, 9), datetime(2026, 9, 10))
    assert result["delivered_orders_count"] == 1
    assert result["delivered_revenue"] == 100.0
    assert result["total_cogs"] == 30.0
    assert result["gross_profit"] == 70.0
    assert result["gross_margin"] == 70.0
    assert result["profit_per_delivered_order"] == 70.0
    assert result["cost_completeness_pct"] == 100.0
    assert result["profitability_complete"] is True


def test_cost_completeness_uses_same_delivered_cohort(db, org_store):
    org, store = org_store
    _add_order(db, org, store, number="DELIVERED-PARTIAL-COST", status="delivered", total=100, created_at=datetime(2026, 9, 9, 10), costs=[25, None])
    _add_order(db, org, store, number="CANCELLED-WITH-COST", status="cancelled", total=100, created_at=datetime(2026, 9, 9, 11), costs=[50])
    db.commit()
    result = get_profitability(db, org.id, store.id, datetime(2026, 9, 9), datetime(2026, 9, 10))
    assert result["total_cogs"] == 25.0
    assert result["cost_completeness_pct"] == 50.0
    assert result["profitability_complete"] is False


def test_product_profitability_uses_only_delivered_orders(db, org_store):
    org, store = org_store
    product = Product(organization_id=org.id, store_id=store.id, title="Winning Product", description="", cost=20)
    db.add(product)
    db.flush()
    _add_order(db, org, store, number="PRODUCT-DELIVERED", status="delivered", total=100, created_at=datetime(2026, 9, 9, 12), costs=[20], product_id=product.id, sku="WIN-001")
    _add_order(db, org, store, number="PRODUCT-CANCELLED", status="cancelled", total=500, created_at=datetime(2026, 9, 9, 13), costs=[300], product_id=product.id, sku="WIN-001")
    db.commit()
    result = get_product_profitability(db, org.id, store.id, datetime(2026, 9, 9), datetime(2026, 9, 10))
    assert len(result) == 1
    item = result[0]
    assert item["sku"] == "WIN-001"
    assert item["units_delivered"] == 1
    assert item["delivered_revenue"] == 100.0
    assert item["total_cogs"] == 20.0
    assert item["gross_profit"] == 80.0
    assert item["gross_margin"] == 80.0
    assert item["cost_completeness_pct"] == 100.0
    assert item["profitability_complete"] is True
