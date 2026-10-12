"""Block C: reject ambiguous automation graphs before publish/activate.

All tests use synthetic SQLite records. No real messages or calls are made.
"""
from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AutomationFlow, AutomationFlowVersion, Organization, Store
from app.automation_flow_graph import validate_graph
from app.services.automation_flows_service import (
    FlowValidationError, publish_version, activate_flow,
)


def _valid_graph():
    return {
        "nodes": [
            {"id": "trigger", "type": "trigger", "config": {"trigger_type": "manual"}},
            {"id": "wait", "type": "wait", "config": {"value": 1, "unit": "hours"}},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "trigger", "target": "wait"},
            {"source": "wait", "target": "end"},
        ],
    }


def test_linear_nodes_cannot_silently_discard_a_second_branch():
    graph = _valid_graph()
    graph["edges"].append({"source": "trigger", "target": "end"})
    assert any("exactly one outgoing edge" in e for e in validate_graph(graph))

    graph = _valid_graph()
    graph["edges"].append({"source": "wait", "target": "end"})
    assert any("exactly one outgoing edge" in e for e in validate_graph(graph))


def test_conditions_need_exactly_true_and_false_routes():
    graph = {
        "nodes": [
            {"id": "trigger", "type": "trigger", "config": {"trigger_type": "manual"}},
            {"id": "condition", "type": "condition", "config": {
                "field": "customer.order_count", "operator": "greater_than", "value": 0,
            }},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "trigger", "target": "condition"},
            {"source": "condition", "target": "end", "label": "true"},
        ],
    }
    assert any("true/false" in e for e in validate_graph(graph))
    graph["edges"].append({"source": "condition", "target": "end", "label": "false"})
    assert validate_graph(graph) == []
    graph["edges"].append({"source": "condition", "target": "end", "label": "unexpected"})
    assert any("exactly two labeled" in e for e in validate_graph(graph))


def test_trigger_cannot_have_incoming_and_end_cannot_have_outgoing():
    graph = _valid_graph()
    graph["edges"].append({"source": "end", "target": "trigger"})
    errors = validate_graph(graph)
    assert any("end must not have outgoing" in e for e in errors)
    assert any("trigger must not have incoming" in e for e in errors)


@pytest.fixture
def persisted():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Flow Guard Org", slug="flow-guard-org", active=True)
        db.add(org)
        db.flush()
        store = Store(
            organization_id=org.id, name="Flow Guard Store", slug="flow-guard-store",
            country_code="CO", currency="COP", timezone="America/Bogota",
            default_language="es", active=True, deleted=False,
        )
        db.add(store)
        db.flush()
        flow = AutomationFlow(
            organization_id=org.id, store_id=store.id, name="Synthetic Flow",
            status="draft",
        )
        db.add(flow)
        db.flush()
        version = AutomationFlowVersion(
            flow_id=flow.id, organization_id=org.id, version_number=1,
            graph=deepcopy(_valid_graph()),
        )
        db.add(version)
        db.flush()
        flow.current_version_id = version.id
        db.commit()
        yield db, org, store, flow, version
    engine.dispose()


def test_draft_with_legacy_ambiguous_graph_cannot_be_published(persisted):
    db, org, store, flow, ver = persisted
    graph = deepcopy(_valid_graph())
    graph["edges"].append({"source": "trigger", "target": "end"})
    ver.graph = graph
    db.commit()
    with pytest.raises(FlowValidationError):
        publish_version(db, org.id, store.id, flow.id, ver.id)
    db.refresh(ver)
    assert ver.published_at is None


def test_previous_published_invalid_graph_cannot_be_activated(persisted):
    db, org, store, flow, ver = persisted
    graph = deepcopy(_valid_graph())
    graph["edges"].append({"source": "trigger", "target": "end"})
    ver.graph = graph
    ver.published_at = datetime.utcnow()
    db.commit()
    with pytest.raises(FlowValidationError):
        activate_flow(db, org.id, store.id, flow.id)
    db.refresh(flow)
    db.refresh(ver)
    assert flow.status == "draft"
    assert flow.active_version_id is None
    assert ver.activated_at is None


def test_valid_graph_can_publish_and_activate_without_running_flows(persisted):
    db, org, store, flow, ver = persisted
    assert validate_graph(ver.graph) == []
    publish_version(db, org.id, store.id, flow.id, ver.id)
    activate_flow(db, org.id, store.id, flow.id)
    db.refresh(flow)
    db.refresh(ver)
    assert flow.status == "active"
    assert flow.active_version_id == ver.id
    assert ver.published_at and ver.activated_at
