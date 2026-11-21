"""Synthetic SQL checks for strict store-scoped Shopify automation scrub."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    AutomationAudienceMember, AutomationCampaign, AutomationDeliveryAttempt,
    AutomationFlow, AutomationFlowRecipientExecution, AutomationFlowRun,
    AutomationFlowVersion, AutomationNodeExecution, AutomationRecipientExecution,
    AutomationRun, Customer, Organization, Store,
)
from app.services.shopify_privacy_automation_redaction import scrub_shopify_automation_scope


@pytest.fixture()
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic compliance", slug="synthetic-scrub")
        db.add(org)
        db.flush()
        stores = [
            Store(organization_id=org.id, name=f"Store-{n}", slug=f"scrub-{n}",
                  shopify_domain=f"scrub-{n}.myshopify.com",
                  country_code="CO", currency="COP", timezone="UTC",
                  deleted=False, active=True)
            for n in (1, 2)
        ]
        buyer = Customer(organization_id=org.id, name="SENSITIVE_BUYER", phone="123")
        other = Customer(organization_id=org.id, name="OTHER_BUYER", phone="456")
        db.add_all([*stores, buyer, other])
        db.flush()
        campaigns = []
        recipients = []
        attempts = []
        flows = []
        flow_recipients = []
        nodes = []
        for index, store in enumerate(stores):
            campaign = AutomationCampaign(
                organization_id=org.id, store_id=store.id,
                name=f"campaign-{index}", timezone="UTC",
                message_template="Hi buyer",
            )
            db.add(campaign)
            db.flush()
            member = AutomationAudienceMember(
                automation_id=campaign.id, customer_id=buyer.id, included=True,
            )
            run = AutomationRun(
                automation_id=campaign.id, organization_id=org.id,
                run_key=f"run-{index}", status="running",
            )
            db.add_all([member, run])
            db.flush()
            recipient = AutomationRecipientExecution(
                run_id=run.id, customer_id=buyer.id,
                status="sending" if index == 0 else "queued",
                rendered_message=f"SENSITIVE_CAMPAIGN_{index}",
                template_data={"customer.name": f"SENSITIVE_{index}"},
                provider_message_id=f"PROVIDER_{index}",
                error_message=f"CONTACT_{index}",
            )
            db.add(recipient)
            db.flush()
            attempt = AutomationDeliveryAttempt(
                recipient_execution_id=recipient.id,
                attempt_number=1, status="sending",
                provider_message_id=f"PROVIDER_{index}",
                error_message=f"DETAILS_{index}",
            )
            db.add(attempt)
            flow = AutomationFlow(
                organization_id=org.id, store_id=store.id,
                name=f"flow-{index}",
            )
            db.add(flow)
            db.flush()
            version = AutomationFlowVersion(
                flow_id=flow.id, organization_id=org.id,
                version_number=1, graph={"nodes": []},
            )
            db.add(version)
            db.flush()
            flow_run = AutomationFlowRun(
                flow_id=flow.id, flow_version_id=version.id,
                organization_id=org.id, store_id=store.id,
                status="running", trigger_context={"message": f"SENSITIVE_TRIGGER_{index}"},
            )
            db.add(flow_run)
            db.flush()
            flow_recipient = AutomationFlowRecipientExecution(
                flow_run_id=flow_run.id, flow_version_id=version.id,
                organization_id=org.id, customer_id=buyer.id,
                status="waiting", claim_token=f"SENSITIVE_LEASE_{index}",
            )
            db.add(flow_recipient)
            db.flush()
            node = AutomationNodeExecution(
                flow_recipient_execution_id=flow_recipient.id,
                node_id="message", node_type="message",
                extra_data={"payload": f"SENSITIVE_NODE_{index}"},
                provider_message_id=f"PROVIDER_NODE_{index}",
                error_message=f"ERROR_NODE_{index}",
            )
            db.add(node)
            campaigns.append(campaign)
            recipients.append(recipient)
            attempts.append(attempt)
            flows.append(flow_run)
            flow_recipients.append(flow_recipient)
            nodes.append(node)
        db.commit()
        yield db, org, stores, buyer, other, campaigns, recipients, attempts, flows, flow_recipients, nodes
    engine.dispose()


def test_scrubs_target_store_only_and_identifies_inflight_delivery(sandbox):
    db, org, stores, buyer, other, campaigns, recipients, attempts, flows, frs, nodes = sandbox
    output = scrub_shopify_automation_scope(
        db, organization_id=org.id, store_id=stores[0].id,
        customer_ids={buyer.id},
    )
    db.commit()
    assert output["audience_members_removed"] == 1
    assert output["campaign_recipients_scrubbed"] == 1
    assert output["campaign_attempts_scrubbed"] == 1
    assert output["flow_recipients_scrubbed"] == 1
    assert output["flow_nodes_scrubbed"] == 1
    assert output["flow_contexts_scrubbed"] == 1
    assert output["possible_inflight_deliveries"] == 2
    assert output["fulfillment_complete"] is False
    db.refresh(recipients[0])
    assert recipients[0].status == "ambiguous"
    assert recipients[0].rendered_message is None
    assert recipients[0].template_data == {}
    assert recipients[0].provider_message_id is None
    db.refresh(recipients[1])
    assert recipients[1].status == "queued"
    assert recipients[1].rendered_message == "SENSITIVE_CAMPAIGN_1"
    db.refresh(attempts[0])
    assert attempts[0].provider_message_id is None
    db.refresh(attempts[1])
    assert attempts[1].provider_message_id == "PROVIDER_1"
    db.refresh(frs[0])
    assert frs[0].status == "failed" and frs[0].claim_token is None
    db.refresh(frs[1])
    assert frs[1].status == "waiting"
    db.refresh(flows[0])
    assert flows[0].trigger_context is None
    db.refresh(flows[1])
    assert flows[1].trigger_context == {"message": "SENSITIVE_TRIGGER_1"}
    db.refresh(nodes[0])
    assert nodes[0].extra_data is None and nodes[0].provider_message_id is None
    db.refresh(nodes[1])
    assert nodes[1].extra_data == {"payload": "SENSITIVE_NODE_1"}


def test_empty_subject_set_never_becomes_full_shop_redaction(sandbox):
    db, org, stores, buyer, *_ = sandbox
    result = scrub_shopify_automation_scope(
        db, organization_id=org.id, store_id=stores[0].id,
        customer_ids=set(),
    )
    assert result["campaign_recipients_scrubbed"] == 0
    assert result["flow_recipients_scrubbed"] == 0
    assert result["audience_members_removed"] == 0


def test_full_shop_scrubs_all_recipients_but_keeps_other_store(sandbox):
    db, org, stores, buyer, other, campaigns, recipients, *_ = sandbox
    result = scrub_shopify_automation_scope(
        db, organization_id=org.id, store_id=stores[0].id,
        customer_ids=None,
    )
    assert result["campaign_recipients_scrubbed"] == 1
    assert result["flow_contexts_scrubbed"] == 1
    assert recipients[1].rendered_message == "SENSITIVE_CAMPAIGN_1"


@pytest.mark.parametrize("bad_ids", [{-1}, {0}, {"1"}, [1], {-5, 3}])
def test_invalid_subject_list_is_rejected(sandbox, bad_ids):
    db, org, stores, *_ = sandbox
    with pytest.raises(ValueError, match="PRIVACY_AUTOMATION_SCOPE_INVALID"):
        scrub_shopify_automation_scope(
            db, organization_id=org.id, store_id=stores[0].id,
            customer_ids=bad_ids,
        )
