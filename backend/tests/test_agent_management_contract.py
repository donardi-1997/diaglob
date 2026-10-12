"""Synthetic, isolated AI Agents CRUD and tenant/store access tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_current_membership
from app.db import Base, get_db
from app.main import app
from app.models import (
    Organization, OrganizationMembership, Store, User,
)
from app.services.agent_management import (
    AgentAccessError,
    AgentNotFoundError,
    AgentValidationError,
    create_agent,
    list_agents,
    serialize_agent,
    update_agent,
)


@pytest.fixture
def context(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'agents_smoke.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    org = Organization(
        name="Organization A", slug="org-a",
        plan="starter", subscription_status="active",
    )
    foreign_org = Organization(
        name="Organization B", slug="org-b",
        plan="starter", subscription_status="active",
    )
    session.add_all([org, foreign_org])
    session.flush()

    def store(name, slug, organization):
        item = Store(
            name=name, slug=slug, organization_id=organization.id,
            country_code="CO", currency="COP",
            timezone="America/Bogota", default_language="es",
            active=True, deleted=False,
        )
        session.add(item)
        session.flush()
        return item

    a1 = store("A1", "a1", org)
    a2 = store("A2", "a2", org)
    b1 = store("B1", "b1", foreign_org)
    manager_user = User(
        name="Manager", email="manager@synthetic.test",
        external_auth_id="manager-agent-smoke",
    )
    owner_user = User(
        name="Owner", email="owner@synthetic.test",
        external_auth_id="owner-agent-smoke",
    )
    analyst_user = User(
        name="Analyst", email="analyst@synthetic.test",
        external_auth_id="analyst-agent-smoke",
    )
    session.add_all([manager_user, owner_user, analyst_user])
    session.flush()
    manager = OrganizationMembership(
        user_id=manager_user.id, organization_id=org.id,
        role="manager", all_stores=False, active=True,
    )
    owner = OrganizationMembership(
        user_id=owner_user.id, organization_id=org.id,
        role="owner", all_stores=True, active=True,
    )
    analyst = OrganizationMembership(
        user_id=analyst_user.id, organization_id=org.id,
        role="analyst", all_stores=False, active=True,
    )
    manager.stores = [a1]
    analyst.stores = [a1]
    session.add_all([manager, owner, analyst])
    session.commit()
    yield session, org, a1, a2, b1, manager, owner, analyst
    session.close()
    engine.dispose()


def _create(db, membership, stores):
    return create_agent(
        db, membership,
        name="Sales AI", role="sales", active=True,
        store_ids=stores, knowledge_base_ids=[],
    )


def test_agents_reject_cross_tenant_unassigned_and_active_without_stores(context):
    db, _, a1, a2, b1, manager, owner, _ = context

    with pytest.raises(AgentAccessError):
        _create(db, manager, [a2.id])
    with pytest.raises(AgentAccessError):
        _create(db, manager, [b1.id])
    with pytest.raises(AgentValidationError):
        _create(db, owner, [])
    with pytest.raises(AgentValidationError):
        _create(db, owner, [a1.id, a1.id])

    agent = _create(db, manager, [a1.id])
    assert [store.id for store in agent.stores] == [a1.id]
    assert agent.organization_id == manager.organization_id


def test_agents_visibility_and_restricted_updates_never_leak_store_names(context):
    db, _, a1, a2, _, manager, owner, _ = context
    mixed = _create(db, owner, [a1.id, a2.id])
    hidden = _create(db, owner, [a2.id])
    visible = list_agents(db, manager)

    assert [agent.id for agent in visible] == [mixed.id]
    serialized = serialize_agent(mixed, manager)
    assert [store["id"] for store in serialized["stores"]] == [a1.id]
    assert "A2" not in str(serialized)

    with pytest.raises(AgentAccessError):
        update_agent(db, manager, mixed.id, updates={"name": "Changed"})
    with pytest.raises(AgentNotFoundError):
        update_agent(db, manager, hidden.id, updates={"active": False})
    assert mixed.name == "Sales AI"

    changed = update_agent(db, owner, hidden.id, updates={"active": False})
    assert changed.active is False
    changed = update_agent(
        db, owner, hidden.id,
        updates={"active": True, "store_ids": [a1.id]},
    )
    assert changed.active is True
    assert [store.id for store in changed.stores] == [a1.id]


def test_agent_router_exposes_real_crud_and_enforces_permissions(context):
    db, org, a1, a2, _, manager, owner, analyst = context
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_membership] = lambda: manager
    try:
        with TestClient(app) as client:
            response = client.get("/api/agents")
            assert response.status_code == 200
            assert response.json() == {"items": [], "total": 0}
            created = client.post(
                "/api/agents",
                json={
                    "name": "Sales", "role": "sales", "active": True,
                    "store_ids": [a1.id], "knowledge_base_ids": [],
                },
            )
            assert created.status_code == 200
            agent_id = created.json()["id"]
            assert created.json()["organization_id"] == org.id
            updated = client.patch(
                f"/api/agents/{agent_id}",
                json={"name": "Sales Updated"},
            )
            assert updated.status_code == 200
            assert updated.json()["name"] == "Sales Updated"

            forbidden = client.patch(
                f"/api/agents/{agent_id}",
                json={"store_ids": [a2.id]},
            )
            assert forbidden.status_code == 403

            app.dependency_overrides[get_current_membership] = lambda: analyst
            assert client.get("/api/agents").status_code == 403
            assert client.post(
                "/api/agents", json={
                    "name": "No", "role": "sales", "store_ids": [a1.id],
                },
            ).status_code == 403
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
