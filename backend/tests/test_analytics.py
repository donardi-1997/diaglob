"""
Tests for Analytics Phase 1.

Covers:
- Summary metrics
- Timeseries
- Conversations analytics
- Commerce analytics
- Automations analytics
- Date range filtering
- Multi-tenant/multi-store isolation
- Edge cases (empty data)
"""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import (
    app,
    get_current_membership,
    get_current_user,
)
from app.models import (
    Automation,
    AutomationExecution,
    Conversation,
    Customer,
    Message,
    Order,
    OrderItem,
    Organization,
    OrganizationMembership,
    Product,
    ProductVariant,
    Store,
    User,
)

SQLALCHEMY_TEST_DATABASE_URL = (
    "sqlite:///./test_analytics.db"
)

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
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
def org(db):
    o = Organization(
        name="Analytics Org",
        slug="analytics-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(o)
    db.flush()
    return o


@pytest.fixture()
def user(db, org):
    u = User(
        email="analytics@test.com",
        name="Analytics Tester",
        external_auth_id="analytics-cognito-sub",
    )
    db.add(u)
    db.flush()

    m = OrganizationMembership(
        user_id=u.id,
        organization_id=org.id,
        role="manager",
    )
    db.add(m)
    db.flush()
    return u


@pytest.fixture()
def membership(db, user, org):
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id
            == user.id,
            OrganizationMembership.organization_id
            == org.id,
        )
        .first()
    )


@pytest.fixture()
def store(db, org):
    s = Store(
        organization_id=org.id,
        name="Analytics Store",
        slug="analytics-store",
        country_code="US",
        currency="USD",
        timezone="America/New_York",
        default_language="en",
    )
    db.add(s)
    db.flush()
    return s


@pytest.fixture()
def store2(db, org):
    s = Store(
        organization_id=org.id,
        name="Analytics Store 2",
        slug="analytics-store-2",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(s)
    db.flush()
    return s


@pytest.fixture()
def client(db, membership):
    original_overrides = dict(
        app.dependency_overrides
    )

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    def _override_user():
        return membership.user

    def _override_membership():
        return membership

    app.dependency_overrides[get_db] = (
        _override_get_db
    )
    app.dependency_overrides[
        get_current_user
    ] = _override_user
    app.dependency_overrides[
        get_current_membership
    ] = _override_membership

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    app.dependency_overrides.update(
        original_overrides
    )


def _seed_data(db, org, store):
    """Seed realistic test data."""
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)

    cust = Customer(
        organization_id=org.id,
        name="Test Customer",
        phone="+1234567890",
    )
    db.add(cust)
    db.flush()

    c1 = Conversation(
        organization_id=org.id,
        store_id=store.id,
        customer_id=cust.id,
        channel="whatsapp",
        mode="ai",
    )
    db.add(c1)
    db.flush()

    c2 = Conversation(
        organization_id=org.id,
        store_id=store.id,
        customer_id=cust.id,
        channel="internal",
        mode="human",
    )
    db.add(c2)
    db.flush()

    m1 = Message(
        conversation_id=c1.id,
        sender="customer",
        text="Hello",
        provider="whatsapp",
    )
    db.add(m1)

    m2 = Message(
        conversation_id=c1.id,
        sender="agent",
        text="Hi there",
        provider="internal",
    )
    db.add(m2)

    m3 = Message(
        conversation_id=c2.id,
        sender="customer",
        text="Help",
        provider="internal",
    )
    db.add(m3)
    db.flush()

    p1 = Product(
        organization_id=org.id,
        store_id=store.id,
        title="Widget A",
        active=True,
    )
    db.add(p1)
    db.flush()

    o1 = Order(
        organization_id=org.id,
        store_id=store.id,
        order_number="A-001",
        total_amount=50000,
        currency="USD",
        source="shopify",
        external_creation_status="created",
    )
    db.add(o1)
    db.flush()

    oi1 = OrderItem(
        order_id=o1.id,
        organization_id=org.id,
        store_id=store.id,
        product_id=p1.id,
        title="Widget A",
        quantity=2,
        unit_price=25000,
        currency="USD",
    )
    db.add(oi1)

    o2 = Order(
        organization_id=org.id,
        store_id=store.id,
        order_number="A-002",
        total_amount=75000,
        currency="USD",
        source="shopify",
        external_creation_status="failed",
    )
    db.add(o2)
    db.flush()

    a1 = Automation(
        organization_id=org.id,
        store_id=store.id,
        name="Test Auto",
        trigger_type="manual",
        conditions_json="[]",
        actions_json="[]",
        active=True,
    )
    db.add(a1)
    db.flush()

    e1 = AutomationExecution(
        automation_id=a1.id,
        organization_id=org.id,
        store_id=store.id,
        event_type="manual",
        status="success",
        input_json="{}",
        result_json="{}",
        started_at=now,
        completed_at=now + timedelta(seconds=2),
    )
    db.add(e1)

    e2 = AutomationExecution(
        automation_id=a1.id,
        organization_id=org.id,
        store_id=store.id,
        event_type="manual",
        status="failed",
        input_json="{}",
        result_json="{}",
        error_message="Test error",
        started_at=yesterday,
        completed_at=yesterday
        + timedelta(seconds=1),
    )
    db.add(e2)
    db.flush()

    db.commit()


# ============================================================
# SUMMARY TESTS
# ============================================================


class TestAnalyticsSummary:
    """Test summary endpoint."""

    def test_summary_with_data(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/summary"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_conversations"] == 2
        assert data["total_messages"] == 3
        assert data["total_products"] == 1
        assert data["total_orders"] == 2
        assert data["total_order_value"] == 125000
        assert data["total_executions"] == 2
        assert data["active_automations"] == 1

    def test_summary_empty_data(
        self, client, store
    ):
        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/summary"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_conversations"] == 0
        assert data["total_messages"] == 0
        assert data["total_orders"] == 0
        assert data["total_order_value"] == 0
        assert data["avg_order_value"] == 0
        assert data["automation_success_rate"] == 0

    def test_summary_store_not_found(
        self, client
    ):
        resp = client.get(
            "/api/stores/99999/analytics/summary"
        )

        assert resp.status_code == 404


# ============================================================
# TIMESERIES TESTS
# ============================================================


class TestAnalyticsTimeseries:
    """Test timeseries endpoint."""

    def test_timeseries_with_data(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/timeseries"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

        today = (
            datetime.utcnow()
            .strftime("%Y-%m-%d")
        )

        today_points = [
            p for p in data if p["date"] == today
        ]

        assert len(today_points) == 1
        assert today_points[0]["conversations"] >= 1
        assert today_points[0]["messages"] >= 1

    def test_timeseries_empty(
        self, client, store
    ):
        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/timeseries"
        )

        assert resp.status_code == 200
        assert resp.json() == []

    def test_timeseries_date_range(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        today = (
            datetime.utcnow()
            .strftime("%Y-%m-%d")
        )

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/timeseries"
            f"?date_from={today}&date_to={today}"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1


# ============================================================
# CONVERSATIONS ANALYTICS TESTS
# ============================================================


class TestAnalyticsConversations:
    """Test conversations analytics endpoint."""

    def test_conversations_with_data(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/conversations"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_conversations"] == 2
        assert data["total_messages"] == 3
        assert data["avg_messages_per_conversation"] == 1.5
        assert "whatsapp" in data["by_channel"]
        assert "internal" in data["by_channel"]
        assert data["by_mode"]["ai"] == 1
        assert data["by_mode"]["human"] == 1

    def test_conversations_empty(
        self, client, store
    ):
        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/conversations"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_conversations"] == 0
        assert data["total_messages"] == 0


# ============================================================
# COMMERCE ANALYTICS TESTS
# ============================================================


class TestAnalyticsCommerce:
    """Test commerce analytics endpoint."""

    def test_commerce_with_data(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/commerce"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_orders"] == 2
        assert data["total_value"] == 125000
        assert data["avg_ticket"] == 62500
        assert "created" in data["by_status"]
        assert "failed" in data["by_status"]
        assert "shopify" in data["by_source"]

    def test_commerce_empty(
        self, client, store
    ):
        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/commerce"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_orders"] == 0
        assert data["total_value"] == 0

    def test_commerce_top_products(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/commerce"
        )

        data = resp.json()
        assert len(data["top_products"]) == 1
        assert (
            data["top_products"][0]["title"]
            == "Widget A"
        )
        assert (
            data["top_products"][0]["total_units"]
            == 2
        )


# ============================================================
# AUTOMATIONS ANALYTICS TESTS
# ============================================================


class TestAnalyticsAutomations:
    """Test automations analytics endpoint."""

    def test_automations_with_data(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/automations"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_automations"] == 1
        assert data["active_automations"] == 1
        assert data["total_executions"] == 2
        assert data["by_status"]["success"] == 1
        assert data["by_status"]["failed"] == 1
        assert data["success_rate"] == 50.0
        assert "manual" in data["by_trigger"]

    def test_automations_empty(
        self, client, store
    ):
        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/automations"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_automations"] == 0
        assert data["total_executions"] == 0
        assert data["success_rate"] == 0

    def test_automations_avg_duration(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/automations"
        )

        data = resp.json()
        assert (
            data["avg_duration_seconds"] is not None
        )
        assert data["avg_duration_seconds"] >= 0


# ============================================================
# DATE RANGE TESTS
# ============================================================


class TestAnalyticsDateRanges:
    """Test date range filtering."""

    def test_summary_with_date_range(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        today = (
            datetime.utcnow()
            .strftime("%Y-%m-%d")
        )

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/summary"
            f"?date_from={today}"
            f"&date_to={today}"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_conversations"] >= 1

    def test_invalid_date_range(
        self, client, store
    ):
        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/summary"
            f"?date_from=invalid&date_to=also-invalid"
        )

        assert resp.status_code == 200

    def test_date_from_future(
        self, client, store, db, org
    ):
        _seed_data(db, org, store)

        future = (
            datetime.utcnow() + timedelta(days=30)
        ).strftime("%Y-%m-%d")

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/analytics/summary"
            f"?date_from={future}"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_conversations"] == 0
        assert data["total_orders"] == 0


# ============================================================
# SECURITY & ISOLATION TESTS
# ============================================================


class TestAnalyticsSecurity:
    """Test multi-tenant and multi-store isolation."""

    def test_cross_store_isolation(
        self, client, store, store2, db, org
    ):
        _seed_data(db, org, store)

        resp = client.get(
            f"/api/stores/{store2.id}"
            f"/analytics/summary"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_conversations"] == 0
        assert data["total_orders"] == 0

    def test_store_not_found_404(
        self, client
    ):
        for endpoint in [
            "summary",
            "timeseries",
            "conversations",
            "commerce",
            "automations",
        ]:
            resp = client.get(
                f"/api/stores/99999"
                f"/analytics/{endpoint}"
            )
            assert resp.status_code == 404

    def test_analyst_role_has_access(
        self, db, org, store
    ):
        analyst = User(
            email="analyst-analytics@test.com",
            name="Analyst",
            external_auth_id="analyst-analytics-sub",
        )
        db.add(analyst)
        db.flush()

        analyst_m = OrganizationMembership(
            user_id=analyst.id,
            organization_id=org.id,
            role="analyst",
        )
        db.add(analyst_m)
        db.flush()
        db.commit()

        original_overrides = dict(
            app.dependency_overrides
        )

        def _override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = (
            _override_get_db
        )
        app.dependency_overrides[
            get_current_user
        ] = lambda: analyst

        app.dependency_overrides[
            get_current_membership
        ] = lambda: analyst_m

        with TestClient(app) as c:
            resp = c.get(
                f"/api/stores/{store.id}"
                f"/analytics/summary"
            )
            assert resp.status_code == 200

        app.dependency_overrides.clear()
        app.dependency_overrides.update(
            original_overrides
        )

    def test_operator_role_no_access(
        self, db, org, store
    ):
        operator = User(
            email="operator-analytics@test.com",
            name="Operator",
            external_auth_id="operator-analytics-sub",
        )
        db.add(operator)
        db.flush()

        operator_m = OrganizationMembership(
            user_id=operator.id,
            organization_id=org.id,
            role="operator",
        )
        db.add(operator_m)
        db.flush()
        db.commit()

        original_overrides = dict(
            app.dependency_overrides
        )

        def _override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = (
            _override_get_db
        )
        app.dependency_overrides[
            get_current_user
        ] = lambda: operator

        app.dependency_overrides[
            get_current_membership
        ] = lambda: operator_m

        with TestClient(app) as c:
            resp = c.get(
                f"/api/stores/{store.id}"
                f"/analytics/summary"
            )
            assert resp.status_code == 403

        app.dependency_overrides.clear()
        app.dependency_overrides.update(
            original_overrides
        )
