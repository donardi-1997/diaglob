"""Focused V2.1 campaign safety and audience tests."""

import json
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker

from app.automation_campaigns import (
    audience_metrics,
    render_template,
    validate_campaign,
)
from app.db import Base
from app.models import Customer, CustomerStoreProfile, Organization, Store
from app.models import AutomationAudienceMember, AutomationCampaign, AutomationRecipientExecution, AutomationRun, Conversation, Message, WhatsAppConnection, WhatsAppMessageTemplate
from app.automation_execution_engine import (
    claim_recipients,
    materialize_due_campaigns,
    process_recipient,
    reclaim_expired_leases,
    worker_cycle,
    _recipient_rows_query,
)
from app.whatsapp_client import WhatsAppDeliveryError, send_whatsapp_template_message
from app.whatsapp_compliance import evaluate_whatsapp_delivery_eligibility, get_whatsapp_service_window_status
from app.main import _replace_campaign_members


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    organization = Organization(name="Campaign Org", slug="campaign-org")
    session.add(organization)
    session.flush()
    store = Store(organization_id=organization.id, name="Campaign Store", slug="campaign-store", country_code="CO", currency="COP", timezone="America/Bogota", default_language="es")
    session.add(store)
    session.flush()
    yield session, organization, store
    session.close()
    Base.metadata.drop_all(engine)


def campaign_data():
    return {
        "automation_type": "custom", "status": "draft", "audience_type": "dynamic",
        "audience_filters": {}, "schedule_type": "once",
        "schedule_config": {"starts_at": datetime.utcnow().isoformat()},
        "timezone": "America/Bogota", "cooldown_days": 0, "channel": "whatsapp",
        "message_template": "Hola {{customer.name}} de {{store.name}}",
    }


def test_template_rejects_unknown_variable(db):
    _, _, store = db
    data = campaign_data()
    data["message_template"] = "Hola {{customer.secret}}"
    with pytest.raises(HTTPException, match="Unknown"):
        validate_campaign(data, store)


def test_dynamic_audience_uses_canonical_segment_metrics(db):
    session, organization, store = db
    customer = Customer(organization_id=organization.id, name="Ana", phone="573001234567", country_code="CO")
    session.add(customer)
    session.flush()
    session.add(CustomerStoreProfile(organization_id=organization.id, customer_id=customer.id, store_id=store.id, currency="COP"))
    session.commit()

    matched = audience_metrics(session, organization.id, store.id, "dynamic", {"segment": ["new"], "country_codes": ["CO"]})

    assert [item["id"] for item in matched] == [customer.id]
    assert matched[0]["primary_segment"] == "new"


def test_renderer_never_renders_none(db):
    _, _, store = db
    assert render_template("Hola {{customer.name}}", {"name": "", "primary_segment": "new", "customer_health": "active"}, store) is None


def make_campaign(session, organization, store, *, status="active", schedule_type="once", next_run_at=None, cooldown_days=0):
    campaign = AutomationCampaign(
        organization_id=organization.id, store_id=store.id, name=f"Campaign {datetime.utcnow().timestamp()}",
        status=status, audience_type="dynamic", audience_filters={}, schedule_type=schedule_type,
        schedule_config={"starts_at": (datetime.utcnow() - timedelta(minutes=1)).isoformat(), "time_of_day": "10:00", "days_of_week": [0]},
        timezone="America/Bogota", cooldown_days=cooldown_days, message_template="Hola {{customer.name}}",
        next_run_at=next_run_at or datetime.utcnow() - timedelta(minutes=1), execution_enabled_at=datetime.utcnow(),
    )
    session.add(campaign)
    session.commit()
    return campaign


def add_customer(session, organization, store, name="Bea"):
    customer = Customer(organization_id=organization.id, name=name, phone="573001234567", country_code="CO")
    session.add(customer); session.flush()
    session.add(CustomerStoreProfile(organization_id=organization.id, customer_id=customer.id, store_id=store.id, currency="COP"))
    conversation = Conversation(organization_id=organization.id, store_id=store.id, customer_id=customer.id, channel="WhatsApp", preview="hello", mode="ai")
    session.add(conversation); session.flush()
    session.add(Message(conversation_id=conversation.id, sender="customer", text="hello", provider="whatsapp", external_message_id=f"inbound-{customer.id}"))
    session.commit()
    return customer


def test_due_campaign_materializes_one_snapshot_and_next_run(db):
    session, organization, store = db
    add_customer(session, organization, store)
    campaign = make_campaign(session, organization, store, schedule_type="daily")
    now = datetime.utcnow()

    assert materialize_due_campaigns(session, now) == 1
    assert materialize_due_campaigns(session, now) == 0
    run = session.query(AutomationRun).filter_by(automation_id=campaign.id).one()
    assert run.scheduled_for <= now
    assert session.query(AutomationRecipientExecution).filter_by(run_id=run.id).count() == 1
    assert session.get(AutomationCampaign, campaign.id).next_run_at > now


def test_paused_campaign_is_not_materialized(db):
    session, organization, store = db
    make_campaign(session, organization, store, status="paused")
    assert materialize_due_campaigns(session) == 0


def test_transient_failure_retries_and_timeout_is_ambiguous(db, monkeypatch):
    session, organization, store = db
    add_customer(session, organization, store)
    campaign = make_campaign(session, organization, store)
    connection = WhatsAppConnection(organization_id=organization.id, store_id=store.id, phone_number_id="phone-id", business_account_id="business-id", access_token_encrypted="encrypted", verify_token="verify")
    session.add(connection); session.commit()
    materialize_due_campaigns(session)
    recipient_id = claim_recipients(session)[0]
    monkeypatch.setattr("app.automation_execution_engine.decrypt_whatsapp_secret", lambda _: "token")

    assert process_recipient(session, recipient_id, sender=lambda *_: (_ for _ in ()).throw(WhatsAppDeliveryError("http_500", "transient", "retry"))) == "retry_wait"
    recipient = session.get(AutomationRecipientExecution, recipient_id)
    assert recipient.status == "retry_wait"
    recipient.status = "processing"; recipient.next_attempt_at = datetime.utcnow(); session.commit()
    assert process_recipient(session, recipient_id, sender=lambda *_: (_ for _ in ()).throw(WhatsAppDeliveryError("timeout", "ambiguous", "unknown"))) == "ambiguous"
    assert session.get(AutomationRecipientExecution, recipient_id).status == "ambiguous"


def test_cooldown_and_expired_processing_lease_are_safe(db):
    session, organization, store = db
    customer = add_customer(session, organization, store)
    campaign = make_campaign(session, organization, store, cooldown_days=7)
    previous_run = AutomationRun(automation_id=campaign.id, organization_id=organization.id, status="completed", run_key="previous", started_at=datetime.utcnow())
    session.add(previous_run); session.flush()
    session.add(AutomationRecipientExecution(run_id=previous_run.id, customer_id=customer.id, status="sent", sent_at=datetime.utcnow()))
    session.commit()
    materialize_due_campaigns(session)
    recipient_id = claim_recipients(session)[0]
    assert process_recipient(session, recipient_id) == "cooldown"
    recipient = session.get(AutomationRecipientExecution, recipient_id)
    recipient.status = "processing"; recipient.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
    session.commit(); reclaim_expired_leases(session)
    assert session.get(AutomationRecipientExecution, recipient_id).status == "queued"


def test_pause_freezes_claimed_recipient_and_success_persists_provider_id(db, monkeypatch):
    session, organization, store = db
    add_customer(session, organization, store)
    campaign = make_campaign(session, organization, store)
    session.add(WhatsAppConnection(organization_id=organization.id, store_id=store.id, phone_number_id="phone", business_account_id="business", access_token_encrypted="encrypted", verify_token="verify"))
    session.commit(); materialize_due_campaigns(session)
    recipient_id = claim_recipients(session)[0]
    campaign.status = "paused"; session.commit()
    assert process_recipient(session, recipient_id) == "paused"
    assert session.get(AutomationRecipientExecution, recipient_id).status == "queued"
    campaign.status = "active"; session.commit()
    recipient = session.get(AutomationRecipientExecution, recipient_id); recipient.status = "processing"; recipient.next_attempt_at = datetime.utcnow(); session.commit()
    monkeypatch.setattr("app.automation_execution_engine.decrypt_whatsapp_secret", lambda _: "token")
    assert process_recipient(session, recipient_id, sender=lambda *_: {"message_id": "wamid.test"}) == "sent"
    assert session.get(AutomationRecipientExecution, recipient_id).provider_message_id == "wamid.test"


def test_legacy_active_campaign_without_execution_enablement_never_materializes(db):
    session, organization, store = db
    add_customer(session, organization, store)
    campaign = make_campaign(session, organization, store)
    campaign.execution_enabled_at = None
    session.commit()
    assert materialize_due_campaigns(session) == 0
    assert session.query(AutomationRun).filter_by(automation_id=campaign.id).count() == 0


def test_expired_sending_lease_becomes_ambiguous_not_queued(db):
    session, organization, store = db
    customer = add_customer(session, organization, store)
    campaign = make_campaign(session, organization, store)
    run = AutomationRun(automation_id=campaign.id, organization_id=organization.id, status="running", run_key="sending-lease", started_at=datetime.utcnow())
    session.add(run); session.flush()
    recipient = AutomationRecipientExecution(run_id=run.id, customer_id=customer.id, status="sending", lease_expires_at=datetime.utcnow() - timedelta(seconds=1), attempt_count=1)
    session.add(recipient); session.commit()
    reclaim_expired_leases(session)
    recipient = session.get(AutomationRecipientExecution, recipient.id)
    assert recipient.status == "ambiguous"
    assert recipient.error_code == "lease_expired_sending"


def test_worker_cycle_loads_claimed_recipient_rows_without_ambiguous_join(db):
    session, organization, store = db
    customer = add_customer(session, organization, store)
    campaign = make_campaign(session, organization, store)
    campaign.execution_enabled_at = None  # Keep scheduler materialization out of this join regression.
    run = AutomationRun(automation_id=campaign.id, organization_id=organization.id, status="pending", run_key="join-regression", started_at=datetime.utcnow())
    session.add(run); session.flush()
    recipient = AutomationRecipientExecution(run_id=run.id, customer_id=customer.id, status="queued", rendered_message="hello", next_attempt_at=datetime.utcnow())
    session.add(recipient); session.commit()

    # No WhatsApp connection is configured, so the real worker path cannot send.
    assert worker_cycle(session) == 1
    assert session.get(AutomationRecipientExecution, recipient.id).status == "failed"


def test_claimed_recipient_rows_query_compiles_for_postgresql(db):
    session, _, _ = db
    sql = str(_recipient_rows_query(session, [1]).statement.compile(dialect=postgresql.dialect()))
    assert "JOIN automation_runs ON automation_recipient_executions.run_id = automation_runs.id" in sql
    assert "JOIN automation_campaigns ON automation_runs.automation_id = automation_campaigns.id" in sql


def test_service_window_uses_only_recent_whatsapp_customer_inbound(db):
    session, organization, store = db
    customer = Customer(organization_id=organization.id, name="No inbound", phone="573009999999")
    session.add(customer); session.commit()
    assert get_whatsapp_service_window_status(session, organization.id, store.id, customer.id)["reason"] == "no_inbound_history"
    conversation = Conversation(organization_id=organization.id, store_id=store.id, customer_id=customer.id, channel="WhatsApp", preview="", mode="ai")
    session.add(conversation); session.flush()
    session.add(Message(conversation_id=conversation.id, sender="human", text="outbound", provider="whatsapp", external_message_id="outbound-only"))
    session.commit()
    assert not get_whatsapp_service_window_status(session, organization.id, store.id, customer.id)["inside_window"]
    session.add(Message(conversation_id=conversation.id, sender="customer", text="inbound", provider="whatsapp", external_message_id="recent-inbound", created_at=datetime.utcnow() - timedelta(hours=23, minutes=59)))
    session.commit()
    assert get_whatsapp_service_window_status(session, organization.id, store.id, customer.id)["inside_window"]


def test_service_window_boundary_and_store_isolation(db):
    session, organization, store = db
    customer = Customer(organization_id=organization.id, name="Boundary", phone="573006666666")
    other_store = Store(organization_id=organization.id, name="Other", slug="other-window-store", country_code="CO", currency="COP", timezone="America/Bogota", default_language="es")
    session.add_all([customer, other_store]); session.flush()
    other_conversation = Conversation(organization_id=organization.id, store_id=other_store.id, customer_id=customer.id, channel="WhatsApp", preview="", mode="ai")
    session.add(other_conversation); session.flush()
    now = datetime.utcnow()
    session.add(Message(conversation_id=other_conversation.id, sender="customer", text="wrong store", provider="whatsapp", external_message_id="wrong-store-inbound", created_at=now - timedelta(minutes=1)))
    session.commit()
    assert not get_whatsapp_service_window_status(session, organization.id, store.id, customer.id, now)["inside_window"]
    conversation = Conversation(organization_id=organization.id, store_id=store.id, customer_id=customer.id, channel="WhatsApp", preview="", mode="ai")
    session.add(conversation); session.flush()
    inbound = Message(conversation_id=conversation.id, sender="customer", text="boundary", provider="whatsapp", external_message_id="boundary-inbound", created_at=now - timedelta(hours=24))
    session.add(inbound); session.commit()
    assert not get_whatsapp_service_window_status(session, organization.id, store.id, customer.id, now)["inside_window"]
    inbound.created_at = now - timedelta(hours=23, minutes=59, seconds=59); session.commit()
    assert get_whatsapp_service_window_status(session, organization.id, store.id, customer.id, now)["inside_window"]


def test_compliance_skip_does_not_attempt_or_call_provider(db):
    session, organization, store = db
    customer = Customer(organization_id=organization.id, name="Outside", phone="573008888888")
    session.add(customer); session.flush()
    session.add(CustomerStoreProfile(organization_id=organization.id, customer_id=customer.id, store_id=store.id, currency="COP"))
    campaign = make_campaign(session, organization, store)
    session.add(WhatsAppConnection(organization_id=organization.id, store_id=store.id, phone_number_id="phone-window", business_account_id="business", access_token_encrypted="encrypted", verify_token="verify"))
    session.commit(); materialize_due_campaigns(session)
    recipient_id = claim_recipients(session)[0]
    assert process_recipient(session, recipient_id, sender=lambda *_: pytest.fail("provider must not be called")) == "outside_service_window"
    recipient = session.get(AutomationRecipientExecution, recipient_id)
    assert recipient.status == "skipped"
    assert recipient.attempt_count == 0


def test_auto_mode_outside_window_requires_approved_store_template(db):
    session, organization, store = db
    customer = Customer(organization_id=organization.id, name="Template", phone="573007777777")
    connection = WhatsAppConnection(organization_id=organization.id, store_id=store.id, phone_number_id="phone-template", business_account_id="business", access_token_encrypted="encrypted", verify_token="verify")
    session.add_all([customer, connection]); session.flush()
    campaign = make_campaign(session, organization, store)
    campaign.message_mode = "auto"
    session.commit()
    assert evaluate_whatsapp_delivery_eligibility(session, campaign, connection, customer.id)["reason"] == "template_required"
    template = WhatsAppMessageTemplate(organization_id=organization.id, whatsapp_connection_id=connection.id, provider_template_name="reactivate", language_code="es_CO", status="pending")
    session.add(template); session.flush(); campaign.whatsapp_template_id = template.id; session.commit()
    assert evaluate_whatsapp_delivery_eligibility(session, campaign, connection, customer.id)["reason"] == "template_not_approved"
    template.status = "approved"; session.commit()
    result = evaluate_whatsapp_delivery_eligibility(session, campaign, connection, customer.id)
    assert result["allowed"] and result["mode"] == "template"


def test_template_sender_uses_cloud_api_template_payload(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"messages": [{"id": "wamid.template"}]}

    def fake_post(url, **kwargs):
        captured["url"] = url; captured.update(kwargs)
        return Response()

    monkeypatch.setattr("app.whatsapp_client.httpx.post", fake_post)
    result = send_whatsapp_template_message("phone-id", "token", "573001", "reengage", "es_CO", [{"type": "body", "parameters": [{"type": "text", "text": "Ana"}]}])
    assert captured["json"] == {"messaging_product": "whatsapp", "recipient_type": "individual", "to": "573001", "type": "template", "template": {"name": "reengage", "language": {"code": "es_CO"}, "components": [{"type": "body", "parameters": [{"type": "text", "text": "Ana"}]}]}}
    assert result["message_id"] == "wamid.template"


def test_fixed_all_filtered_selection_snapshots_members_and_exclusions(db):
    session, organization, store = db
    customers = [add_customer(session, organization, store, f"Fixed {number}") for number in range(10)]
    campaign = make_campaign(session, organization, store, status="draft")
    campaign.audience_type = "fixed"; campaign.audience_filters = {"country_codes": ["CO"]}; session.commit()
    count = _replace_campaign_members(session, campaign, organization.id, store.id, {"selection_mode": "all_filtered", "audience_filters": campaign.audience_filters, "excluded_customer_ids": [customers[0].id, customers[1].id]})
    session.commit()
    assert count == 8
    assert session.query(AutomationAudienceMember).filter_by(automation_id=campaign.id).count() == 8
    add_customer(session, organization, store, "Future fixed member")
    assert session.query(AutomationAudienceMember).filter_by(automation_id=campaign.id).count() == 8


def test_fixed_explicit_selection_is_store_scoped_and_deduplicated(db):
    session, organization, store = db
    customer = add_customer(session, organization, store)
    campaign = make_campaign(session, organization, store, status="draft")
    campaign.audience_type = "fixed"; session.commit()
    assert _replace_campaign_members(session, campaign, organization.id, store.id, {"member_ids": [customer.id, customer.id]}) == 1
    session.commit()
    assert session.query(AutomationAudienceMember).filter_by(automation_id=campaign.id).count() == 1


def test_replacing_fixed_members_does_not_change_historical_run_recipients(db):
    session, organization, store = db
    first, second = add_customer(session, organization, store, "First"), add_customer(session, organization, store, "Second")
    campaign = make_campaign(session, organization, store, status="draft")
    campaign.audience_type = "fixed"; session.commit()
    _replace_campaign_members(session, campaign, organization.id, store.id, {"member_ids": [first.id]})
    run = AutomationRun(automation_id=campaign.id, organization_id=organization.id, status="completed", run_key="historical", started_at=datetime.utcnow())
    session.add(run); session.flush(); session.add(AutomationRecipientExecution(run_id=run.id, customer_id=first.id, status="sent")); session.commit()
    _replace_campaign_members(session, campaign, organization.id, store.id, {"member_ids": [second.id]}); session.commit()
    assert session.query(AutomationRecipientExecution).filter_by(run_id=run.id, customer_id=first.id).count() == 1
