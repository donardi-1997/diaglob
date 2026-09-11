"""
Tests for Automations Phase 1.

Covers:
- CRUD operations
- Multi-tenant/multi-store isolation
- Condition evaluation
- Execution engine
- Action execution
- Security (permissions, cross-tenant, cross-store)
"""

import json

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
from app.automations import (
    evaluate_condition,
    evaluate_conditions,
    _resolve_field,
)
from app.models import (
    Automation,
    AutomationExecution,
    Order,
    Organization,
    OrganizationMembership,
    Store,
    User,
)

SQLALCHEMY_TEST_DATABASE_URL = (
    "sqlite:///./test_automations.db"
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


@pytest.fixture(scope="module")
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db(setup_db):
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.begin() as connection:
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())


@pytest.fixture()
def org(db):
    o = Organization(
        name="Test Org",
        slug="test-org-auto",
        plan="starter",
        subscription_status="active",
    )
    db.add(o)
    db.flush()
    return o


@pytest.fixture()
def user(db, org):
    u = User(
        email="auto@test.com",
        name="Auto Tester",
        external_auth_id="auto-cognito-sub",
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
        name="Auto Store",
        slug="auto-store",
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
        name="Auto Store 2",
        slug="auto-store-2",
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


# ============================================================
# CONDITION EVALUATION UNIT TESTS
# ============================================================


class TestConditionEvaluation:
    """Unit tests for the condition evaluator."""

    def test_eq_match(self):
        assert evaluate_condition(
            {"field": "x", "operator": "eq", "value": 5},
            {"x": 5},
        )

    def test_eq_no_match(self):
        assert not evaluate_condition(
            {"field": "x", "operator": "eq", "value": 5},
            {"x": 6},
        )

    def test_neq_match(self):
        assert evaluate_condition(
            {"field": "x", "operator": "neq", "value": 5},
            {"x": 6},
        )

    def test_gt_match(self):
        assert evaluate_condition(
            {"field": "x", "operator": "gt", "value": 10},
            {"x": 15},
        )

    def test_gt_no_match(self):
        assert not evaluate_condition(
            {"field": "x", "operator": "gt", "value": 10},
            {"x": 5},
        )

    def test_gte_match_equal(self):
        assert evaluate_condition(
            {"field": "x", "operator": "gte", "value": 10},
            {"x": 10},
        )

    def test_gte_match_greater(self):
        assert evaluate_condition(
            {"field": "x", "operator": "gte", "value": 10},
            {"x": 15},
        )

    def test_lt_match(self):
        assert evaluate_condition(
            {"field": "x", "operator": "lt", "value": 10},
            {"x": 5},
        )

    def test_lte_match_equal(self):
        assert evaluate_condition(
            {"field": "x", "operator": "lte", "value": 10},
            {"x": 10},
        )

    def test_contains_match(self):
        assert evaluate_condition(
            {
                "field": "name",
                "operator": "contains",
                "value": "test",
            },
            {"name": "This is a test"},
        )

    def test_contains_no_match(self):
        assert not evaluate_condition(
            {
                "field": "name",
                "operator": "contains",
                "value": "xyz",
            },
            {"name": "This is a test"},
        )

    def test_exists_when_present(self):
        assert evaluate_condition(
            {"field": "x", "operator": "exists", "value": None},
            {"x": 42},
        )

    def test_exists_when_absent(self):
        assert not evaluate_condition(
            {"field": "x", "operator": "exists", "value": None},
            {"y": 42},
        )

    def test_dotted_field(self):
        assert evaluate_condition(
            {
                "field": "order.total",
                "operator": "gte",
                "value": 100,
            },
            {"order": {"total": 150}},
        )

    def test_dotted_field_missing(self):
        assert not evaluate_condition(
            {
                "field": "order.total",
                "operator": "gte",
                "value": 100,
            },
            {"order": {}},
        )

    def test_missing_field_returns_false(self):
        assert not evaluate_condition(
            {
                "field": "nonexistent",
                "operator": "eq",
                "value": 1,
            },
            {"x": 1},
        )

    def test_invalid_operator_returns_false(self):
        assert not evaluate_condition(
            {
                "field": "x",
                "operator": "INVALID",
                "value": 1,
            },
            {"x": 1},
        )

    def test_empty_condition_returns_false(self):
        assert not evaluate_condition({}, {"x": 1})

    def test_evaluate_conditions_all_pass(self):
        assert evaluate_conditions(
            [
                {"field": "a", "operator": "eq", "value": 1},
                {"field": "b", "operator": "eq", "value": 2},
            ],
            {"a": 1, "b": 2},
        )

    def test_evaluate_conditions_one_fails(self):
        assert not evaluate_conditions(
            [
                {"field": "a", "operator": "eq", "value": 1},
                {"field": "b", "operator": "eq", "value": 3},
            ],
            {"a": 1, "b": 2},
        )

    def test_evaluate_conditions_empty_always_passes(self):
        assert evaluate_conditions([], {"x": 1})

    def test_resolve_field_nested(self):
        result = _resolve_field(
            {"a": {"b": {"c": 42}}},
            "a.b.c",
        )
        assert result == 42

    def test_resolve_field_missing(self):
        result = _resolve_field(
            {"a": 1},
            "b.c",
        )
        assert result is None


# ============================================================
# CRUD ENDPOINT TESTS
# ============================================================


class TestAutomationCRUD:
    """Test CRUD operations for automations."""

    def test_create_automation(
        self, client, store
    ):
        resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Test Rule",
                "trigger_type": "manual",
                "conditions_json": [],
                "actions_json": [
                    {"type": "log_event", "message": "Hello"}
                ],
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Rule"
        assert data["trigger_type"] == "manual"
        assert data["active"] is True
        assert data["store_id"] == store.id

    def test_list_automations(
        self, client, store
    ):
        client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Rule 1"},
        )

        client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Rule 2"},
        )

        resp = client.get(
            f"/api/stores/{store.id}/automations"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_get_automation(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Get Me"},
        )

        auto_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}"
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Get Me"

    def test_update_automation(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Original"},
        )

        auto_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}",
            json={"name": "Updated"},
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    def test_delete_automation(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Delete Me"},
        )

        auto_id = create_resp.json()["id"]

        resp = client.delete(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}"
        )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        get_resp = client.get(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}"
        )

        assert get_resp.status_code == 404

    def test_toggle_automation(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Toggle Me"},
        )

        auto_id = create_resp.json()["id"]
        assert create_resp.json()["active"] is True

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/toggle"
        )

        assert resp.status_code == 200
        assert resp.json()["active"] is False

        resp2 = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/toggle"
        )

        assert resp2.json()["active"] is True

    def test_duplicate_name_rejected(
        self, client, store
    ):
        client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Unique"},
        )

        resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Unique"},
        )

        assert resp.status_code == 409

    def test_invalid_trigger_type_rejected(
        self, client, store
    ):
        resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Bad Trigger",
                "trigger_type": "invalid.trigger",
            },
        )

        assert resp.status_code == 400

    def test_store_not_found_returns_404(
        self, client
    ):
        resp = client.get(
            "/api/stores/99999/automations"
        )

        assert resp.status_code == 404


# ============================================================
# SECURITY & ISOLATION TESTS
# ============================================================


class TestAutomationSecurity:
    """Test multi-tenant and multi-store isolation."""

    def test_cross_store_automation_list_empty(
        self, client, store, store2, db, org
    ):
        client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Store1 Rule"},
        )

        resp = client.get(
            f"/api/stores/{store2.id}/automations"
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_cross_tenant_automation_blocked(
        self, client, store, db
    ):
        other_org = Organization(
            name="Other Org",
            slug="other-org-auto",
            plan="starter",
            subscription_status="active",
        )
        db.add(other_org)
        db.flush()

        other_user = User(
            email="other@test.com",
            name="Other",
            external_auth_id="other-sub",
        )
        db.add(other_user)
        db.flush()

        other_membership = OrganizationMembership(
            user_id=other_user.id,
            organization_id=other_org.id,
            role="owner",
        )
        db.add(other_membership)
        db.flush()

        other_store = Store(
            organization_id=other_org.id,
            name="Other Store",
            slug="other-store-auto",
            country_code="US",
            currency="USD",
            timezone="America/New_York",
        )
        db.add(other_store)
        db.flush()

        db.commit()

        auto = Automation(
            organization_id=other_org.id,
            store_id=other_store.id,
            name="Secret Rule",
            trigger_type="manual",
            conditions_json="[]",
            actions_json="[]",
        )
        db.add(auto)
        db.commit()

        resp = client.get(
            f"/api/stores/{other_store.id}/automations"
        )

        assert resp.status_code == 404

    def test_manager_role_has_access(
        self, client, store
    ):
        resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Manager Rule"},
        )

        assert resp.status_code == 200

    def test_analyst_role_read_only(self, db, org, store):
        analyst_user = User(
            email="analyst@test.com",
            name="Analyst",
            external_auth_id="analyst-sub",
        )
        db.add(analyst_user)
        db.flush()

        analyst_membership = OrganizationMembership(
            user_id=analyst_user.id,
            organization_id=org.id,
            role="analyst",
        )
        db.add(analyst_membership)
        db.flush()

        auto = Automation(
            organization_id=org.id,
            store_id=store.id,
            name="Read Only Rule",
            trigger_type="manual",
            conditions_json="[]",
            actions_json="[]",
        )
        db.add(auto)
        db.commit()

        original_overrides = dict(
            app.dependency_overrides
        )

        def _override_user():
            return analyst_user

        def _override_membership():
            return analyst_membership

        app.dependency_overrides[
            get_current_user
        ] = _override_user
        app.dependency_overrides[
            get_current_membership
        ] = _override_membership

        with TestClient(app) as c:
            read_resp = c.get(
                f"/api/stores/{store.id}/automations"
            )
            assert read_resp.status_code == 403

            create_resp = c.post(
                f"/api/stores/{store.id}/automations",
                json={"name": "Should Fail"},
            )
            assert create_resp.status_code == 403

        app.dependency_overrides.clear()
        app.dependency_overrides.update(
            original_overrides
        )


# ============================================================
# EXECUTION TESTS
# ============================================================


class TestAutomationExecution:
    """Test the automation execution engine."""

    def test_manual_run_success(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Manual Test",
                "trigger_type": "manual",
                "conditions_json": [],
                "actions_json": [
                    {"type": "log_event", "message": "Test ran"}
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={
                "event_type": "manual",
                "payload": {
                    "customer_name": "Test",
                    "amount": 150000,
                },
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["event_type"] == "manual"
        assert "actions" in data["result_json"]

    def test_conditions_false_skipped(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Conditional",
                "trigger_type": "manual",
                "conditions_json": [
                    {
                        "field": "amount",
                        "operator": "gte",
                        "value": 200000,
                    }
                ],
                "actions_json": [
                    {"type": "log_event", "message": "Ran"}
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={
                "event_type": "manual",
                "payload": {"amount": 50000},
            },
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "skipped"

    def test_conditions_true_runs(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "High Value",
                "trigger_type": "manual",
                "conditions_json": [
                    {
                        "field": "amount",
                        "operator": "gte",
                        "value": 100000,
                    }
                ],
                "actions_json": [
                    {"type": "log_event", "message": "High value!"}
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={
                "event_type": "manual",
                "payload": {"amount": 150000},
            },
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_execution_persisted(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Persist Test",
                "trigger_type": "manual",
            },
        )

        auto_id = create_resp.json()["id"]

        client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={"event_type": "manual", "payload": {}},
        )

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/executions"
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert (
            resp.json()["items"][0]["status"]
            == "success"
        )

    def test_list_all_executions(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Exec List",
                "trigger_type": "manual",
            },
        )

        auto_id = create_resp.json()["id"]

        client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={"event_type": "manual", "payload": {}},
        )

        client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={"event_type": "manual", "payload": {}},
        )

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/automation-executions"
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_run_automation_not_found(
        self, client, store
    ):
        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/99999/run",
            json={"event_type": "manual", "payload": {}},
        )

        assert resp.status_code == 404

    def test_execution_with_empty_payload(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Empty Payload",
                "trigger_type": "manual",
                "conditions_json": [],
                "actions_json": [
                    {"type": "log_event", "message": "OK"}
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "success"


# ============================================================
# ACTION TESTS
# ============================================================


class TestAutomationActions:
    """Test action execution within automations."""

    def test_log_event_action(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Log Test",
                "trigger_type": "manual",
                "actions_json": [
                    {
                        "type": "log_event",
                        "message": "Event logged",
                    }
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={
                "event_type": "manual",
                "payload": {"test": True},
            },
        )

        assert resp.status_code == 200
        result = resp.json()["result_json"]
        assert len(result["actions"]) == 1
        assert (
            result["actions"][0]["action"]
            == "log_event"
        )
        assert (
            result["actions"][0]["status"]
            != "failed"
        )

    def test_add_order_note_action(
        self, client, store, db
    ):
        order = Order(
            organization_id=store.organization_id,
            store_id=store.id,
            order_number="AUTO-001",
            total_amount=50000,
            currency="USD",
        )
        db.add(order)
        db.commit()

        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Note Test",
                "trigger_type": "manual",
                "actions_json": [
                    {
                        "type": "add_order_note",
                        "note": "Automation note",
                    }
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={
                "event_type": "manual",
                "payload": {"order_id": order.id},
            },
        )

        assert resp.status_code == 200

        db.refresh(order)
        assert order.note == "Automation note"

    def test_add_order_note_cross_store_blocked(
        self, client, store, store2, db
    ):
        other_order = Order(
            organization_id=store.organization_id,
            store_id=store2.id,
            order_number="OTHER-001",
            total_amount=50000,
            currency="COP",
        )
        db.add(other_order)
        db.commit()

        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Cross Store",
                "trigger_type": "manual",
                "actions_json": [
                    {
                        "type": "add_order_note",
                        "note": "Should not apply",
                    }
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={
                "event_type": "manual",
                "payload": {
                    "order_id": other_order.id,
                },
            },
        )

        assert resp.status_code == 200
        result = resp.json()["result_json"]
        assert any(
            a.get("status") == "skipped"
            for a in result.get("actions", [])
        )

    def test_add_order_note_wrong_org_blocked(
        self, client, store, db
    ):
        other_org = Organization(
            name="Other",
            slug="other-note-org",
            plan="starter",
            subscription_status="active",
        )
        db.add(other_org)
        db.flush()

        other_order = Order(
            organization_id=other_org.id,
            store_id=store.id,
            order_number="WRONG-ORG-001",
            total_amount=50000,
            currency="USD",
        )
        db.add(other_order)
        db.commit()

        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Cross Org",
                "trigger_type": "manual",
                "actions_json": [
                    {
                        "type": "add_order_note",
                        "note": "Cross org note",
                    }
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={
                "event_type": "manual",
                "payload": {
                    "order_id": other_order.id,
                },
            },
        )

        assert resp.status_code == 200
        result = resp.json()["result_json"]
        assert any(
            a.get("status") == "skipped"
            for a in result.get("actions", [])
        )

    def test_unknown_action_type_skipped(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Unknown Action",
                "trigger_type": "manual",
                "actions_json": [
                    {"type": "nonexistent_action"}
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={"event_type": "manual", "payload": {}},
        )

        assert resp.status_code == 200
        result = resp.json()["result_json"]
        assert result["actions"][0]["status"] == "skipped"

    def test_multiple_actions_executed(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Multi Action",
                "trigger_type": "manual",
                "actions_json": [
                    {"type": "log_event", "message": "First"},
                    {"type": "log_event", "message": "Second"},
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={"event_type": "manual", "payload": {}},
        )

        assert resp.status_code == 200
        result = resp.json()["result_json"]
        assert len(result["actions"]) == 2


# ============================================================
# EDGE CASE TESTS
# ============================================================


class TestAutomationEdgeCases:
    """Test edge cases and error handling."""

    def test_automation_with_description(
        self, client, store
    ):
        resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "With Desc",
                "description": "My description",
            },
        )

        assert resp.status_code == 200
        assert (
            resp.json()["description"]
            == "My description"
        )

    def test_automation_inactive_by_default_not_possible(
        self, client, store
    ):
        resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Inactive",
                "active": False,
            },
        )

        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_update_only_description(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "Update Desc"},
        )

        auto_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}",
            json={"description": "New description"},
        )

        assert resp.status_code == 200
        assert (
            resp.json()["description"]
            == "New description"
        )
        assert resp.json()["name"] == "Update Desc"

    def test_executions_empty_when_no_runs(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={"name": "No Runs"},
        )

        auto_id = create_resp.json()["id"]

        resp = client.get(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/executions"
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_executions_automation_not_found(
        self, client, store
    ):
        resp = client.get(
            f"/api/stores/{store.id}"
            f"/automations/99999/executions"
        )

        assert resp.status_code == 404

    def test_get_automation_not_found(
        self, client, store
    ):
        resp = client.get(
            f"/api/stores/{store.id}"
            f"/automations/99999"
        )

        assert resp.status_code == 404

    def test_update_automation_not_found(
        self, client, store
    ):
        resp = client.put(
            f"/api/stores/{store.id}"
            f"/automations/99999",
            json={"name": "x"},
        )

        assert resp.status_code == 404

    def test_delete_automation_not_found(
        self, client, store
    ):
        resp = client.delete(
            f"/api/stores/{store.id}"
            f"/automations/99999"
        )

        assert resp.status_code == 404

    def test_toggle_automation_not_found(
        self, client, store
    ):
        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/99999/toggle"
        )

        assert resp.status_code == 404

    def test_execution_result_contains_input(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Input Check",
                "trigger_type": "manual",
                "actions_json": [
                    {"type": "log_event", "message": "OK"}
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={
                "event_type": "manual",
                "payload": {"key": "value"},
            },
        )

        assert resp.status_code == 200
        assert resp.json()["input_json"]["key"] == "value"

    def test_execution_completed_at_populated(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Time Check",
                "trigger_type": "manual",
                "actions_json": [
                    {"type": "log_event", "message": "OK"}
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={"event_type": "manual", "payload": {}},
        )

        assert resp.status_code == 200
        assert resp.json()["completed_at"] is not None
        assert resp.json()["started_at"] is not None

    def test_last_execution_shown_in_list(
        self, client, store
    ):
        create_resp = client.post(
            f"/api/stores/{store.id}/automations",
            json={
                "name": "Last Exec",
                "trigger_type": "manual",
                "actions_json": [
                    {"type": "log_event", "message": "OK"}
                ],
            },
        )

        auto_id = create_resp.json()["id"]

        client.post(
            f"/api/stores/{store.id}"
            f"/automations/{auto_id}/run",
            json={"event_type": "manual", "payload": {}},
        )

        list_resp = client.get(
            f"/api/stores/{store.id}/automations"
        )

        items = list_resp.json()["items"]
        assert len(items) == 1
        assert items[0]["last_execution"] is not None
        assert (
            items[0]["last_execution"]["status"]
            == "success"
        )
