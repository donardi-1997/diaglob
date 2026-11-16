"""Drafts are persistable, but never executable before full validation."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.automation_flow_graph import validate_draft_graph, validate_graph
from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import Organization, OrganizationMembership, Store, User
from app.services.automation_flows_service import create_flow


def _valid_graph():
    return {
        "nodes": [
            {"id": "start", "type": "trigger", "config": {"trigger_type": "manual"}},
            {"id": "done", "type": "end", "config": {}},
        ],
        "edges": [{"source": "start", "target": "done"}],
    }


def _incomplete_graph():
    return {
        "nodes": [
            {"id": "start", "type": "trigger", "config": {"trigger_type": "manual"}},
            {"id": "message", "type": "message", "config": {"message_mode": "auto", "message_template": ""}},
        ],
        "edges": [],
    }


@pytest.mark.parametrize("graph", [
    {"nodes": [], "edges": []},
    _incomplete_graph(),
    {"nodes": [{"id": "message", "type": "message", "config": {}}], "edges": []},
])
def test_safe_incomplete_draft_is_accepted_but_not_publishable(graph):
    assert validate_draft_graph(graph) == []
    assert validate_graph(graph)


@pytest.mark.parametrize("graph", [
    {"nodes": None, "edges": []},
    {"nodes": [{"id": "a", "type": "untrusted", "config": {}}], "edges": []},
    {"nodes": [{"id": "a", "type": "tool", "config": {"tool_name": "billing.refund"}}], "edges": []},
    {"nodes": [{"id": "a", "type": "end", "config": {}}, {"id": "a", "type": "end", "config": {}}], "edges": []},
    {"nodes": [{"id": "a", "type": "end", "config": {}}], "edges": [{"source": "a", "target": "missing"}]},
    {"nodes": [{"id": "a", "type": "end", "config": {}}], "edges": [{"source": "a", "target": "a"}]},
    {"nodes": [{"id": "a", "type": "end", "config": {}}], "edges": [], "extra": "x" * 129000},
    {"nodes": [{"id": "a", "type": [], "config": {}}], "edges": []},
    {"nodes": [{"id": "a", "type": "tool", "config": {"tool_name": []}}], "edges": []},
    {"nodes": [{"id": "a", "type": "end", "config": {}}], "edges": [{"source": [], "target": "a"}]},
])
def test_unsafe_or_malformed_draft_is_rejected(graph):
    assert validate_draft_graph(graph)


def test_version_lifecycle_api_enforces_draft_publish_activate_and_store_scope():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        org = Organization(name="Draft Org", slug="draft-org", plan="starter", subscription_status="active")
        session.add(org)
        session.flush()
        store = Store(organization_id=org.id, name="Draft Store", slug="draft-store",
                      country_code="CO", currency="COP", timezone="America/Bogota", default_language="es")
        session.add(store)
        session.flush()
        user = User(email="draft-flow@test.com", name="Draft Flow", external_auth_id="draft-flow-user")
        session.add(user)
        session.flush()
        membership = OrganizationMembership(user_id=user.id, organization_id=org.id, role="manager")
        session.add(membership)
        session.commit()
        created = create_flow(session, org.id, store.id, user.id, "Draft test", None, _valid_graph())
        flow_id = created["id"]
        base = f"/api/stores/{store.id}/automation-flows/{flow_id}"

        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_membership] = lambda: membership
        app.dependency_overrides[get_db] = lambda: session
        with TestClient(app) as client:
            saved = client.post(f"{base}/versions", json={"graph": _incomplete_graph()})
            assert saved.status_code == 200, saved.text
            draft_id = saved.json()["id"]
            retrieved = client.get(base)
            assert retrieved.status_code == 200
            assert retrieved.json()["current_version"]["graph"] == _incomplete_graph()

            assert client.post(f"{base}/versions/{draft_id}/publish").status_code == 422
            assert client.post(f"{base}/activate").status_code == 409

            complete = client.post(f"{base}/versions", json={"graph": _valid_graph()})
            assert complete.status_code == 200
            good_id = complete.json()["id"]
            assert client.post(f"{base}/versions/{draft_id}/publish").status_code == 409
            assert client.post(f"{base}/versions/{good_id}/publish").status_code == 200
            activated = client.post(f"{base}/activate")
            assert activated.status_code == 200
            assert activated.json()["status"] == "active"

            assert client.post(f"{base}/versions", json={"graph": _incomplete_graph()}).status_code == 409
            assert client.post(f"{base}/versions/{draft_id}/publish").status_code == 409
            assert client.post(f"/api/stores/{store.id + 999}/automation-flows/{flow_id}/versions",
                               json={"graph": _incomplete_graph()}).status_code == 404
    finally:
        app.dependency_overrides.clear()
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
