"""Meta error classification, channel pause, and non-text inbound messages.

All data is synthetic: no Meta token, phone or merchant is contacted.
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.whatsapp_client as whatsapp_client
from app.automation_execution_engine import (
    claim_recipients,
    materialize_due_campaigns,
    process_recipient,
)
from app.automation_flow_engine import (
    claim_flow_recipients,
    materialize_flow_trigger,
    process_flow_recipient,
)
from app.db import Base
from app.models import (
    AutomationFlowRecipientExecution,
    AutomationNodeExecution,
    AutomationRecipientExecution,
    Conversation,
    Customer,
    CustomerStoreProfile,
    Message,
    Organization,
    Store,
    WhatsAppConnection,
)
from app.services.whatsapp_channel_health import (
    CHANNEL_GIVE_UP,
    CHANNEL_PAUSE,
    CHANNEL_UNAVAILABLE_CODE,
    channel_pause_code,
)
from app.services.whatsapp_service import get_connection
from app.services.whatsapp_webhooks import (
    emit_webhook_events,
    inbound_message_content,
    process_webhook_payload,
)
from app.whatsapp_client import (
    WhatsAppDeliveryError,
    classify_whatsapp_error_response,
    send_whatsapp_text_message,
)
from tests.test_automation_campaigns import add_customer, make_campaign
from tests.test_automation_flows import _message_only_graph, _published_flow


@pytest.fixture(scope="module")
def engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db(engine):
    session = sessionmaker(bind=engine)()
    org = Organization(name="Channel Org", slug="channel-org", plan="pro", subscription_status="active")
    session.add(org)
    session.flush()
    store = Store(
        organization_id=org.id, name="Channel Store", slug="channel-store",
        country_code="CO", currency="COP", timezone="America/Bogota",
        default_language="es",
    )
    session.add(store)
    session.flush()
    connection = WhatsAppConnection(
        organization_id=org.id, store_id=store.id, phone_number_id="phone-1",
        business_account_id="waba-1", access_token_encrypted="encrypted",
        verify_token="verify", status="connected",
    )
    session.add(connection)
    session.commit()
    yield session, org, store, connection
    session.close()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


def _raise(code, category):
    def sender(*_args):
        raise WhatsAppDeliveryError(code, category, "WhatsApp rejected the request")
    return sender


# ── Meta error classification ────────────────────────────────────────────

def _response(status, body=None):
    request = httpx.Request("POST", "https://graph.facebook.com/v21.0/x/messages")
    if body is None:
        return httpx.Response(status, request=request, text="upstream")
    return httpx.Response(status, request=request, json=body)


@pytest.mark.parametrize(
    ("status", "body", "code", "category"),
    [
        # Meta sends throughput/pair/spam limits as HTTP 400: retry them.
        (400, {"error": {"code": 130429}}, "meta_130429", "transient"),
        (400, {"error": {"code": 131056}}, "meta_131056", "transient"),
        (400, {"error": {"code": 131048}}, "meta_131048", "transient"),
        # Token/account problems affect every send on the connection.
        (401, {"error": {"code": 190}}, "meta_190", "channel"),
        (403, {"error": {"code": 200}}, "meta_200", "channel"),
        (400, {"error": {"code": 131031}}, "meta_131031", "channel"),
        # Recipient-specific: retrying won't help.
        (400, {"error": {"code": 131047}}, "meta_131047", "permanent"),
        (400, {"error": {"code": 131026}}, "meta_131026", "permanent"),
        # No parsable Meta code: fall back to HTTP status.
        (500, None, "http_500", "transient"),
        (429, None, "http_429", "transient"),
        (401, None, "http_401", "channel"),
        (400, None, "http_400", "permanent"),
    ],
)
def test_meta_errors_are_classified_by_error_code(status, body, code, category):
    error = classify_whatsapp_error_response(_response(status, body))
    assert (error.code, error.category) == (code, category)


def test_classified_error_never_echoes_provider_body():
    body = {"error": {"code": 131047, "message": "Re-engagement for +573001234567"}}
    error = classify_whatsapp_error_response(_response(400, body))
    assert "573001234567" not in str(error)


def test_success_without_message_id_is_ambiguous_not_sent(monkeypatch):
    monkeypatch.setattr(
        whatsapp_client.httpx, "post",
        lambda *args, **kwargs: _response(200, {"messaging_product": "whatsapp"}),
    )
    with pytest.raises(WhatsAppDeliveryError) as raised:
        send_whatsapp_text_message("phone", "token", "573001234567", "hola")
    assert (raised.value.code, raised.value.category) == ("missing_message_id", "ambiguous")


def test_text_and_template_share_the_same_classification(monkeypatch):
    monkeypatch.setattr(
        whatsapp_client.httpx, "post",
        lambda *args, **kwargs: _response(400, {"error": {"code": 130429}}),
    )
    with pytest.raises(WhatsAppDeliveryError) as raised:
        send_whatsapp_text_message("phone", "token", "573001234567", "hola")
    assert raised.value.category == "transient"


# ── Channel pause: campaigns ─────────────────────────────────────────────

def test_campaign_channel_error_pauses_connection_and_defers_others(db, monkeypatch):
    session, org, store, connection = db
    add_customer(session, org, store, name="Ana")
    add_customer(session, org, store, name="Beto")
    make_campaign(session, org, store)
    monkeypatch.setattr("app.automation_execution_engine.decrypt_whatsapp_secret", lambda _: "token")
    materialize_due_campaigns(session)
    first, second = claim_recipients(session)
    now = datetime.utcnow()

    assert process_recipient(session, first, now=now, sender=_raise("meta_190", "channel")) == "channel_paused"
    session.expire_all()
    assert channel_pause_code(session.get(WhatsAppConnection, connection.id)) == "meta_190"
    paused = session.get(AutomationRecipientExecution, first)
    assert paused.status == "retry_wait"
    assert paused.next_attempt_at == now + CHANNEL_PAUSE

    calls = []
    result = process_recipient(
        session, second, now=now + timedelta(minutes=1),
        sender=lambda *args: calls.append(args) or {"message_id": "wamid.x"},
    )
    assert result == "channel_paused"
    assert calls == []
    deferred = session.get(AutomationRecipientExecution, second)
    assert deferred.status == "queued"
    assert deferred.error_code == CHANNEL_UNAVAILABLE_CODE
    assert deferred.attempt_count == 0


def test_campaign_success_after_pause_window_clears_the_pause(db, monkeypatch):
    session, org, store, connection = db
    add_customer(session, org, store)
    make_campaign(session, org, store)
    monkeypatch.setattr("app.automation_execution_engine.decrypt_whatsapp_secret", lambda _: "token")
    connection.last_error = "WHATSAPP_CHANNEL_PAUSED:meta_190"
    connection.updated_at = datetime.utcnow() - CHANNEL_PAUSE - timedelta(seconds=1)
    session.commit()
    materialize_due_campaigns(session)
    (recipient_id,) = claim_recipients(session)

    assert process_recipient(session, recipient_id, sender=lambda *_: {"message_id": "wamid.ok"}) == "sent"
    session.expire_all()
    assert session.get(WhatsAppConnection, connection.id).last_error is None


def test_campaign_gives_up_after_channel_stays_down(db, monkeypatch):
    session, org, store, connection = db
    add_customer(session, org, store)
    make_campaign(session, org, store)
    materialize_due_campaigns(session)
    (recipient_id,) = claim_recipients(session)
    later = datetime.utcnow() + CHANNEL_GIVE_UP + timedelta(minutes=1)
    connection.last_error = "WHATSAPP_CHANNEL_PAUSED:meta_190"
    connection.updated_at = later
    session.commit()

    assert process_recipient(session, recipient_id, now=later) == "failed"
    failed = session.get(AutomationRecipientExecution, recipient_id)
    assert failed.status == "failed"
    assert failed.error_code == CHANNEL_UNAVAILABLE_CODE


# ── Channel pause: flows ─────────────────────────────────────────────────

def _flow_customers(session, org, store, count):
    customers = []
    for index in range(count):
        customer = Customer(organization_id=org.id, name=f"C{index}", phone=f"57300111{index:04d}")
        session.add(customer)
        session.flush()
        session.add(CustomerStoreProfile(
            organization_id=org.id, customer_id=customer.id, store_id=store.id, currency="COP",
        ))
        customers.append(customer)
    session.commit()
    return customers


def test_flow_channel_error_pauses_without_failing_recipients(db, monkeypatch):
    session, org, store, connection = db
    import app.automation_flow_engine as flow_engine
    monkeypatch.setattr(
        flow_engine, "evaluate_whatsapp_delivery_eligibility",
        lambda *args, **kwargs: {"allowed": True, "mode": "free_form"},
    )
    monkeypatch.setattr(flow_engine, "_acquire_rate_slot", lambda *args: True)
    monkeypatch.setattr(flow_engine, "decrypt_whatsapp_secret", lambda _: "token")
    flow = _published_flow(session, org, store, _message_only_graph())
    customers = _flow_customers(session, org, store, 2)
    run = materialize_flow_trigger(session, flow, [c.id for c in customers])
    session.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.flow_run_id == run.id,
    ).update({"current_node_id": "msg"})
    session.commit()
    claims = claim_flow_recipients(session, include_tokens=True)
    (first_id, first_token), (second_id, second_token) = claims

    assert process_flow_recipient(
        session, first_id, claim_token=first_token, sender=_raise("meta_190", "channel"),
    ) == "channel_paused"
    session.expire_all()
    first = session.get(AutomationFlowRecipientExecution, first_id)
    assert first.status == "active"
    assert first.claim_token is None
    node = session.query(AutomationNodeExecution).filter(
        AutomationNodeExecution.flow_recipient_execution_id == first_id,
    ).one()
    assert node.status == "retry_wait"

    calls = []
    assert process_flow_recipient(
        session, second_id, claim_token=second_token,
        sender=lambda *args: calls.append(args),
    ) == "channel_paused"
    assert calls == []
    assert session.get(AutomationFlowRecipientExecution, second_id).status == "active"


# ── Merchant visibility ──────────────────────────────────────────────────

def test_connection_status_tells_merchant_to_reconnect(db):
    session, org, store, connection = db
    assert get_connection(session, org.id, store.id)["channel_attention"] == {
        "required": False, "reason": None,
    }
    connection.last_error = "WHATSAPP_CHANNEL_PAUSED:meta_190"
    session.commit()
    status = get_connection(session, org.id, store.id)
    assert status["connected"] is True
    assert status["channel_attention"] == {"required": True, "reason": "meta_190"}


# ── Inbound non-text messages ────────────────────────────────────────────

@pytest.mark.parametrize(
    ("message", "language", "expected"),
    [
        ({"type": "button", "button": {"text": "Confirmar pedido", "payload": "CONFIRM"}},
         "es", ("Confirmar pedido", "button", "CONFIRM")),
        ({"type": "interactive", "interactive": {"type": "button_reply",
          "button_reply": {"id": "yes", "title": "Sí"}}}, "es", ("Sí", "interactive", "yes")),
        ({"type": "interactive", "interactive": {"type": "list_reply",
          "list_reply": {"id": "opt2", "title": "Cambiar dirección"}}},
         "es", ("Cambiar dirección", "interactive", "opt2")),
        ({"type": "image", "image": {"id": "m1", "caption": "llegó roto"}},
         "es", ("[Imagen] llegó roto", "image", None)),
        ({"type": "audio", "audio": {"id": "m2"}}, "en", ("[Audio]", "audio", None)),
        ({"type": "document", "document": {"id": "m3", "filename": "factura.pdf"}},
         "pt-BR", ("[Documento] factura.pdf", "document", None)),
        ({"type": "location", "location": {"name": "Casa", "address": "Calle 1"}},
         "es", ("[Ubicación] Casa - Calle 1", "location", None)),
        ({"type": "reaction", "reaction": {"emoji": "👍"}}, "es", None),
        ({"type": "unsupported"}, "es", None),
        ({"type": "text", "text": {"body": "   "}}, "es", None),
    ],
)
def test_inbound_message_content(message, language, expected):
    assert inbound_message_content(message, language) == expected


def _webhook(*messages):
    return {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "phone-1"},
        "contacts": [{"wa_id": "573005550000", "profile": {"name": "Cliente"}}],
        "messages": [
            {"from": "573005550000", "id": f"wamid.in.{index}", **message}
            for index, message in enumerate(messages)
        ],
    }}]}]}


def test_template_button_reply_reaches_inbox_ai_and_automations(db, monkeypatch):
    session, org, store, _ = db
    result = process_webhook_payload(session, _webhook(
        {"type": "button", "button": {"text": "Confirmar pedido", "payload": "CONFIRM"}},
    ))
    stored = session.query(Message).one()
    assert stored.text == "Confirmar pedido"
    assert stored.sender == "customer"
    conversation = session.get(Conversation, stored.conversation_id)
    assert conversation.preview == "Confirmar pedido"
    assert result["inbound_conversation_ids"] == [conversation.id]

    emitted = []
    monkeypatch.setattr(
        "app.services.whatsapp_webhooks.safe_emit_event",
        lambda **kwargs: emitted.append(kwargs),
    )
    monkeypatch.setattr(
        "app.services.product_analytics.track_first_whatsapp_inbound", lambda **_: None,
    )
    emit_webhook_events(session, result["new_conversations"], result["new_messages"])
    received = [e for e in emitted if e["event_type"] == "message.received"]
    assert received[0]["payload"]["message"]["type"] == "button"
    assert received[0]["payload"]["message"]["button_payload"] == "CONFIRM"


def test_media_is_stored_but_not_answered_by_ai(db):
    session, org, store, _ = db
    result = process_webhook_payload(session, _webhook(
        {"type": "text", "text": {"body": "hola"}},
        {"type": "image", "image": {"id": "media-1"}},
    ))
    texts = [m.text for m in session.query(Message).order_by(Message.id).all()]
    assert texts == ["hola", "[Imagen]"]
    # The latest message is a photo the AI cannot read: leave it to a human.
    assert result["inbound_conversation_ids"] == []


def test_reactions_are_ignored(db):
    session, *_ = db
    result = process_webhook_payload(session, _webhook(
        {"type": "reaction", "reaction": {"message_id": "wamid.out", "emoji": "👍"}},
    ))
    assert session.query(Message).count() == 0
    assert result["new_messages"] == []


def test_manual_send_channel_error_pauses_automations(db, monkeypatch):
    session, org, store, connection = db
    customer = Customer(organization_id=org.id, name="Eva", phone="573001112222")
    session.add(customer)
    session.flush()
    conversation = Conversation(
        organization_id=org.id, store_id=store.id, customer_id=customer.id,
        channel="WhatsApp", mode="human",
    )
    session.add(conversation)
    session.commit()
    import app.services.whatsapp_service as service
    monkeypatch.setattr(
        service, "get_whatsapp_service_window_status",
        lambda *args, **kwargs: {"inside_window": True},
    )
    monkeypatch.setattr(service, "decrypt_whatsapp_secret", lambda _: "token")
    monkeypatch.setattr(service, "send_whatsapp_text_message", MagicMock(
        side_effect=WhatsAppDeliveryError("meta_190", "channel", "WhatsApp rejected the request"),
    ))
    with pytest.raises(service.WhatsAppSendError):
        service.send_message(session, org.id, conversation.id, "hola")
    session.expire_all()
    assert channel_pause_code(session.get(WhatsAppConnection, connection.id)) == "meta_190"
