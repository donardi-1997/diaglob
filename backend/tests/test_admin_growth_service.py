"""Regression tests for platform admin growth analytics."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Conversation, Customer, Message, Order, Organization, Store, User
from app.services.admin_growth_service import get_admin_growth_metrics

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_admin_growth_service.db"

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


def test_admin_growth_tracks_recent_activity_and_billing_health(db):
    now = datetime.utcnow()
    recent = now - timedelta(days=1)
    old = now - timedelta(days=60)

    active_org = Organization(
        name="Active Merchant",
        slug="active-merchant",
        plan="growth",
        subscription_status="active",
        pending_plan="starter",
        auto_renew_enabled=False,
        created_at=recent,
    )
    old_org = Organization(
        name="Old Merchant",
        slug="old-merchant",
        plan="starter",
        subscription_status="active",
        created_at=old,
    )
    db.add_all([active_org, old_org])
    db.flush()

    user = User(
        email="admin-growth@example.com",
        name="Recent User",
        created_at=recent,
    )
    db.add(user)

    store = Store(
        organization_id=active_org.id,
        name="Growth Store",
        slug="growth-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        created_at=recent,
    )
    db.add(store)
    db.flush()

    customer = Customer(
        organization_id=active_org.id,
        name="Growth Customer",
        phone="3000000000",
        created_at=recent,
    )
    db.add(customer)
    db.flush()

    conversation = Conversation(
        organization_id=active_org.id,
        store_id=store.id,
        customer_id=customer.id,
        channel="internal",
        preview="test",
        unread=0,
        mode="ai",
        tags="",
        created_at=recent,
        updated_at=recent,
    )
    db.add(conversation)
    db.flush()

    db.add(
        Message(
            conversation_id=conversation.id,
            sender="ai",
            text="AI response",
            provider="internal",
            delivery_status="delivered",
            created_at=recent,
        )
    )
    db.add(
        Order(
            organization_id=active_org.id,
            store_id=store.id,
            order_number="ADMIN-GROWTH-1",
            total_amount=100,
            currency="COP",
            source="shopify",
            lifecycle_status="delivered",
            created_at=recent,
            updated_at=recent,
        )
    )
    db.commit()

    result = get_admin_growth_metrics(db, days=30)

    assert result["window_days"] == 30
    assert result["totals"]["new_organizations"] == 1
    assert result["totals"]["new_users"] == 1
    assert result["totals"]["ai_responses"] == 1
    assert result["totals"]["orders"] == 1

    billing = result["billing_health"]
    assert billing["subscription_statuses"]["active"] == 2
    assert billing["pending_plan_changes"] == 1
    assert billing["auto_renew_disabled"] == 1
    assert billing["historical_billing_available"] is False

    assert result["rankings"]["top_ai_usage"][0]["organization_id"] == active_org.id
    assert result["rankings"]["top_ai_usage"][0]["ai_responses"] == 1
    assert result["rankings"]["top_orders"][0]["orders"] == 1
    assert result["rankings"]["top_conversations"][0]["conversations"] == 1


def test_admin_growth_excludes_activity_outside_window(db):
    old = datetime.utcnow() - timedelta(days=45)
    org = Organization(
        name="Historical Merchant",
        slug="historical-merchant",
        plan="starter",
        subscription_status="active",
        created_at=old,
    )
    user = User(
        email="historical@example.com",
        name="Historical User",
        created_at=old,
    )
    db.add_all([org, user])
    db.commit()

    result = get_admin_growth_metrics(db, days=30)

    assert result["totals"]["new_organizations"] == 0
    assert result["totals"]["new_users"] == 0
    assert len(result["daily"]) == 30
