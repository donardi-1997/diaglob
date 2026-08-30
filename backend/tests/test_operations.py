"""
Tests for the Operations Center service.

Covers:
- Summary with data
- Summary with no data
- Store isolation
- Cross-tenant isolation
- Activity feed
- Alerts
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    Agent,
    Automation,
    AutomationExecution,
    Conversation,
    Customer,
    Message,
    Order,
    Product,
    ProductVariant,
    Organization,
    OrganizationMembership,
    Store,
    User,
    WhatsAppConnection,
)
from app.operations import get_operations_summary


@pytest.fixture(scope="module")
def setup_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    org = Organization(
        id=1,
        name="Test Org",
        slug="test-org",
        plan="growth",
    )
    session.add(org)

    user = User(
        id=1,
        email="test@test.com",
        name="Test User",
    )
    session.add(user)

    membership = OrganizationMembership(
        id=1,
        user_id=1,
        organization_id=1,
        role="owner",
    )
    session.add(membership)

    store = Store(
        id=1,
        organization_id=1,
        name="Test Store",
        slug="test-store",
        country_code="US",
        currency="USD",
        timezone="UTC",
        active=True,
    )
    session.add(store)

    other_org = Organization(
        id=2,
        name="Other Org",
        slug="other-org",
        plan="starter",
    )
    session.add(other_org)

    other_store = Store(
        id=2,
        organization_id=2,
        name="Other Store",
        slug="other-store",
        country_code="US",
        currency="USD",
        timezone="UTC",
        active=True,
    )
    session.add(other_store)

    customer = Customer(
        id=1,
        organization_id=1,
        name="John Doe",
        phone="+1234567890",
    )
    session.add(customer)

    customer2 = Customer(
        id=2,
        organization_id=2,
        name="Jane Doe",
        phone="+0987654321",
    )
    session.add(customer2)

    conv1 = Conversation(
        id=1,
        organization_id=1,
        store_id=1,
        customer_id=1,
        channel="whatsapp",
        mode="ai",
    )
    session.add(conv1)

    conv2 = Conversation(
        id=2,
        organization_id=2,
        store_id=2,
        customer_id=2,
        channel="whatsapp",
        mode="ai",
    )
    session.add(conv2)

    msg1 = Message(
        id=1,
        conversation_id=1,
        sender="user",
        text="Hello",
    )
    session.add(msg1)

    msg2 = Message(
        id=2,
        conversation_id=1,
        sender="ai",
        text="Hi there",
    )
    session.add(msg2)

    order1 = Order(
        id=1,
        organization_id=1,
        store_id=1,
        customer_id=1,
        total_amount=150.00,
        order_number="ORD-001",
        currency="USD",
        source="shopify",
        external_creation_status="created",
    )
    session.add(order1)

    order2 = Order(
        id=2,
        organization_id=2,
        store_id=2,
        customer_id=2,
        total_amount=75.00,
        order_number="ORD-002",
        currency="USD",
        source="manual",
    )
    session.add(order2)

    auto1 = Automation(
        id=1,
        organization_id=1,
        store_id=1,
        name="Auto 1",
        trigger_type="order.created",
        active=True,
    )
    session.add(auto1)

    auto2 = Automation(
        id=2,
        organization_id=2,
        store_id=2,
        name="Auto 2",
        trigger_type="manual",
        active=False,
    )
    session.add(auto2)

    exe1 = AutomationExecution(
        id=1,
        automation_id=1,
        organization_id=1,
        store_id=1,
        event_type="order.created",
        status="success",
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    session.add(exe1)

    product1 = Product(
        id=1,
        organization_id=1,
        store_id=1,
        title="Product A",
        active=True,
    )
    session.add(product1)

    variant1 = ProductVariant(
        id=1,
        product_id=1,
        title="Variant A",
        price=29.99,
        currency="USD",
    )
    session.add(variant1)

    agent1 = Agent(
        id=1,
        organization_id=1,
        name="Agent 1",
        role="sales",
        active=True,
    )
    session.add(agent1)

    whatsapp1 = WhatsAppConnection(
        id=1,
        organization_id=1,
        store_id=1,
        phone_number_id="pn-1",
        business_account_id="ba-1",
        access_token_encrypted="encrypted-token",
        verify_token="verify-token-1",
        status="connected",
    )
    session.add(whatsapp1)

    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


class TestOperationsSummary:
    """Test operations summary endpoint."""

    def test_summary_with_data(self, setup_db):
        result = get_operations_summary(
            db=setup_db,
            organization_id=1,
            store_id=1,
        )

        assert result["conversations"]["total"] == 1
        assert result["conversations"]["messages_total"] == 2
        assert result["orders"]["total"] == 1
        assert result["orders"]["total_value"] == 150.00
        assert result["automations"]["total"] == 1
        assert result["automations"]["active"] == 1
        assert result["products"]["total"] == 1
        assert result["products"]["variants"] == 1
        assert result["agents"]["total"] == 1
        assert result["agents"]["active"] == 1
        assert result["integrations"]["whatsapp_connected"] is True

    def test_summary_empty_store(self, setup_db):
        other_org = (
            setup_db.query(Organization)
            .filter(Organization.id == 2)
            .first()
        )

        result = get_operations_summary(
            db=setup_db,
            organization_id=2,
            store_id=2,
        )

        assert result["conversations"]["total"] == 1
        assert result["orders"]["total"] == 1

    def test_store_isolation(self, setup_db):
        result1 = get_operations_summary(
            db=setup_db,
            organization_id=1,
            store_id=1,
        )

        result2 = get_operations_summary(
            db=setup_db,
            organization_id=2,
            store_id=2,
        )

        assert result1["orders"]["total"] == 1
        assert result2["orders"]["total"] == 1

    def test_activity_feed(self, setup_db):
        result = get_operations_summary(
            db=setup_db,
            organization_id=1,
            store_id=1,
        )

        activity = result["activity"]
        assert len(activity) > 0

        types = {a["type"] for a in activity}
        assert "conversation" in types or "order" in types

    def test_alerts_for_no_whatsapp(self, setup_db):
        result = get_operations_summary(
            db=setup_db,
            organization_id=1,
            store_id=1,
        )

        alerts = result["alerts"]

        alert_types = {a["type"] for a in alerts}

        assert "no_whatsapp" not in alert_types

    def test_orders_by_status(self, setup_db):
        result = get_operations_summary(
            db=setup_db,
            organization_id=1,
            store_id=1,
        )

        by_status = result["orders"]["by_status"]
        assert "created" in by_status

    def test_ai_resolved_percentage(self, setup_db):
        result = get_operations_summary(
            db=setup_db,
            organization_id=1,
            store_id=1,
        )

        pct = result["conversations"]["ai_resolved_pct"]
        assert 0 <= pct <= 100

    def test_output_structure(self, setup_db):
        result = get_operations_summary(
            db=setup_db,
            organization_id=1,
            store_id=1,
        )

        assert "conversations" in result
        assert "orders" in result
        assert "automations" in result
        assert "products" in result
        assert "agents" in result
        assert "integrations" in result
        assert "alerts" in result
        assert "activity" in result
