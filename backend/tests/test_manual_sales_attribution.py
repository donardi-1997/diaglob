"""Regression tests for manual sales-attribution corrections."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.sales_attribution import (
    OrderSalesAttribution,
    OrderSalesAttributionChange,
)
from app.models import Agent, Order, Organization, OrganizationMembership, Store, User
from app.services.manual_sales_attribution import (
    get_order_attribution_history,
    set_manual_order_attribution,
)
from app.services.sales_attribution import SalesAttributionError


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


def _seed(db):
    org = Organization(
        name="Manual Attribution Org",
        slug="manual-attribution-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(org)
    db.flush()

    store = Store(
        organization_id=org.id,
        name="Main",
        slug="manual-main",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    other_store = Store(
        organization_id=org.id,
        name="Other",
        slug="manual-other",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add_all([store, other_store])
    db.flush()

    editor = User(email="editor@example.com", name="Editor")
    seller = User(email="seller@example.com", name="Laura")
    restricted = User(email="restricted@example.com", name="Restricted")
    db.add_all([editor, seller, restricted])
    db.flush()

    editor_membership = OrganizationMembership(
        user_id=editor.id,
        organization_id=org.id,
        role="manager",
        all_stores=True,
        active=True,
    )
    seller_membership = OrganizationMembership(
        user_id=seller.id,
        organization_id=org.id,
        role="operator",
        all_stores=True,
        active=True,
    )
    restricted_membership = OrganizationMembership(
        user_id=restricted.id,
        organization_id=org.id,
        role="operator",
        all_stores=False,
        active=True,
    )
    restricted_membership.stores.append(other_store)
    db.add_all([editor_membership, seller_membership, restricted_membership])

    agent = Agent(
        organization_id=org.id,
        name="AI Sales",
        role="sales",
        active=True,
    )
    db.add(agent)
    db.flush()
    agent.stores.append(store)

    order = Order(
        organization_id=org.id,
        store_id=store.id,
        order_number="HIST-1",
        total_amount=120000,
        currency="COP",
        source="shopify",
        lifecycle_status="delivered",
        created_at=datetime(2026, 9, 1),
    )
    db.add(order)
    db.commit()
    return org, store, editor, seller, restricted, agent, order


def test_manual_assign_reassign_and_clear_are_audited(db):
    org, store, editor, seller, _, agent, order = _seed(db)

    human = set_manual_order_attribution(
        db,
        org.id,
        store.id,
        order.id,
        changed_by_user_id=editor.id,
        actor_type="human",
        actor_id=seller.id,
    )
    assert human is not None
    assert human["actor_type"] == "human"
    assert human["actor_label"] == "Laura"
    assert human["source"] == "manual_reclassification"

    ai = set_manual_order_attribution(
        db,
        org.id,
        store.id,
        order.id,
        changed_by_user_id=editor.id,
        actor_type="ai",
        actor_id=agent.id,
    )
    assert ai is not None
    assert ai["actor_type"] == "ai"
    assert ai["actor_label"] == "AI Sales"

    cleared = set_manual_order_attribution(
        db,
        org.id,
        store.id,
        order.id,
        changed_by_user_id=editor.id,
        actor_type=None,
        actor_id=None,
    )
    assert cleared is None
    assert db.query(OrderSalesAttribution).filter_by(order_id=order.id).first() is None

    changes = (
        db.query(OrderSalesAttributionChange)
        .filter_by(order_id=order.id)
        .order_by(OrderSalesAttributionChange.id.asc())
        .all()
    )
    assert [change.action for change in changes] == ["assign", "reassign", "clear"]
    assert changes[0].changed_by_label == "Editor"
    assert changes[0].previous_actor_type is None
    assert changes[0].new_actor_type == "human"
    assert changes[0].new_actor_label == "Laura"
    assert changes[1].previous_actor_type == "human"
    assert changes[1].previous_actor_label == "Laura"
    assert changes[1].new_actor_type == "ai"
    assert changes[1].new_actor_label == "AI Sales"
    assert changes[2].previous_actor_type == "ai"
    assert changes[2].new_actor_type is None


def test_same_manual_actor_is_idempotent_and_does_not_duplicate_audit(db):
    org, store, editor, seller, _, _, order = _seed(db)

    for _ in range(2):
        result = set_manual_order_attribution(
            db,
            org.id,
            store.id,
            order.id,
            changed_by_user_id=editor.id,
            actor_type="human",
            actor_id=seller.id,
        )
        assert result is not None
        assert result["actor_label"] == "Laura"

    assert db.query(OrderSalesAttributionChange).filter_by(order_id=order.id).count() == 1


def test_manual_editor_must_have_access_to_target_store(db):
    org, store, _, seller, restricted, _, order = _seed(db)

    with pytest.raises(SalesAttributionError, match="editor does not have access"):
        set_manual_order_attribution(
            db,
            org.id,
            store.id,
            order.id,
            changed_by_user_id=restricted.id,
            actor_type="human",
            actor_id=seller.id,
        )


def test_manual_target_actor_must_have_access_to_target_store(db):
    org, store, editor, _, restricted, _, order = _seed(db)

    with pytest.raises(SalesAttributionError, match="closer does not have access"):
        set_manual_order_attribution(
            db,
            org.id,
            store.id,
            order.id,
            changed_by_user_id=editor.id,
            actor_type="human",
            actor_id=restricted.id,
        )


def test_clear_requires_null_actor_id(db):
    org, store, editor, _, _, _, order = _seed(db)

    with pytest.raises(SalesAttributionError, match="actor_id must be null"):
        set_manual_order_attribution(
            db,
            org.id,
            store.id,
            order.id,
            changed_by_user_id=editor.id,
            actor_type=None,
            actor_id=999,
        )


def test_history_is_newest_first_and_preserves_actor_snapshots(db):
    org, store, editor, seller, _, agent, order = _seed(db)

    set_manual_order_attribution(
        db,
        org.id,
        store.id,
        order.id,
        changed_by_user_id=editor.id,
        actor_type="human",
        actor_id=seller.id,
    )
    set_manual_order_attribution(
        db,
        org.id,
        store.id,
        order.id,
        changed_by_user_id=editor.id,
        actor_type="ai",
        actor_id=agent.id,
    )

    changes = (
        db.query(OrderSalesAttributionChange)
        .filter_by(order_id=order.id)
        .order_by(OrderSalesAttributionChange.id.asc())
        .all()
    )
    changes[0].created_at = datetime(2026, 9, 10, 10, 0)
    changes[1].created_at = datetime(2026, 9, 10, 10, 0) + timedelta(seconds=1)
    db.commit()

    history = get_order_attribution_history(db, org.id, store.id, order.id)

    assert [item["action"] for item in history] == ["reassign", "assign"]
    assert history[0]["previous_actor_label"] == "Laura"
    assert history[0]["new_actor_label"] == "AI Sales"
    assert history[0]["changed_by_label"] == "Editor"


def test_history_rejects_cross_store_order_lookup(db):
    org, store, _, _, _, _, order = _seed(db)

    with pytest.raises(SalesAttributionError, match="Order not found"):
        get_order_attribution_history(db, org.id, store.id + 1, order.id)
