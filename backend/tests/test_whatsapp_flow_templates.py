"""Flow WhatsApp messages: approved templates with order/shipment data,
compliance skips that continue the flow, and the legacy 24h-window guard."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.automation_flow_engine as flow_engine
from app.automation_flow_engine import (
    claim_flow_recipients,
    materialize_flow_trigger,
    process_flow_recipient,
    utcnow,
)
from app.automation_flow_graph import validate_graph
from app.automations import execute_send_whatsapp_message
from app.db import Base
from app.models import (
    AutomationExecution,
    AutomationFlow,
    AutomationFlowRecipientExecution,
    AutomationFlowVersion,
    AutomationNodeExecution,
    Conversation,
    Customer,
    CustomerStoreProfile,
    Message,
    Organization,
    Store,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
)
from app.whatsapp_compliance import (
    FLOW_TEMPLATE_VARIABLES,
    template_body_parameter_count,
    template_components,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    org = Organization(name="WA Org", slug="wa-org", plan="pro", subscription_status="active")
    session.add(org)
    session.flush()
    store = Store(
        organization_id=org.id, name="WA Store", slug="wa-store",
        country_code="CO", currency="COP", timezone="America/Bogota",
        default_language="es",
    )
    session.add(store)
    session.flush()
    connection = WhatsAppConnection(
        organization_id=org.id, store_id=store.id,
        phone_number_id="pn-test", business_account_id="waba-test",
        access_token_encrypted="encrypted", verify_token="verify",
        status="connected",
    )
    session.add(connection)
    session.flush()
    customer = Customer(organization_id=org.id, name="Ana", phone="+573001112233")
    session.add(customer)
    session.flush()
    session.add(CustomerStoreProfile(
        organization_id=org.id, customer_id=customer.id,
        store_id=store.id, currency="COP",
    ))
    session.commit()
    yield SimpleNamespace(session=session, org=org, store=store, connection=connection, customer=customer)
    session.close()
    engine.dispose()


def _template(ctx, body="Hola, tu pedido {{1}} por {{2}} va en camino", status="approved"):
    template = WhatsAppMessageTemplate(
        organization_id=ctx.org.id,
        whatsapp_connection_id=ctx.connection.id,
        provider_template_name="order_update",
        language_code="es",
        category="UTILITY",
        status=status,
        components={"items": [{"type": "BODY", "text": body}]},
    )
    ctx.session.add(template)
    ctx.session.commit()
    return template


def _flow(ctx, first_message: dict):
    graph = {
        "nodes": [
            {"id": "trigger", "type": "trigger", "config": {"trigger_type": "order_created"}},
            {"id": "msg1", "type": "message", "config": first_message},
            {"id": "msg2", "type": "message", "config": {
                "message_mode": "free_form", "message_template": "Gracias {{customer.name}}",
            }},
            {"id": "end", "type": "end", "config": {}},
        ],
        "edges": [
            {"source": "trigger", "target": "msg1"},
            {"source": "msg1", "target": "msg2"},
            {"source": "msg2", "target": "end"},
        ],
    }
    assert validate_graph(graph) == []
    flow = AutomationFlow(
        organization_id=ctx.org.id, store_id=ctx.store.id,
        name="Order update", status="draft",
    )
    ctx.session.add(flow)
    ctx.session.flush()
    version = AutomationFlowVersion(
        flow_id=flow.id, organization_id=ctx.org.id, version_number=1, graph=graph,
    )
    ctx.session.add(version)
    ctx.session.flush()
    version.published_at = utcnow()
    version.activated_at = utcnow()
    flow.current_version_id = version.id
    flow.active_version_id = version.id
    flow.status = "active"
    ctx.session.commit()
    return flow


def _run_first_step(ctx, flow, monkeypatch, trigger_context=None):
    sent_templates = []
    sent_text = []
    monkeypatch.setattr(flow_engine, "decrypt_whatsapp_secret", lambda _value: "token")
    monkeypatch.setattr(
        flow_engine,
        "send_whatsapp_template_message",
        lambda *args: sent_templates.append(args) or {"message_id": "wamid.template"},
    )
    run = materialize_flow_trigger(
        ctx.session, flow, [ctx.customer.id],
        trigger_context=trigger_context or {
            "order": {"number": "#1001", "total": 125000.0, "currency": "COP"},
        },
    )
    assert run is not None
    claimed = claim_flow_recipients(ctx.session)
    assert len(claimed) == 1
    recipient = ctx.session.get(AutomationFlowRecipientExecution, claimed[0])
    result = process_flow_recipient(
        ctx.session, recipient.id, claim_token=recipient.claim_token,
        sender=lambda *args: sent_text.append(args) or {"message_id": "wamid.text"},
    )
    recipient = ctx.session.get(AutomationFlowRecipientExecution, claimed[0])
    return result, recipient, sent_templates, sent_text


def test_template_mode_sends_approved_template_with_order_data(db, monkeypatch):
    template = _template(db)
    flow = _flow(db, {
        "message_mode": "template",
        "whatsapp_template_id": template.id,
        "template_variables": {"body": ["order.number", "order.total"]},
    })

    result, recipient, sent_templates, sent_text = _run_first_step(db, flow, monkeypatch)

    assert result == "sent"
    assert sent_text == []
    assert len(sent_templates) == 1
    _phone_id, _token, phone, name, language, components = sent_templates[0]
    assert (phone, name, language) == ("+573001112233", "order_update", "es")
    assert components == [{"type": "body", "parameters": [
        {"type": "text", "text": "#1001"},
        {"type": "text", "text": "125000.0"},
    ]}]
    assert recipient.current_node_id == "msg2"
    assert recipient.status == "active"


def test_auto_mode_outside_window_uses_template_not_free_text(db, monkeypatch):
    template = _template(db)
    flow = _flow(db, {
        "message_mode": "auto",
        "message_template": "Tu pedido {{order.number}} fue confirmado",
        "whatsapp_template_id": template.id,
        "template_variables": {"body": ["order.number", "order.total"]},
    })

    result, _recipient, sent_templates, sent_text = _run_first_step(db, flow, monkeypatch)

    assert result == "sent"
    assert len(sent_templates) == 1
    assert sent_text == []


def test_compliance_skip_continues_to_next_node(db, monkeypatch):
    # Free text with no inbound history is outside the 24h window.
    flow = _flow(db, {"message_mode": "free_form", "message_template": "Hola {{customer.name}}"})

    result, recipient, sent_templates, sent_text = _run_first_step(db, flow, monkeypatch)

    assert result == "skipped"
    assert sent_templates == [] and sent_text == []
    # Regression: the recipient used to be marked completed here.
    assert recipient.status == "active"
    assert recipient.current_node_id == "msg2"
    skipped = db.session.query(AutomationNodeExecution).filter(
        AutomationNodeExecution.flow_recipient_execution_id == recipient.id,
        AutomationNodeExecution.node_id == "msg1",
    ).one()
    assert skipped.status == "skipped"
    assert skipped.error_code == "outside_service_window" or skipped.error_code == "no_inbound_history"


def test_parameter_count_mismatch_skips_without_calling_meta(db, monkeypatch):
    template = _template(db, body="Pedido {{1}}, total {{2}}, envío {{3}}")
    flow = _flow(db, {
        "message_mode": "template",
        "whatsapp_template_id": template.id,
        "template_variables": {"body": ["order.number", "order.total"]},
    })

    result, recipient, sent_templates, _sent_text = _run_first_step(db, flow, monkeypatch)

    assert result == "skipped"
    assert sent_templates == []
    assert recipient.current_node_id == "msg2"


def test_missing_event_data_skips_template(db, monkeypatch):
    template = _template(db, body="Tu guía es {{1}}")
    flow = _flow(db, {
        "message_mode": "template",
        "whatsapp_template_id": template.id,
        "template_variables": {"body": ["shipment.tracking_number"]},
    })

    result, _recipient, sent_templates, _sent_text = _run_first_step(
        db, flow, monkeypatch, trigger_context={"order": {"number": "#1"}},
    )

    assert result == "skipped"
    assert sent_templates == []


# ---------------------------------------------------------------- unit level

def test_campaign_templates_keep_the_customer_only_variables():
    template = SimpleNamespace(components={"items": [{"type": "BODY", "text": "Pedido {{1}}"}]})
    with pytest.raises(ValueError):
        template_components(template, {"body": ["order.number"]}, {"order.number": "#1"})
    assert template_components(
        template, {"body": ["order.number"]}, {"order.number": "#1"},
        allowed=FLOW_TEMPLATE_VARIABLES,
    ) == [{"type": "body", "parameters": [{"type": "text", "text": "#1"}]}]


def test_body_parameter_count_ignores_repeated_and_unknown_components():
    assert template_body_parameter_count(SimpleNamespace(
        components={"items": [{"type": "HEADER", "text": "{{1}}"}, {"type": "BODY", "text": "{{1}} y {{2}} y {{1}}"}]},
    )) == 2
    assert template_body_parameter_count(SimpleNamespace(components={})) is None


def test_flow_variables_exclude_contact_details():
    assert not {"customer.email", "customer.phone", "order.shipping.address1"} & FLOW_TEMPLATE_VARIABLES


@pytest.mark.parametrize("config,expected", [
    ({"message_mode": "template"}, "a WhatsApp template is required"),
    ({"message_mode": "auto", "whatsapp_template_id": 3}, "message_template is required"),
    ({"message_mode": "template", "whatsapp_template_id": "3"}, "invalid whatsapp_template_id"),
    ({"message_mode": "template", "whatsapp_template_id": 3,
      "template_variables": {"body": ["customer.email"]}}, "unsupported template variables"),
    ({"message_mode": "template", "whatsapp_template_id": 3,
      "template_variables": {"body": "order.number"}}, "must be a list"),
])
def test_message_node_validation_errors(config, expected):
    graph = {
        "nodes": [
            {"id": "t", "type": "trigger", "config": {"trigger_type": "order_created"}},
            {"id": "m", "type": "message", "config": config},
            {"id": "e", "type": "end", "config": {}},
        ],
        "edges": [{"source": "t", "target": "m"}, {"source": "m", "target": "e"}],
    }
    assert any(expected in error for error in validate_graph(graph))


def test_template_mode_does_not_require_free_text():
    graph = {
        "nodes": [
            {"id": "t", "type": "trigger", "config": {"trigger_type": "shipment_delivered"}},
            {"id": "m", "type": "message", "config": {
                "message_mode": "template", "whatsapp_template_id": 9,
                "template_variables": {"body": ["customer.name", "shipment.tracking_number"]},
            }},
            {"id": "e", "type": "end", "config": {}},
        ],
        "edges": [{"source": "t", "target": "m"}, {"source": "m", "target": "e"}],
    }
    assert validate_graph(graph) == []


# ------------------------------------------------------- legacy rule action

def _legacy_send(ctx, monkeypatch, inbound_minutes_ago=None):
    conversation = Conversation(
        organization_id=ctx.org.id, store_id=ctx.store.id, customer_id=ctx.customer.id,
        channel="WhatsApp", preview="hi", mode="ai",
    )
    ctx.session.add(conversation)
    ctx.session.flush()
    if inbound_minutes_ago is not None:
        ctx.session.add(Message(
            conversation_id=conversation.id, sender="customer", text="hi",
            provider="whatsapp", external_message_id="wamid.in",
            created_at=datetime.utcnow() - timedelta(minutes=inbound_minutes_ago),
        ))
    execution = AutomationExecution(
        automation_id=1, organization_id=ctx.org.id, store_id=ctx.store.id,
        event_type="manual", status="running",
    )
    ctx.session.add(execution)
    ctx.session.commit()
    sent = []
    monkeypatch.setattr("app.whatsapp_security.decrypt_whatsapp_secret", lambda _v: "token")
    monkeypatch.setattr(
        "app.whatsapp_client.send_whatsapp_text_message",
        lambda **kwargs: sent.append(kwargs) or {"message_id": "wamid.out"},
    )
    result = execute_send_whatsapp_message(
        db=ctx.session, organization_id=ctx.org.id, store_id=ctx.store.id,
        action={"type": "send_whatsapp_message", "message": "Hola"},
        payload={"conversation_id": conversation.id}, execution=execution,
    )
    return result, sent


def test_legacy_free_text_is_skipped_outside_the_24h_window(db, monkeypatch):
    result, sent = _legacy_send(db, monkeypatch, inbound_minutes_ago=None)
    assert result["status"] == "skipped"
    assert result["reason"] == "no_inbound_history"
    assert sent == []

    result, sent = _legacy_send(db, monkeypatch, inbound_minutes_ago=25 * 60)
    assert result["status"] == "skipped"
    assert result["reason"] == "outside_service_window"
    assert sent == []


def test_legacy_free_text_is_sent_inside_the_24h_window(db, monkeypatch):
    result, sent = _legacy_send(db, monkeypatch, inbound_minutes_ago=30)
    assert result["status"] == "applied"
    assert len(sent) == 1 and sent[0]["text"] == "Hola"
