"""Authorization tests for LLM/action tools."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import MembershipStore, Organization, OrganizationMembership, Store, User
from app.services.action_policy import evaluate_action
from app.services.ai_tool_registry import list_authorized_tools


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


def seed_membership(
    db,
    *,
    role="manager",
    all_stores=True,
    plan="growth",
    subscription_status="active",
):
    organization = Organization(
        name=f"Agent Policy {role}",
        slug=f"agent-policy-{role}-{all_stores}",
        plan=plan,
        subscription_status=subscription_status,
        active=True,
    )
    db.add(organization)
    db.flush()

    user = User(
        email=f"{role}-{all_stores}@example.com",
        name=f"{role} user",
        active=True,
    )
    db.add(user)
    db.flush()

    membership = OrganizationMembership(
        user_id=user.id,
        organization_id=organization.id,
        role=role,
        all_stores=all_stores,
        active=True,
    )
    db.add(membership)
    db.flush()

    store_a = Store(
        organization_id=organization.id,
        name="Store A",
        slug=f"store-a-{role}-{all_stores}",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
        deleted=False,
    )
    store_b = Store(
        organization_id=organization.id,
        name="Store B",
        slug=f"store-b-{role}-{all_stores}",
        country_code="US",
        currency="USD",
        timezone="America/New_York",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add_all([store_a, store_b])
    db.flush()

    if not all_stores:
        db.add(
            MembershipStore(
                membership_id=membership.id,
                store_id=store_a.id,
            )
        )

    db.commit()
    db.refresh(membership)
    return membership, store_a, store_b


def test_manager_can_read_and_create_automation(db):
    membership, store, _ = seed_membership(db)

    read = evaluate_action(
        db,
        membership,
        "orders.list",
        store_id=store.id,
    )
    create = evaluate_action(
        db,
        membership,
        "automations.create",
        store_id=store.id,
    )
    fulfillment = evaluate_action(
        db,
        membership,
        "fulfillment.retry",
        store_id=store.id,
    )

    assert read.allowed is True
    assert read.confirmation == "none"
    assert create.allowed is True
    assert create.confirmation == "simple"
    assert fulfillment.allowed is True
    assert fulfillment.risk == "financial"
    assert fulfillment.confirmation == "critical"


def test_operator_only_sees_tools_backed_by_role_permissions(db):
    membership, store, _ = seed_membership(db, role="operator")

    tool_names = {
        item["name"]
        for item in list_authorized_tools(
            db,
            membership,
            store_id=store.id,
        )
    }

    assert "customers.search" in tool_names
    assert "orders.list" not in tool_names
    assert "automations.create" not in tool_names
    assert "analytics.summary" not in tool_names


def test_analyst_can_use_analytics_but_not_commerce_tools(db):
    membership, store, _ = seed_membership(db, role="analyst")

    analytics = evaluate_action(
        db,
        membership,
        "analytics.summary",
        store_id=store.id,
    )
    products = evaluate_action(
        db,
        membership,
        "products.list",
        store_id=store.id,
    )

    assert analytics.allowed is True
    assert products.allowed is False
    assert products.code == "PERMISSION_DENIED"


def test_limited_membership_cannot_cross_store_scope(db):
    membership, store_a, store_b = seed_membership(
        db,
        all_stores=False,
    )

    allowed = evaluate_action(
        db,
        membership,
        "orders.list",
        store_id=store_a.id,
    )
    denied = evaluate_action(
        db,
        membership,
        "orders.list",
        store_id=store_b.id,
    )

    assert allowed.allowed is True
    assert denied.allowed is False
    assert denied.code == "STORE_ACCESS_DENIED"


def test_read_tools_stay_available_without_paid_plan_but_writes_do_not(db):
    membership, store, _ = seed_membership(
        db,
        plan="none",
        subscription_status="inactive",
    )

    read = evaluate_action(
        db,
        membership,
        "orders.list",
        store_id=store.id,
    )
    write = evaluate_action(
        db,
        membership,
        "automations.create",
        store_id=store.id,
    )

    assert read.allowed is True
    assert write.allowed is False
    assert write.code == "PLAN_REQUIRED"


def test_external_read_is_not_misclassified_as_write(db):
    membership, store, _ = seed_membership(
        db,
        plan="none",
        subscription_status="inactive",
    )

    decision = evaluate_action(
        db,
        membership,
        "suppliers.cj.search",
        store_id=store.id,
    )

    assert decision.allowed is True
    assert decision.risk == "external"


def test_unknown_action_is_denied(db):
    membership, store, _ = seed_membership(db)

    decision = evaluate_action(
        db,
        membership,
        "database.drop_everything",
        store_id=store.id,
    )

    assert decision.allowed is False
    assert decision.code == "ACTION_UNKNOWN"


def test_tool_catalog_never_includes_denied_capabilities(db):
    membership, store, _ = seed_membership(db, role="operator")

    tools = list_authorized_tools(
        db,
        membership,
        store_id=store.id,
        include_denied=False,
    )

    assert tools
    assert all(item["authorization"]["allowed"] is True for item in tools)
    assert all("input_schema" in item for item in tools)
