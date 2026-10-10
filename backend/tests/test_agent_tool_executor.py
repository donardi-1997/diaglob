"""Execution and one-time approval tests for agent tools."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    AutomationFlow,
    Order,
    Organization,
    OrganizationMembership,
    Product,
    ProductVariant,
    Store,
    User,
)
from app.services.agent_approvals import approve_action
from app.services.agent_tool_executor import execute_agent_tool


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


def seed(db):
    organization = Organization(
        name="Agent Executor Org",
        slug="agent-executor-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(organization)
    db.flush()

    user = User(
        email="agent-executor@example.com",
        name="Agent Executor",
        active=True,
    )
    db.add(user)
    db.flush()

    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=organization.id,
        role="manager",
        all_stores=True,
        active=True,
    )
    db.add(membership)
    db.flush()

    store = Store(
        organization_id=organization.id,
        name="Executor Store",
        slug="executor-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.flush()

    order = Order(
        organization_id=organization.id,
        store_id=store.id,
        shopify_order_id="agent-100",
        external_order_id="agent-100",
        order_number="100",
        total_amount=125000,
        currency="COP",
        financial_status="paid",
        payment_status="paid",
        fulfillment_status="unfulfilled",
        lifecycle_status="paid",
        source="shopify",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(order)
    db.commit()
    db.refresh(membership)
    return membership, store, order


def test_safe_read_tool_executes_without_approval(db):
    membership, store, order = seed(db)

    result = execute_agent_tool(
        db,
        membership,
        tool_name="orders.list",
        store_id=store.id,
        arguments={"limit": 10},
    )

    assert result["status"] == "success"
    assert result["result"]["count"] == 1
    assert result["result"]["items"][0]["id"] == order.id


@pytest.mark.parametrize("price,stock,available,expected", [
    (0, 10, True, False), (100, 0, True, False),
    (100, 10, False, False), (100, 10, True, True),
])
def test_copilot_product_availability_requires_price_and_verified_stock(
    db, price, stock, available, expected,
):
    membership, store, _ = seed(db)
    product = Product(organization_id=membership.organization_id, store_id=store.id,
                      title="Bakata product", active=True)
    db.add(product)
    db.flush()
    db.add(ProductVariant(product_id=product.id, title="Default", price=price,
                          currency="COP", inventory_quantity=stock, available=available))
    db.commit()
    result = execute_agent_tool(db, membership, tool_name="products.list",
                                store_id=store.id, arguments={})
    assert result["status"] == "success"
    assert result["result"]["items"][0]["variants"][0]["available"] is expected


def test_write_tool_requires_explicit_approval(db):
    membership, store, _order = seed(db)
    arguments = {
        "name": "AI draft flow",
        "graph": {},
    }

    result = execute_agent_tool(
        db,
        membership,
        tool_name="automations.create",
        store_id=store.id,
        arguments=arguments,
    )

    assert result["status"] == "confirmation_required"
    assert result["confirmation"] == "simple"
    assert result["approval"]["status"] == "pending"
    assert db.query(AutomationFlow).count() == 0


def test_approved_write_executes_once_and_consumes_approval(db):
    membership, store, _order = seed(db)
    arguments = {
        "name": "Approved AI flow",
        "graph": {},
    }

    requested = execute_agent_tool(
        db,
        membership,
        tool_name="automations.create",
        store_id=store.id,
        arguments=arguments,
    )
    approval_id = requested["approval"]["id"]
    approved = approve_action(db, membership, approval_id)
    assert approved.status == "approved"

    executed = execute_agent_tool(
        db,
        membership,
        tool_name="automations.create",
        store_id=store.id,
        arguments=arguments,
        approval_id=approval_id,
    )

    assert executed["status"] == "success"
    assert executed["result"]["name"] == "Approved AI flow"
    assert db.query(AutomationFlow).count() == 1

    replay = execute_agent_tool(
        db,
        membership,
        tool_name="automations.create",
        store_id=store.id,
        arguments=arguments,
        approval_id=approval_id,
    )
    assert replay["status"] == "denied"
    assert replay["code"] == "APPROVAL_NOT_APPROVED"
    assert db.query(AutomationFlow).count() == 1


def test_approval_cannot_be_reused_with_changed_arguments(db):
    membership, store, _order = seed(db)
    original = {
        "name": "Original flow",
        "graph": {},
    }

    requested = execute_agent_tool(
        db,
        membership,
        tool_name="automations.create",
        store_id=store.id,
        arguments=original,
    )
    approval_id = requested["approval"]["id"]
    approve_action(db, membership, approval_id)

    tampered = execute_agent_tool(
        db,
        membership,
        tool_name="automations.create",
        store_id=store.id,
        arguments={
            "name": "Different flow",
            "graph": {},
        },
        approval_id=approval_id,
    )

    assert tampered["status"] == "denied"
    assert tampered["code"] == "APPROVAL_ARGUMENTS_MISMATCH"
    assert db.query(AutomationFlow).count() == 0


def test_critical_fulfillment_never_executes_without_approval(db):
    membership, store, _order = seed(db)

    result = execute_agent_tool(
        db,
        membership,
        tool_name="fulfillment.retry",
        store_id=store.id,
        arguments={},
    )

    assert result["status"] == "confirmation_required"
    assert result["confirmation"] == "critical"
    assert result["risk"] == "financial"

def test_invalid_tool_arguments_are_denied_before_approval(db):
    membership, store, _order = seed(db)

    result = execute_agent_tool(
        db,
        membership,
        tool_name="automations.create",
        store_id=store.id,
        arguments={
            "name": "Unsafe flow",
            "graph": {},
            "unexpected": "must not reach approval",
        },
    )

    assert result["status"] == "denied"
    assert result["code"] == "TOOL_ARGUMENTS_INVALID"
    assert "unknown field" in result["message"]
    assert db.query(AutomationFlow).count() == 0

