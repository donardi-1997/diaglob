"""Regression tests for dropshipping profitability analytics."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dropshipping_analytics import _parse_date
from app.db import Base
from app.models import Order, OrderItem, Organization, Store
from app.services.dropshipping_analytics import (
    _safe_percentage,
    get_profitability,
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_dropshipping_analytics.db"

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
                title=f"Item {number}-{index}",
                quantity=1,
                unit_price=total / max(len(costs), 1),
                unit_cost=cost,
                currency=store.currency,
            )
        )

    db.flush()
    return order


def test_date_only_end_boundary_includes_entire_day():
    assert _parse_date(
        "2026-09-09",
        inclusive_end=True,
    ) == datetime(2026, 9, 10)


def test_percentage_returns_percentage_not_fraction():
    assert _safe_percentage(1, 2) == 50.0
    assert _safe_percentage(3, 4) == 75.0


def test_profitability_uses_only_delivered_orders_in_range(db, org_store):
    org, store = org_store

    _add_order(
        db,
        org,
        store,
        number="DELIVERED-IN-RANGE",
        status="delivered",
        total=100,
        created_at=datetime(2026, 9, 9, 15, 30),
        costs=[20, 10],
    )
    _add_order(
        db,
        org,
        store,
        number="CANCELLED-IN-RANGE",
        status="cancelled",
        total=500,
        created_at=datetime(2026, 9, 9, 16, 0),
        costs=[300],
    )
    _add_order(
        db,
        org,
        store,
        number="DELIVERED-OUTSIDE-RANGE",
        status="delivered",
        total=250,
        created_at=datetime(2026, 9, 8, 23, 59),
        costs=[100],
    )
    db.commit()

    result = get_profitability(
        db,
        org.id,
        store.id,
        datetime(2026, 9, 9),
        datetime(2026, 9, 10),
    )

    assert result["delivered_orders_count"] == 1
    assert result["delivered_revenue"] == 100.0
    assert result["total_cogs"] == 30.0
    assert result["gross_profit"] == 70.0
    assert result["gross_margin"] == 70.0
    assert result["profit_per_delivered_order"] == 70.0
    assert result["cost_completeness_pct"] == 100.0


def test_cost_completeness_uses_same_delivered_cohort(db, org_store):
    org, store = org_store

    _add_order(
        db,
        org,
        store,
        number="DELIVERED-PARTIAL-COST",
        status="delivered",
        total=100,
        created_at=datetime(2026, 9, 9, 10, 0),
        costs=[25, None],
    )
    _add_order(
        db,
        org,
        store,
        number="CANCELLED-WITH-COST",
        status="cancelled",
        total=100,
        created_at=datetime(2026, 9, 9, 11, 0),
        costs=[50],
    )
    db.commit()

    result = get_profitability(
        db,
        org.id,
        store.id,
        datetime(2026, 9, 9),
        datetime(2026, 9, 10),
    )

    assert result["total_cogs"] == 25.0
    assert result["cost_completeness_pct"] == 50.0
