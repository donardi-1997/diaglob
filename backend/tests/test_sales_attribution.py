"""Regression tests for explicit sales attribution analytics."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.sales_attribution import OrderSalesAttribution
from app.models import (
    Agent,
    Order,
    OrderItem,
    Organization,
    OrganizationMembership,
    Store,
    User,
)
from app.services.sales_attribution import (
    SalesAttributionError,
    get_sales_attribution_analytics,
    record_ai_order_attribution,
    record_human_order_attribution,
)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
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


def _seed_workspace(db):
    org = Organization(
        name="Attribution Org",
        slug="attribution-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()

    store = Store(
        organization_id=org.id,
        name="Main Store",
        slug="main-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    other_store = Store(
        organization_id=org.id,
        name="Other Store",
        slug="other-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add_all([store, other_store])
    db.flush()

    user = User(email="seller@example.com", name="Laura Seller")
    other_user = User(email="other@example.com", name="Other Seller")
    db.add_all([user, other_user])
    db.flush()
    db.add_all(
        [
            OrganizationMembership(
                user_id=user.id,
                organization_id=org.id,
                role="operator",
                all_stores=True,
                active=True,
            ),
            OrganizationMembership(
                user_id=other_user.id,
                organization_id=org.id,
                role="operator",
                all_stores=True,
                active=True,
            ),
        ]
    )

    agent = Agent(
        organization_id=org.id,
        name="AI Sales Agent",
        role="sales",
        active=True,
    )
    db.add(agent)
    db.flush()
    agent.stores.append(store)
    db.commit()
    return org, store, other_store, user, other_user, agent


def _add_order(
    db,
    org,
    store,
    *,
    number: str,
    status: str,
    total: float,
    cost: float | None,
    created_at: datetime,
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
    db.add(
        OrderItem(
            order_id=order.id,
            organization_id=org.id,
            store_id=store.id,
            title=f"Item {number}",
            sku=f"SKU-{number}",
            quantity=1,
            unit_price=total,
            unit_cost=cost,
            currency=store.currency,
        )
    )
    db.commit()
    return order


def test_analytics_separates_human_ai_and_unattributed_orders(db):
    org, store, _, user, _, agent = _seed_workspace(db)
    day = datetime(2026, 9, 10)

    human_delivered = _add_order(
        db,
        org,
        store,
        number="HUMAN-D",
        status="delivered",
        total=100,
        cost=40,
        created_at=day,
    )
    human_cancelled = _add_order(
        db,
        org,
        store,
        number="HUMAN-C",
        status="cancelled",
        total=50,
        cost=10,
        created_at=day,
    )
    ai_delivered = _add_order(
        db,
        org,
        store,
        number="AI-D",
        status="delivered",
        total=200,
        cost=80,
        created_at=day,
    )
    _add_order(
        db,
        org,
        store,
        number="UNKNOWN-D",
        status="delivered",
        total=300,
        cost=100,
        created_at=day,
    )

    record_human_order_attribution(
        db,
        org.id,
        store.id,
        human_delivered.id,
        user.id,
    )
    record_human_order_attribution(
        db,
        org.id,
        store.id,
        human_cancelled.id,
        user.id,
    )
    record_ai_order_attribution(
        db,
        org.id,
        store.id,
        ai_delivered.id,
        agent.id,
    )

    result = get_sales_attribution_analytics(
        db,
        org.id,
        store.id,
        datetime(2026, 9, 10),
        datetime(2026, 9, 11),
    )

    assert result["total_orders"] == 4
    assert result["attributed_orders"] == 3
    assert result["unattributed_orders"] == 1
    assert result["attribution_rate_pct"] == 75.0

    human = result["by_actor_type"]["human"]
    assert human["total_orders"] == 2
    assert human["delivered_orders"] == 1
    assert human["cancelled_orders"] == 1
    assert human["delivered_revenue"] == 100.0
    assert human["gross_profit"] == 60.0
    assert human["delivery_rate"] == 50.0
    assert human["cancellation_rate"] == 50.0

    ai = result["by_actor_type"]["ai"]
    assert ai["total_orders"] == 1
    assert ai["delivered_revenue"] == 200.0
    assert ai["gross_profit"] == 120.0
    assert ai["delivery_rate"] == 100.0

    unattributed = result["by_actor_type"]["unattributed"]
    assert unattributed["total_orders"] == 1
    assert unattributed["delivered_revenue"] == 300.0
    assert unattributed["gross_profit"] == 200.0

    assert result["employees"][0]["actor_id"] == user.id
    assert result["employees"][0]["actor_label"] == "Laura Seller"
    assert result["employees"][0]["total_orders"] == 2
    assert result["ai_agents"][0]["actor_id"] == agent.id
    assert result["ai_agents"][0]["actor_label"] == "AI Sales Agent"


def test_existing_attribution_is_not_silently_overwritten(db):
    org, store, _, user, _, agent = _seed_workspace(db)
    order = _add_order(
        db,
        org,
        store,
        number="LOCKED",
        status="delivered",
        total=100,
        cost=40,
        created_at=datetime(2026, 9, 10),
    )

    first = record_human_order_attribution(
        db,
        org.id,
        store.id,
        order.id,
        user.id,
    )
    second = record_ai_order_attribution(
        db,
        org.id,
        store.id,
        order.id,
        agent.id,
    )

    assert first["actor_type"] == "human"
    assert second["actor_type"] == "human"
    row = db.query(OrderSalesAttribution).filter_by(order_id=order.id).one()
    assert row.human_user_id == user.id
    assert row.ai_agent_id is None


def test_actor_label_is_historical_snapshot(db):
    org, store, _, user, _, _ = _seed_workspace(db)
    order = _add_order(
        db,
        org,
        store,
        number="SNAPSHOT",
        status="delivered",
        total=100,
        cost=25,
        created_at=datetime(2026, 9, 10),
    )
    record_human_order_attribution(
        db,
        org.id,
        store.id,
        order.id,
        user.id,
    )

    user.name = "Renamed User"
    db.commit()
    result = get_sales_attribution_analytics(db, org.id, store.id, None, None)

    assert result["employees"][0]["actor_label"] == "Laura Seller"


def test_store_scope_prevents_cross_store_attribution_leaks(db):
    org, store, other_store, user, other_user, _ = _seed_workspace(db)
    main_order = _add_order(
        db,
        org,
        store,
        number="MAIN",
        status="delivered",
        total=100,
        cost=30,
        created_at=datetime(2026, 9, 10),
    )
    other_order = _add_order(
        db,
        org,
        other_store,
        number="OTHER",
        status="delivered",
        total=999,
        cost=1,
        created_at=datetime(2026, 9, 10),
    )
    record_human_order_attribution(
        db,
        org.id,
        store.id,
        main_order.id,
        user.id,
    )
    record_human_order_attribution(
        db,
        org.id,
        other_store.id,
        other_order.id,
        other_user.id,
    )

    result = get_sales_attribution_analytics(db, org.id, store.id, None, None)

    assert result["total_orders"] == 1
    assert result["overall"]["delivered_revenue"] == 100.0
    assert len(result["employees"]) == 1
    assert result["employees"][0]["actor_label"] == "Laura Seller"


def test_invalid_ai_agent_store_is_rejected(db):
    org, store, other_store, _, _, _ = _seed_workspace(db)
    other_agent = Agent(
        organization_id=org.id,
        name="Other Store AI",
        role="sales",
        active=True,
    )
    db.add(other_agent)
    db.flush()
    other_agent.stores.append(other_store)
    order = _add_order(
        db,
        org,
        store,
        number="WRONG-AI",
        status="delivered",
        total=100,
        cost=20,
        created_at=datetime(2026, 9, 10),
    )

    with pytest.raises(SalesAttributionError, match="does not belong"):
        record_ai_order_attribution(
            db,
            org.id,
            store.id,
            order.id,
            other_agent.id,
        )
