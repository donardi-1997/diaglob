"""Voice call node tests for the durable Flow Builder."""
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.automation_flow_engine import (
    claim_flow_recipients,
    complete_voice_call,
    materialize_flow_trigger,
    process_flow_recipient,
    utcnow,
)
from app.automation_flow_graph import validate_graph
from app.db import Base
from app.models import (
    AutomationFlow,
    AutomationFlowRecipientExecution,
    AutomationFlowVersion,
    AutomationNodeExecution,
    Customer,
    CustomerStoreProfile,
    Organization,
    Store,
)


def _call_graph(timeout_minutes=5):
    return {
        "nodes": [
            {
                "id": "trigger",
                "type": "trigger",
                "config": {"trigger_type": "order_created"},
            },
            {
                "id": "call",
                "type": "call",
                "config": {
                    "call_prompt": "Hola {{customer.name}}, confirma tu pedido de {{store.name}}.",
                    "call_language": "es",
                    "timeout_minutes": timeout_minutes,
                },
            },
            {"id": "confirmed", "type": "end", "config": {}},
            {"id": "rejected", "type": "end", "config": {}},
            {"id": "no_answer", "type": "end", "config": {}},
            {"id": "failed", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "trigger", "target": "call"},
            {"source": "call", "target": "confirmed", "label": "confirmed"},
            {"source": "call", "target": "rejected", "label": "rejected"},
            {"source": "call", "target": "no_answer", "label": "no_answer"},
            {"source": "call", "target": "failed", "label": "failed"},
        ],
    }


def _setup():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    org = Organization(
        name="Voice Org",
        slug="voice-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    session.add(org)
    session.flush()
    store = Store(
        organization_id=org.id,
        name="Tienda Voice",
        slug="voice-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
        deleted=False,
    )
    session.add(store)
    session.flush()
    customer = Customer(
        organization_id=org.id,
        name="Ana",
        phone="+573001112233",
        country_code="CO",
    )
    session.add(customer)
    session.flush()
    session.add(
        CustomerStoreProfile(
            organization_id=org.id,
            customer_id=customer.id,
            store_id=store.id,
            currency="COP",
        )
    )
    session.flush()
    return engine, session, org, store, customer


def _activate_flow(session, org, store, graph):
    flow = AutomationFlow(
        organization_id=org.id,
        store_id=store.id,
        name="Voice confirmation",
        status="active",
    )
    session.add(flow)
    session.flush()
    version = AutomationFlowVersion(
        flow_id=flow.id,
        organization_id=org.id,
        version_number=1,
        graph=graph,
        published_at=utcnow(),
        activated_at=utcnow(),
    )
    session.add(version)
    session.flush()
    flow.current_version_id = version.id
    flow.active_version_id = version.id
    session.commit()
    return flow


def test_call_graph_requires_all_outcome_branches():
    graph = _call_graph()
    assert validate_graph(graph) == []

    graph["edges"] = [
        edge for edge in graph["edges"]
        if edge.get("label") != "failed"
    ]
    errors = validate_graph(graph)
    assert any("call must handle branches" in error for error in errors)


def test_call_waits_for_callback_and_advances_idempotently():
    engine, session, org, store, customer = _setup()
    try:
        flow = _activate_flow(session, org, store, _call_graph())
        run = materialize_flow_trigger(session, flow, [customer.id])
        recipient_id, claim_token = claim_flow_recipients(
            session,
            include_tokens=True,
        )[0]

        calls = []

        def fake_voice_sender(**payload):
            calls.append(payload)
            return {"call_id": "call-123", "status": "queued"}

        result = process_flow_recipient(
            session,
            recipient_id,
            claim_token=claim_token,
            voice_sender=fake_voice_sender,
        )
        assert result == "waiting"
        assert len(calls) == 1
        assert calls[0]["to"] == customer.phone
        assert "Ana" in calls[0]["prompt"]
        assert "Tienda Voice" in calls[0]["prompt"]

        recipient = session.get(
            AutomationFlowRecipientExecution,
            recipient_id,
        )
        assert recipient.status == "waiting"
        assert recipient.current_node_id == "call"

        response = complete_voice_call(
            session,
            call_id="call-123",
            outcome="confirmed",
            transcript="Sí, deseo recibirlo.",
            provider_status="completed",
        )
        assert response["status"] == "processed"

        recipient = session.get(
            AutomationFlowRecipientExecution,
            recipient_id,
        )
        assert recipient.current_node_id == "confirmed"
        assert recipient.status == "active"

        node_exec = session.query(AutomationNodeExecution).filter(
            AutomationNodeExecution.provider_message_id == "call-123",
        ).one()
        assert node_exec.status == "completed"
        assert node_exec.outcome == "confirmed"
        assert node_exec.extra_data["transcript"] == "Sí, deseo recibirlo."

        duplicate = complete_voice_call(
            session,
            call_id="call-123",
            outcome="rejected",
        )
        assert duplicate["status"] == "duplicate"
        assert session.get(
            AutomationFlowRecipientExecution,
            recipient_id,
        ).current_node_id == "confirmed"
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_call_timeout_routes_to_no_answer_without_redial():
    engine, session, org, store, customer = _setup()
    try:
        flow = _activate_flow(
            session,
            org,
            store,
            _call_graph(timeout_minutes=1),
        )
        materialize_flow_trigger(session, flow, [customer.id])
        now = utcnow()
        recipient_id, claim_token = claim_flow_recipients(
            session,
            now=now,
            include_tokens=True,
        )[0]

        calls = []

        def fake_voice_sender(**payload):
            calls.append(payload)
            return {"call_id": "call-timeout", "status": "queued"}

        assert process_flow_recipient(
            session,
            recipient_id,
            now=now,
            claim_token=claim_token,
            voice_sender=fake_voice_sender,
        ) == "waiting"

        future = now + timedelta(minutes=2)
        timed_out = claim_flow_recipients(
            session,
            now=future,
            include_tokens=True,
        )
        assert len(timed_out) == 1

        assert process_flow_recipient(
            session,
            recipient_id,
            now=future,
            claim_token=timed_out[0][1],
            voice_sender=fake_voice_sender,
        ) == "advanced"

        recipient = session.get(
            AutomationFlowRecipientExecution,
            recipient_id,
        )
        assert recipient.current_node_id == "no_answer"
        assert len(calls) == 1
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
