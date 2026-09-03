"""V2.2 Flow Builder tests — graph validation, execution, versioning, API."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

from app.automation_flow_graph import validate_graph, get_next_node, get_entry_node, _is_dag
from app.automation_flow_engine import (
    materialize_flow_trigger, claim_flow_recipients, reclaim_expired_flow_leases,
    process_flow_recipient, aggregate_flow_runs, utcnow, _evaluate_condition,
)
from app.db import Base, get_db
from app.main import app, get_current_user, get_current_membership
from app.models import (
    AutomationFlow, AutomationFlowVersion, AutomationFlowRun,
    AutomationFlowRecipientExecution, AutomationNodeExecution,
    AutomationRateLimit, Customer, Organization, OrganizationMembership,
    CustomerStoreProfile, Store, User, WhatsAppConnection,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    org = Organization(name="Flow Org", slug="flow-org", plan="starter", subscription_status="active")
    session.add(org)
    session.flush()
    store = Store(organization_id=org.id, name="Flow Store", slug="flow-store",
                  country_code="CO", currency="COP", timezone="America/Bogota",
                  default_language="es")
    session.add(store)
    session.flush()
    yield session, org, store
    session.close()
    Base.metadata.drop_all(engine)


def _make_graph(trigger_type="manual", wait_value=1, wait_unit="hours",
                message_template="Hola {{name}}", message_mode="free_form",
                include_condition=False):
    nodes = [
        {"id": "trigger", "type": "trigger", "config": {"trigger_type": trigger_type}},
    ]
    edges = []
    prev = "trigger"
    if include_condition:
        cond_id = "cond1"
        nodes.append({"id": cond_id, "type": "condition", "config": {
            "field": "customer.order_count", "operator": "greater_than", "value": 5,
        }})
        edges.append({"source": prev, "target": cond_id})
        nodes.append({"id": "msg_yes", "type": "message", "config": {
            "message_mode": message_mode, "message_template": message_template,
        }})
        edges.append({"source": cond_id, "target": "msg_yes", "label": "true"})
        nodes.append({"id": "msg_no", "type": "message", "config": {
            "message_mode": message_mode, "message_template": "Default msg",
        }})
        edges.append({"source": cond_id, "target": "msg_no", "label": "false"})
        edges.append({"source": "msg_yes", "target": "end"})
        edges.append({"source": "msg_no", "target": "end"})
        nodes.append({"id": "end", "type": "end", "config": {}})
    else:
        wait_id = "wait1"
        nodes.append({"id": wait_id, "type": "wait", "config": {"value": wait_value, "unit": wait_unit}})
        edges.append({"source": prev, "target": wait_id})
        msg_id = "msg1"
        nodes.append({"id": msg_id, "type": "message", "config": {
            "message_mode": message_mode, "message_template": message_template,
        }})
        edges.append({"source": wait_id, "target": msg_id})
        nodes.append({"id": "end", "type": "end", "config": {}})
        edges.append({"source": msg_id, "target": "end"})
    return {"nodes": nodes, "edges": edges}


# ═══════════════════════════════════════════════════════════════
# GRAPH VALIDATION
# ═══════════════════════════════════════════════════════════════

class TestGraphValidation:
    def test_valid_simple_flow(self):
        errors = validate_graph(_make_graph())
        assert errors == []

    def test_valid_condition_flow(self):
        errors = validate_graph(_make_graph(include_condition=True))
        assert errors == []

    def test_empty_graph(self):
        errors = validate_graph({"nodes": [], "edges": []})
        assert any("at least one node" in e for e in errors)

    def test_no_trigger(self):
        errors = validate_graph({"nodes": [{"id": "a", "type": "end", "config": {}}], "edges": []})
        assert any("exactly one trigger" in e for e in errors)

    def test_two_triggers(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t1", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "t2", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t1", "target": "e"}, {"source": "t2", "target": "e"}],
        })
        assert any("exactly one trigger" in e for e in errors)

    def test_no_end(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "m", "type": "message", "config": {"message_mode": "free_form", "message_template": "hi"}},
            ],
            "edges": [{"source": "t", "target": "m"}],
        })
        assert any("at least one end node" in e for e in errors)

    def test_duplicate_node_ids(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "t", "type": "end", "config": {}},
            ],
            "edges": [],
        })
        assert any("Duplicate node IDs" in e for e in errors)

    def test_invalid_trigger_type(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "invalid"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t", "target": "e"}],
        })
        assert any("invalid trigger_type" in e for e in errors)

    def test_invalid_wait_unit(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "w", "type": "wait", "config": {"value": 1, "unit": "years"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t", "target": "w"}, {"source": "w", "target": "e"}],
        })
        assert any("invalid wait unit" in e for e in errors)

    def test_wait_value_too_large(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "w", "type": "wait", "config": {"value": 400, "unit": "days"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t", "target": "w"}, {"source": "w", "target": "e"}],
        })
        assert any("exceeds maximum" in e for e in errors)

    def test_invalid_message_mode(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "m", "type": "message", "config": {"message_mode": "sms", "message_template": "hi"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t", "target": "m"}, {"source": "m", "target": "e"}],
        })
        assert any("invalid message_mode" in e for e in errors)

    def test_message_no_template(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "m", "type": "message", "config": {"message_mode": "free_form", "message_template": ""}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t", "target": "m"}, {"source": "m", "target": "e"}],
        })
        assert any("message_template is required" in e for e in errors)

    def test_condition_no_branches(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "c", "type": "condition", "config": {"field": "customer.order_count", "operator": "greater_than", "value": 0}},
                {"id": "m", "type": "message", "config": {"message_mode": "free_form", "message_template": "hi"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t", "target": "c"}, {"source": "c", "target": "m"}, {"source": "m", "target": "e"}],
        })
        assert any("true/false branches" in e for e in errors)

    def test_orphan_nodes(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "e", "type": "end", "config": {}},
                {"id": "orphan", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t", "target": "e"}],
        })
        assert any("Orphan nodes" in e for e in errors)

    def test_self_loop(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t", "target": "t"}, {"source": "t", "target": "e"}],
        })
        assert any("Self-loop" in e for e in errors)

    def test_cycle_detection(self):
        errors = validate_graph({
            "nodes": [
                {"id": "a", "type": "wait", "config": {"value": 1, "unit": "hours"}},
                {"id": "b", "type": "message", "config": {"message_mode": "free_form", "message_template": "hi"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "b", "target": "a"},
            ],
        })
        assert any("cycle" in e.lower() for e in errors)

    def test_unknown_source_edge(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "missing", "target": "e"}],
        })
        assert any("unknown source" in e for e in errors)

    def test_unknown_target_edge(self):
        errors = validate_graph({
            "nodes": [
                {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}},
                {"id": "e", "type": "end", "config": {}},
            ],
            "edges": [{"source": "t", "target": "missing"}],
        })
        assert any("unknown target" in e for e in errors)

    def test_exceeds_max_nodes(self):
        nodes = [{"id": f"n{i}", "type": "end", "config": {}} for i in range(60)]
        nodes[0] = {"id": "t", "type": "trigger", "config": {"trigger_type": "manual"}}
        errors = validate_graph({"nodes": nodes, "edges": []})
        assert any("exceeds maximum" in e for e in errors)


class TestGraphHelpers:
    def test_get_entry_node(self):
        graph = _make_graph()
        entry = get_entry_node(graph)
        assert entry is not None
        assert entry["type"] == "trigger"

    def test_get_next_node_simple(self):
        graph = _make_graph()
        nxt = get_next_node(graph, "trigger")
        assert nxt is not None
        assert nxt["id"] == "wait1"

    def test_get_next_node_condition_true(self):
        graph = _make_graph(include_condition=True)
        nxt = get_next_node(graph, "cond1", "true")
        assert nxt is not None
        assert nxt["id"] == "msg_yes"

    def test_get_next_node_condition_false(self):
        graph = _make_graph(include_condition=True)
        nxt = get_next_node(graph, "cond1", "false")
        assert nxt is not None
        assert nxt["id"] == "msg_no"

    def test_evaluate_condition_equals(self):
        assert _evaluate_condition("vip", "equals", "vip")
        assert not _evaluate_condition("vip", "equals", "regular")

    def test_evaluate_condition_greater_than(self):
        assert _evaluate_condition(10, "greater_than", 5)
        assert not _evaluate_condition(3, "greater_than", 5)

    def test_evaluate_condition_in_list(self):
        assert _evaluate_condition("vip", "in", ["vip", "premium"])
        assert not _evaluate_condition("regular", "in", ["vip", "premium"])

    def test_evaluate_condition_is_true(self):
        assert _evaluate_condition(True, "is_true", None)
        assert not _evaluate_condition(False, "is_true", None)

    def test_is_dag_valid(self):
        assert _is_dag(
            [{"id": "a"}, {"id": "b"}],
            [{"source": "a", "target": "b"}],
        )

    def test_is_dag_cycle(self):
        assert not _is_dag(
            [{"id": "a"}, {"id": "b"}],
            [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
        )


# ═══════════════════════════════════════════════════════════════
# FLOW CRUD + VERSIONING API
# ═══════════════════════════════════════════════════════════════

def _user_and_membership(db, org, store):
    user = User(email="flow@test.com", name="Flow Test", external_auth_id="flow-cognito-sub")
    db.add(user)
    db.flush()
    mem = OrganizationMembership(user_id=user.id, organization_id=org.id, role="manager")
    db.add(mem)
    db.flush()
    return user, mem


def _mock_auth(user, membership):
    def _get_user():
        return user
    def _get_membership():
        return membership
    return _get_user, _get_membership


class TestFlowCRUD:
    def test_create_flow_empty(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "My Flow"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == "My Flow"
            assert data["status"] == "draft"
        finally:
            app.dependency_overrides.clear()

    def test_create_flow_with_valid_graph(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            graph = _make_graph()
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "Valid Flow", "graph": graph})
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_version_id"] is not None
        finally:
            app.dependency_overrides.clear()

    def test_create_flow_with_invalid_graph(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "Bad Flow", "graph": {"nodes": [], "edges": []}})
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_create_flow_rejects_store_from_other_organization(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        other_org = Organization(name="Other Org", slug="other-org")
        session.add(other_org)
        session.flush()
        other_store = Store(
            organization_id=other_org.id, name="Other Store",
            slug="other-store", country_code="CO", currency="COP",
            timezone="America/Bogota", default_language="es",
        )
        session.add(other_store)
        session.commit()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            response = client.post(
                f"/api/stores/{other_store.id}/automation-flows",
                json={"name": "Invalid Flow"},
            )
            assert response.status_code == 404
            assert session.query(AutomationFlow).filter(
                AutomationFlow.store_id == other_store.id,
            ).count() == 0
        finally:
            app.dependency_overrides.clear()

    def test_list_flows(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F1"})
            client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F2"})
            resp = client.get(f"/api/stores/{store.id}/automation-flows")
            assert resp.status_code == 200
            assert len(resp.json()) == 2
        finally:
            app.dependency_overrides.clear()

    def test_get_flow_with_version(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            graph = _make_graph()
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F", "graph": graph})
            flow_id = resp.json()["id"]
            resp = client.get(f"/api/stores/{store.id}/automation-flows/{flow_id}")
            assert resp.status_code == 200
            assert "current_version" in resp.json()
        finally:
            app.dependency_overrides.clear()

    def test_update_flow_name(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "Old"})
            fid = resp.json()["id"]
            resp = client.put(f"/api/stores/{store.id}/automation-flows/{fid}", json={"name": "New"})
            assert resp.status_code == 200
            assert resp.json()["name"] == "New"
        finally:
            app.dependency_overrides.clear()

    def test_update_flow_creates_new_version(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F", "graph": _make_graph()})
            fid = resp.json()["id"]
            resp = client.put(f"/api/stores/{store.id}/automation-flows/{fid}", json={"graph": _make_graph(wait_value=2)})
            assert resp.status_code == 200
            resp = client.get(f"/api/stores/{store.id}/automation-flows/{fid}/versions")
            assert len(resp.json()) == 2
        finally:
            app.dependency_overrides.clear()

    def test_cannot_edit_active_flow(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F", "graph": _make_graph()})
            fid = resp.json()["id"]
            vid = resp.json()["current_version_id"]
            client.post(f"/api/stores/{store.id}/automation-flows/{fid}/versions/{vid}/publish")
            client.post(f"/api/stores/{store.id}/automation-flows/{fid}/activate")
            resp = client.put(f"/api/stores/{store.id}/automation-flows/{fid}", json={"name": "X"})
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()

    def test_archive_flow(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F"})
            fid = resp.json()["id"]
            resp = client.delete(f"/api/stores/{store.id}/automation-flows/{fid}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "archived"
        finally:
            app.dependency_overrides.clear()

    def test_publish_version(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F", "graph": _make_graph()})
            fid, vid = resp.json()["id"], resp.json()["current_version_id"]
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{fid}/versions/{vid}/publish")
            assert resp.status_code == 200
            assert resp.json()["published_at"] is not None
        finally:
            app.dependency_overrides.clear()

    def test_cannot_publish_twice(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F", "graph": _make_graph()})
            fid, vid = resp.json()["id"], resp.json()["current_version_id"]
            client.post(f"/api/stores/{store.id}/automation-flows/{fid}/versions/{vid}/publish")
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{fid}/versions/{vid}/publish")
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()

    def test_activate_flow(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F", "graph": _make_graph()})
            fid, vid = resp.json()["id"], resp.json()["current_version_id"]
            client.post(f"/api/stores/{store.id}/automation-flows/{fid}/versions/{vid}/publish")
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{fid}/activate")
            assert resp.status_code == 200
            assert resp.json()["status"] == "active"
        finally:
            app.dependency_overrides.clear()

    def test_deactivate_flow(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F", "graph": _make_graph()})
            fid, vid = resp.json()["id"], resp.json()["current_version_id"]
            client.post(f"/api/stores/{store.id}/automation-flows/{fid}/versions/{vid}/publish")
            client.post(f"/api/stores/{store.id}/automation-flows/{fid}/activate")
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{fid}/deactivate")
            assert resp.status_code == 200
            assert resp.json()["status"] == "draft"
        finally:
            app.dependency_overrides.clear()

    def test_list_versions(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows", json={"name": "F", "graph": _make_graph()})
            fid = resp.json()["id"]
            client.put(f"/api/stores/{store.id}/automation-flows/{fid}", json={"graph": _make_graph(wait_value=2)})
            resp = client.get(f"/api/stores/{store.id}/automation-flows/{fid}/versions")
            assert len(resp.json()) == 2
        finally:
            app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════
# FLOW EXECUTION ENGINE
# ═══════════════════════════════════════════════════════════════

class TestFlowExecution:
    def _active_flow(self, db):
        session, org, store = db
        user, _ = _user_and_membership(session, org, store)
        flow = AutomationFlow(
            organization_id=org.id, store_id=store.id,
            name="Test Flow", status="draft", created_by=user.id,
        )
        session.add(flow)
        session.flush()
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=org.id,
            version_number=1, graph=_make_graph(),
        )
        session.add(ver)
        session.flush()
        flow.current_version_id = ver.id
        ver.published_at = utcnow()
        ver.activated_at = utcnow()
        flow.active_version_id = ver.id
        flow.status = "active"
        session.commit()
        return flow, ver

    def _customer(self, db, name="Test", phone="+573001234567"):
        session, org, store = db
        c = Customer(organization_id=org.id, name=name, phone=phone)
        session.add(c)
        session.flush()
        session.add(CustomerStoreProfile(
            organization_id=org.id, customer_id=c.id, store_id=store.id,
            currency=store.currency,
        ))
        session.flush()
        return c

    def _process_claimed(self, session, recipient_id, **kwargs):
        recipient = session.get(AutomationFlowRecipientExecution, recipient_id)
        return process_flow_recipient(
            session, recipient_id, claim_token=recipient.claim_token, **kwargs,
        )

    def test_materialize_trigger(self, db):
        flow, ver = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        run = materialize_flow_trigger(session, flow, [c.id], trigger_key="test-1")
        assert run is not None
        assert run.total_recipients == 1
        recip = session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id
        ).first()
        assert recip is not None
        assert recip.status == "active"

    def test_materialize_idempotent(self, db):
        flow, ver = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        r1 = materialize_flow_trigger(session, flow, [c.id], trigger_key="idem-1")
        r2 = materialize_flow_trigger(session, flow, [c.id], trigger_key="idem-1")
        assert r2 is None

    def test_materialize_inactive_flow(self, db):
        session, org, store = db
        flow = AutomationFlow(
            organization_id=org.id, store_id=store.id,
            name="X", status="draft",
        )
        session.add(flow)
        session.flush()
        result = materialize_flow_trigger(session, flow, [])
        assert result is None

    def test_claim_and_process(self, db):
        flow, ver = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        run = materialize_flow_trigger(session, flow, [c.id])
        ids = claim_flow_recipients(session)
        assert len(ids) > 0
        result = self._process_claimed(session, ids[0])
        assert result in ("waiting", "completed", "advanced", "sent")

    def test_two_claim_attempts_only_one_gets_due_recipient(self, db):
        flow, ver = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        materialize_flow_trigger(session, flow, [c.id])
        first = claim_flow_recipients(session, include_tokens=True)
        second = claim_flow_recipients(session, include_tokens=True)
        assert len(first) == 1
        assert second == []

    def test_stale_claim_token_cannot_process(self, db):
        flow, ver = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        materialize_flow_trigger(session, flow, [c.id])
        first = claim_flow_recipients(session, include_tokens=True)
        recipient_id, token_a = first[0]
        session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.id == recipient_id
        ).update({"claim_token": "token-b"})
        session.commit()
        calls = []
        result = process_flow_recipient(
            session, recipient_id, claim_token=token_a,
            sender=lambda *args: calls.append(args),
        )
        recipient = session.get(AutomationFlowRecipientExecution, recipient_id)
        assert result == "not_claimed"
        assert calls == []
        assert recipient.attempt_count == 0
        assert session.query(AutomationNodeExecution).filter(
            AutomationNodeExecution.flow_recipient_execution_id == recipient_id
        ).count() == 0

    def test_wait_node(self, db):
        flow, ver = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        run = materialize_flow_trigger(session, flow, [c.id])
        ids = claim_flow_recipients(session)
        result = self._process_claimed(session, ids[0])
        assert result == "waiting"
        recip = session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id
        ).first()
        assert recip.status == "waiting"
        assert recip.next_action_at > utcnow()

    def test_reclaim_expired_leases(self, db):
        flow, ver = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        run = materialize_flow_trigger(session, flow, [c.id])
        claim_flow_recipients(session)
        now = utcnow()
        session.query(AutomationFlowRecipientExecution).update({
            "claim_expires_at": now - timedelta(seconds=1),
            "status": "waiting",
        })
        session.commit()
        reclaim_expired_flow_leases(session)
        recip = session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id
        ).first()
        assert recip.status == "active"
        assert recip.claim_token is None

    def test_aggregate_flow_runs(self, db):
        flow, ver = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        run = materialize_flow_trigger(session, flow, [c.id])
        session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id
        ).update({"status": "completed", "completed_at": utcnow()})
        run.completed_recipients = run.total_recipients
        session.commit()
        aggregate_flow_runs(session)
        run = session.get(AutomationFlowRun, run.id)
        assert run.status == "completed"
        assert run.completed_at is not None

    def test_condition_node_true_branch(self, db):
        session, org, store = db
        c = self._customer(db)
        c.primary_segment = "vip"
        c.orders_count = 10
        session.commit()
        flow = AutomationFlow(
            organization_id=org.id, store_id=store.id,
            name="Cond Flow", status="draft",
        )
        session.add(flow)
        session.flush()
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=org.id,
            version_number=1, graph=_make_graph(include_condition=True),
        )
        session.add(ver)
        session.flush()
        ver.published_at = utcnow()
        ver.activated_at = utcnow()
        flow.current_version_id = ver.id
        flow.active_version_id = ver.id
        flow.status = "active"
        session.commit()
        run = materialize_flow_trigger(session, flow, [c.id])
        ids = claim_flow_recipients(session)
        result = self._process_claimed(session, ids[0])
        assert result in ("advanced", "sent")
        recip = session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id
        ).first()
        assert recip.current_node_id == "msg_yes"

    def test_condition_node_false_branch(self, db):
        session, org, store = db
        c = self._customer(db)
        c.orders_count = 0
        session.commit()
        flow = AutomationFlow(
            organization_id=org.id, store_id=store.id,
            name="Cond Flow", status="draft",
        )
        session.add(flow)
        session.flush()
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=org.id,
            version_number=1, graph=_make_graph(include_condition=True),
        )
        session.add(ver)
        session.flush()
        ver.published_at = utcnow()
        ver.activated_at = utcnow()
        flow.current_version_id = ver.id
        flow.active_version_id = ver.id
        flow.status = "active"
        session.commit()
        run = materialize_flow_trigger(session, flow, [c.id])
        ids = claim_flow_recipients(session)
        result = self._process_claimed(session, ids[0])
        assert result in ("advanced", "sent")
        recip = session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id
        ).first()
        assert recip.current_node_id == "msg_no"

    def test_message_no_phone_fails(self, db):
        session, org, store = db
        c = self._customer(db, phone="")
        flow = AutomationFlow(
            organization_id=org.id, store_id=store.id,
            name="No Phone Flow", status="draft",
        )
        session.add(flow)
        session.flush()
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=org.id,
            version_number=1, graph=_make_graph(),
        )
        session.add(ver)
        session.flush()
        ver.published_at = utcnow()
        ver.activated_at = utcnow()
        flow.current_version_id = ver.id
        flow.active_version_id = ver.id
        flow.status = "active"
        session.commit()
        run = materialize_flow_trigger(session, flow, [c.id])
        ids = claim_flow_recipients(session)
        session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.id.in_(ids)
        ).update({"current_node_id": "msg1"})
        session.commit()
        result = self._process_claimed(session, ids[0])
        assert result == "failed"

    def test_process_nonexistent_recipient(self, db):
        session, org, store = db
        result = process_flow_recipient(session, 999999)
        assert result == "not_claimed"

    def test_process_completed_recipient(self, db):
        flow, ver = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        run = materialize_flow_trigger(session, flow, [c.id])
        claim_flow_recipients(session)
        session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id
        ).update({"status": "completed"})
        session.commit()
        recip = session.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id
        ).first()
        result = process_flow_recipient(session, recip.id)
        assert result == "not_claimed"


# ═══════════════════════════════════════════════════════════════
# FLOW SIMULATION API
# ═══════════════════════════════════════════════════════════════

class TestFlowSimulation:
    def test_simulate_valid(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows/simulate", json={
                "name": "S", "graph": _make_graph(),
            })
            assert resp.status_code == 200
            assert resp.json()["valid"] is True
        finally:
            app.dependency_overrides.clear()

    def test_simulate_invalid(self, db):
        session, org, store = db
        user, mem = _user_and_membership(session, org, store)
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows/simulate", json={
                "name": "S", "graph": {"nodes": [], "edges": []},
            })
            assert resp.status_code == 200
            assert resp.json()["valid"] is False
        finally:
            app.dependency_overrides.clear()


# ═══════════════════════════════════════════════════════════════
# FLOW TRIGGER + RECIPIENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════

class TestFlowTriggerEndpoints:
    def _customer(self, db, name="C1", phone="+573001234567"):
        session, org, store = db
        customer = Customer(organization_id=org.id, name=name, phone=phone)
        session.add(customer)
        session.flush()
        session.add(CustomerStoreProfile(
            organization_id=org.id, customer_id=customer.id,
            store_id=store.id, currency=store.currency,
        ))
        session.flush()
        return customer

    def _active_flow(self, db):
        session, org, store = db
        user, _ = _user_and_membership(session, org, store)
        flow = AutomationFlow(
            organization_id=org.id, store_id=store.id,
            name="Trigger Flow", status="draft", created_by=user.id,
        )
        session.add(flow)
        session.flush()
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=org.id,
            version_number=1, graph=_make_graph(),
        )
        session.add(ver)
        session.flush()
        ver.published_at = utcnow()
        ver.activated_at = utcnow()
        flow.current_version_id = ver.id
        flow.active_version_id = ver.id
        flow.status = "active"
        session.commit()
        return flow, ver, user

    def test_trigger_run(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        c = self._customer(db, name="C1")
        session.commit()
        mem = session.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs", json={
                "customer_ids": [c.id],
            })
            assert resp.status_code == 200
            assert resp.json()["total_recipients"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_trigger_missing_customer(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        mem = session.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs", json={
                "customer_ids": [999999],
            })
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_trigger_rejects_customer_from_other_store(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        other_store = Store(
            organization_id=org.id, name="Other Store",
            slug="other-store", country_code="CO", currency="COP",
            timezone="America/Bogota", default_language="es",
        )
        session.add(other_store)
        session.flush()
        customer = Customer(
            organization_id=org.id, name="Other Store Customer",
            phone="+573001234567",
        )
        session.add(customer)
        session.flush()
        session.add(CustomerStoreProfile(
            organization_id=org.id, customer_id=customer.id,
            store_id=other_store.id, currency=other_store.currency,
        ))
        session.commit()
        mem = session.query(OrganizationMembership).filter(
            OrganizationMembership.user_id == user.id,
        ).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            response = client.post(
                f"/api/stores/{store.id}/automation-flows/{flow.id}/runs",
                json={"customer_ids": [customer.id]},
            )
            assert response.status_code == 422
            assert session.query(AutomationFlowRun).filter(
                AutomationFlowRun.flow_id == flow.id,
            ).count() == 0
        finally:
            app.dependency_overrides.clear()

    def test_trigger_rejects_customer_from_other_organization(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        other_org = Organization(name="Other Org", slug="other-org")
        session.add(other_org)
        session.flush()
        customer = Customer(
            organization_id=other_org.id, name="Other Org Customer",
            phone="+573001234567",
        )
        session.add(customer)
        session.commit()
        mem = session.query(OrganizationMembership).filter(
            OrganizationMembership.user_id == user.id,
        ).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            response = client.post(
                f"/api/stores/{store.id}/automation-flows/{flow.id}/runs",
                json={"customer_ids": [customer.id]},
            )
            assert response.status_code == 422
            assert session.query(AutomationFlowRun).filter(
                AutomationFlowRun.flow_id == flow.id,
            ).count() == 0
        finally:
            app.dependency_overrides.clear()

    def test_trigger_duplicate_key(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        c = self._customer(db, name="C1")
        session.commit()
        mem = session.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs", json={
                "customer_ids": [c.id], "trigger_key": "dup-1",
            })
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs", json={
                "customer_ids": [c.id], "trigger_key": "dup-1",
            })
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.clear()

    def test_list_runs(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        c = self._customer(db, name="C1")
        session.commit()
        mem = session.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs", json={"customer_ids": [c.id]})
            resp = client.get(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs")
            assert resp.status_code == 200
            assert len(resp.json()) == 1
        finally:
            app.dependency_overrides.clear()

    def test_get_run_detail(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        c = self._customer(db, name="C1")
        session.commit()
        mem = session.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs", json={"customer_ids": [c.id]})
            run_id = resp.json()["id"]
            resp = client.get(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs/{run_id}")
            assert resp.status_code == 200
            assert "recipients" in resp.json()
        finally:
            app.dependency_overrides.clear()

    def test_list_recipients(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        c = self._customer(db, name="C1")
        session.commit()
        mem = session.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs", json={"customer_ids": [c.id]})
            run_id = resp.json()["id"]
            resp = client.get(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs/{run_id}/recipients")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1
        finally:
            app.dependency_overrides.clear()

    def test_get_recipient_detail(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        c = self._customer(db, name="C1")
        session.commit()
        mem = session.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs", json={"customer_ids": [c.id]})
            run_id = resp.json()["id"]
            resp = client.get(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs/{run_id}/recipients")
            recip_id = resp.json()["items"][0]["id"]
            resp = client.get(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs/{run_id}/recipients/{recip_id}")
            assert resp.status_code == 200
            assert "node_executions" in resp.json()
        finally:
            app.dependency_overrides.clear()

    def test_retry_recipient(self, db):
        flow, ver, user = self._active_flow(db)
        session, org, store = db
        c = self._customer(db)
        session.commit()
        mem = session.query(OrganizationMembership).filter(OrganizationMembership.user_id == user.id).first()
        client = TestClient(app)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: mem
        app.dependency_overrides[get_db] = lambda: session
        try:
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs", json={"customer_ids": [c.id]})
            run_id = resp.json()["id"]
            resp = client.get(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs/{run_id}/recipients")
            recip_id = resp.json()["items"][0]["id"]
            session.query(AutomationFlowRecipientExecution).filter(
                AutomationFlowRecipientExecution.id == recip_id
            ).update({"status": "failed", "error_code": "test"})
            session.commit()
            resp = client.post(f"/api/stores/{store.id}/automation-flows/{flow.id}/runs/{run_id}/recipients/{recip_id}/retry")
            assert resp.status_code == 200
            assert resp.json()["status"] == "active"
        finally:
            app.dependency_overrides.clear()
