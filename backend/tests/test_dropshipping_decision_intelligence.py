"""Regression coverage for Dropshipping Analytics V2.1 decision intelligence."""
from datetime import datetime
import math

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
from app.services.dropshipping_decision_intelligence import (
    get_dropshipping_decision_insights,
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_dropshipping_decision_intelligence.db"

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
        name="Decision Intelligence Org",
        slug="decision-intelligence-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Decision Intelligence Store",
        slug="decision-intelligence-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(store)
    db.flush()
    return org, store


def add_product(db, org, store, title: str, *, stock: int = 100) -> Product:
    product = Product(
        organization_id=org.id,
        store_id=store.id,
        title=title,
        description="",
        cost=20,
    )
    db.add(product)
    db.flush()
    db.add(
        ProductVariant(
            product_id=product.id,
            title=f"{title} / Default",
            sku=f"SKU-{product.id}",
            price=100,
            currency=store.currency,
            inventory_quantity=stock,
            available=stock > 0,
        )
    )
    db.flush()
    return product


def add_order_item(
    db,
    org,
    store,
    product: Product,
    *,
    number: str,
    status: str,
    created_at: datetime,
    price: float = 100,
    cost: float | None = 40,
    quantity: int = 1,
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
    variant = (
        db.query(ProductVariant)
        .filter(ProductVariant.product_id == product.id)
        .first()
    )
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


def insight_types(result, product_id: int | None = None) -> set[str]:
    return {
        item["type"]
        for item in result["insights"]
        if product_id is None or item["product_id"] == product_id
    }


def service_result(db, org, store, *, date_from=None, date_to=None, limit=20):
    return get_dropshipping_decision_insights(
        db,
        org.id,
        store.id,
        store.currency,
        date_from,
        date_to,
        limit,
    )


def test_empty_store_returns_no_insights(db, org_store):
    org, store = org_store
    result = service_result(db, org, store)
    assert result["summary"] == {
        "critical": 0,
        "warning": 0,
        "opportunity": 0,
        "positive": 0,
        "products_evaluated": 0,
    }
    assert result["insights"] == []
    assert result["currency"] == "COP"


def test_incomplete_cost_suppresses_margin_dependent_insights(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Partial costs")
    add_order_item(
        db, org, store, product,
        number="PARTIAL-1", status="delivered",
        created_at=datetime(2026, 9, 1, 10), price=100, cost=40,
    )
    add_order_item(
        db, org, store, product,
        number="PARTIAL-2", status="delivered",
        created_at=datetime(2026, 9, 2, 10), price=100, cost=None,
    )
    db.commit()

    result = service_result(db, org, store)
    types = insight_types(result, product.id)
    assert "cost_incomplete" in types
    assert "negative_margin" not in types
    assert "low_margin" not in types
    assert "winner" not in types
    assert "opportunity" not in types


def test_negative_margin_is_critical(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Loss maker")
    add_order_item(
        db, org, store, product,
        number="LOSS-1", status="delivered",
        created_at=datetime(2026, 9, 1, 10), price=100, cost=150,
    )
    db.commit()

    result = service_result(db, org, store)
    insight = next(
        item for item in result["insights"]
        if item["type"] == "negative_margin"
    )
    assert insight["severity"] == "critical"
    assert insight["id"] == f"negative_margin:{product.id}"
    assert insight["action_key"] == "review_price_and_cost"
    assert insight["evidence"]["gross_profit"] == -50.0


def test_low_margin_requires_three_delivered_orders(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Thin margin")
    for index in range(3):
        add_order_item(
            db, org, store, product,
            number=f"THIN-{index}", status="delivered",
            created_at=datetime(2026, 9, 1 + index, 10),
            price=100, cost=90,
        )
    db.commit()

    result = service_result(db, org, store)
    assert "low_margin" in insight_types(result, product.id)
    low_margin = next(
        item for item in result["insights"] if item["type"] == "low_margin"
    )
    assert low_margin["severity"] == "warning"
    assert low_margin["evidence"]["gross_margin"] == 10.0


def test_delivery_risk_is_sample_guarded_at_five_shipped_orders(db, org_store):
    org, store = org_store
    guarded = add_product(db, org, store, "Guarded delivery")
    for index, status in enumerate(["delivered", "shipped", "shipped", "shipped"]):
        add_order_item(
            db, org, store, guarded,
            number=f"GUARD-{index}", status=status,
            created_at=datetime(2026, 9, 1, 9 + index),
        )

    risky = add_product(db, org, store, "Risky delivery")
    for index, status in enumerate(
        ["delivered", "delivered", "shipped", "shipped", "shipped"]
    ):
        add_order_item(
            db, org, store, risky,
            number=f"RISK-{index}", status=status,
            created_at=datetime(2026, 9, 2, 9 + index),
        )
    db.commit()

    result = service_result(db, org, store)
    assert "delivery_risk" not in insight_types(result, guarded.id)
    assert "delivery_risk" in insight_types(result, risky.id)


def test_cancellation_risk_requires_more_than_twenty_five_percent(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Cancellation risk")
    statuses = ["cancelled", "cancelled", "confirmed", "confirmed", "confirmed"]
    for index, status in enumerate(statuses):
        add_order_item(
            db, org, store, product,
            number=f"CAN-{index}", status=status,
            created_at=datetime(2026, 9, 1, 9 + index),
        )
    db.commit()

    result = service_result(db, org, store)
    insight = next(
        item for item in result["insights"]
        if item["type"] == "cancellation_risk"
    )
    assert insight["evidence"]["cancellation_rate"] == 40.0


def test_return_risk_requires_more_than_fifteen_percent(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Return risk")
    statuses = ["returned", "shipped", "shipped", "shipped", "shipped", "shipped"]
    for index, status in enumerate(statuses):
        add_order_item(
            db, org, store, product,
            number=f"RET-{index}", status=status,
            created_at=datetime(2026, 9, 1, 9 + index),
        )
    db.commit()

    result = service_result(db, org, store)
    insight = next(
        item for item in result["insights"] if item["type"] == "return_risk"
    )
    assert insight["evidence"]["return_rate"] == 20.0


def test_stockout_suppresses_stock_runway(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Sold out", stock=0)
    add_order_item(
        db, org, store, product,
        number="SOLD-OUT", status="delivered",
        created_at=datetime(2026, 9, 2, 10), quantity=5,
    )
    db.commit()

    result = service_result(
        db, org, store,
        date_from=datetime(2026, 9, 1),
        date_to=datetime(2026, 9, 11),
    )
    types = insight_types(result, product.id)
    assert "stockout" in types
    assert "stock_runway" not in types


@pytest.mark.parametrize(
    ("stock", "expected_severity"),
    [(2, "critical"), (5, "warning"), (7, None)],
)
def test_stock_runway_boundaries(db, org_store, stock, expected_severity):
    org, store = org_store
    product = add_product(db, org, store, f"Runway {stock}", stock=stock)
    add_order_item(
        db, org, store, product,
        number=f"RUNWAY-{stock}", status="delivered",
        created_at=datetime(2026, 9, 2, 10), quantity=10,
    )
    db.commit()

    result = service_result(
        db, org, store,
        date_from=datetime(2026, 9, 1),
        date_to=datetime(2026, 9, 11),
    )
    runway = [
        item for item in result["insights"]
        if item["type"] == "stock_runway" and item["product_id"] == product.id
    ]
    if expected_severity is None:
        assert runway == []
    else:
        assert runway[0]["severity"] == expected_severity
        assert runway[0]["evidence"]["units_per_day"] == 1.0
        assert runway[0]["evidence"]["stock_runway_days"] == float(stock)


def test_stock_runway_requires_three_delivered_units(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Low sample", stock=1)
    add_order_item(
        db, org, store, product,
        number="LOW-SAMPLE", status="delivered",
        created_at=datetime(2026, 9, 2, 10), quantity=2,
    )
    db.commit()

    result = service_result(
        db, org, store,
        date_from=datetime(2026, 9, 1),
        date_to=datetime(2026, 9, 11),
    )
    assert "stock_runway" not in insight_types(result, product.id)


def test_unbounded_range_omits_runway_but_keeps_other_rules(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Unbounded loss", stock=1)
    add_order_item(
        db, org, store, product,
        number="UNBOUNDED", status="delivered",
        created_at=datetime(2026, 9, 2, 10), price=100, cost=150, quantity=10,
    )
    db.commit()

    result = service_result(db, org, store)
    types = insight_types(result, product.id)
    assert "negative_margin" in types
    assert "stock_runway" not in types


def test_revenue_and_profit_concentration_require_multiple_contributors(db, org_store):
    org, store = org_store
    dominant = add_product(db, org, store, "Dominant")
    secondary = add_product(db, org, store, "Secondary")
    add_order_item(
        db, org, store, dominant,
        number="DOM", status="delivered",
        created_at=datetime(2026, 9, 1, 10), price=900, cost=300,
    )
    add_order_item(
        db, org, store, secondary,
        number="SEC", status="delivered",
        created_at=datetime(2026, 9, 1, 11), price=100, cost=50,
    )
    db.commit()

    result = service_result(db, org, store)
    types = insight_types(result, dominant.id)
    assert "revenue_concentration" in types
    assert "profit_concentration" in types


def test_single_product_store_does_not_trigger_concentration(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Only product")
    add_order_item(
        db, org, store, product,
        number="ONLY", status="delivered",
        created_at=datetime(2026, 9, 1, 10), price=1000, cost=100,
    )
    db.commit()

    result = service_result(db, org, store)
    types = insight_types(result, product.id)
    assert "revenue_concentration" not in types
    assert "profit_concentration" not in types


def test_winner_suppresses_opportunity(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Winner")
    for index in range(5):
        add_order_item(
            db, org, store, product,
            number=f"WIN-{index}", status="delivered",
            created_at=datetime(2026, 9, 1, 9 + index), price=100, cost=40,
        )
    db.commit()

    result = service_result(db, org, store)
    types = insight_types(result, product.id)
    assert "winner" in types
    assert "opportunity" not in types
    winner = next(item for item in result["insights"] if item["type"] == "winner")
    assert winner["severity"] == "positive"
    assert winner["action_key"] == "consider_scaling"


def test_opportunity_identifies_low_share_quality_product(db, org_store):
    org, store = org_store
    dominant = add_product(db, org, store, "High volume")
    opportunity = add_product(db, org, store, "Small winner")

    for index in range(5):
        add_order_item(
            db, org, store, dominant,
            number=f"DOM-HIGH-{index}", status="delivered",
            created_at=datetime(2026, 9, 1, 8 + index), price=1000, cost=400,
        )

    for index, status in enumerate(
        ["delivered", "delivered", "confirmed", "confirmed", "confirmed"]
    ):
        add_order_item(
            db, org, store, opportunity,
            number=f"OPP-{index}", status=status,
            created_at=datetime(2026, 9, 2, 8 + index), price=100, cost=40,
        )
    db.commit()

    result = service_result(db, org, store)
    types = insight_types(result, opportunity.id)
    assert "opportunity" in types
    assert "winner" not in types
    item = next(
        insight for insight in result["insights"]
        if insight["type"] == "opportunity"
    )
    assert item["severity"] == "opportunity"
    assert item["action_key"] == "test_more_volume"


def test_strict_store_isolation(db, org_store):
    org, store = org_store
    own = add_product(db, org, store, "Own product")
    add_order_item(
        db, org, store, own,
        number="OWN", status="delivered",
        created_at=datetime(2026, 9, 1, 10), price=100, cost=40,
    )

    other_store = Store(
        organization_id=org.id,
        name="Foreign Store",
        slug="decision-intelligence-foreign",
        country_code="MX",
        currency="MXN",
        timezone="America/Mexico_City",
        default_language="es",
    )
    db.add(other_store)
    db.flush()
    foreign = add_product(db, org, other_store, "Foreign loss")
    add_order_item(
        db, org, other_store, foreign,
        number="FOREIGN", status="delivered",
        created_at=datetime(2026, 9, 1, 10), price=10, cost=1000,
    )
    db.commit()

    result = service_result(db, org, store)
    assert result["summary"]["products_evaluated"] == 1
    assert all(item["product_id"] != foreign.id for item in result["insights"])


def test_deterministic_sort_prefers_more_severe_magnitude(db, org_store):
    org, store = org_store
    mild = add_product(db, org, store, "A mild loss")
    severe = add_product(db, org, store, "Z severe loss")
    add_order_item(
        db, org, store, mild,
        number="MILD", status="delivered",
        created_at=datetime(2026, 9, 1, 10), price=100, cost=110,
    )
    add_order_item(
        db, org, store, severe,
        number="SEVERE", status="delivered",
        created_at=datetime(2026, 9, 1, 11), price=100, cost=200,
    )
    db.commit()

    result = service_result(db, org, store)
    losses = [item for item in result["insights"] if item["type"] == "negative_margin"]
    assert [item["product_id"] for item in losses] == [severe.id, mild.id]


def test_summary_counts_all_insights_before_limit(db, org_store):
    org, store = org_store
    loss = add_product(db, org, store, "Loss")
    thin = add_product(db, org, store, "Thin")
    winner = add_product(db, org, store, "Winner")
    add_order_item(
        db, org, store, loss,
        number="LOSS", status="delivered",
        created_at=datetime(2026, 9, 1, 8), price=100, cost=200,
    )
    for index in range(3):
        add_order_item(
            db, org, store, thin,
            number=f"THIN-SUM-{index}", status="delivered",
            created_at=datetime(2026, 9, 1, 10 + index), price=100, cost=90,
        )
    for index in range(5):
        add_order_item(
            db, org, store, winner,
            number=f"WIN-SUM-{index}", status="delivered",
            created_at=datetime(2026, 9, 2, 10 + index), price=100, cost=40,
        )
    db.commit()

    result = service_result(db, org, store, limit=1)
    summary_total = sum(
        result["summary"][key]
        for key in ("critical", "warning", "opportunity", "positive")
    )
    assert len(result["insights"]) == 1
    assert result["insights"][0]["severity"] == "critical"
    assert summary_total > len(result["insights"])
    assert result["summary"]["products_evaluated"] == 3


def test_evidence_contains_only_finite_numbers(db, org_store):
    org, store = org_store
    product = add_product(db, org, store, "Finite")
    add_order_item(
        db, org, store, product,
        number="FINITE", status="delivered",
        created_at=datetime(2026, 9, 2, 10), price=100, cost=150, quantity=10,
    )
    db.commit()

    result = service_result(
        db, org, store,
        date_from=datetime(2026, 9, 1),
        date_to=datetime(2026, 9, 11),
    )
    for item in result["insights"]:
        for value in item["evidence"].values():
            if isinstance(value, (int, float)):
                assert math.isfinite(value)
