"""Synthetic SQLite fixtures for Shopify customer-linked automation provenance."""
import json
from dataclasses import asdict

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    AutomationAudienceMember, AutomationCampaign, AutomationDeliveryAttempt,
    AutomationFlow, AutomationFlowRecipientExecution, AutomationFlowRun,
    AutomationFlowVersion, AutomationNodeExecution, AutomationRecipientExecution,
    AutomationRun, Customer, CustomerStoreProfile, Organization,
    ShopifyPrivacyRequest, Store,
)
from app.services.shopify_privacy_automation_provenance import (
    inspect_shopify_automation_privacy_impact,
)
from app.services.shopify_privacy_scope_preview import ShopifyPrivacyScopeError
from app.shopify_security import encrypt_shopify_secret


@pytest.fixture
def scenario(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org_a = Organization(name="Organization A", slug="org-a", plan="starter")
        org_b = Organization(name="Organization B", slug="org-b", plan="starter")
        db.add_all([org_a, org_b])
        db.flush()
        stores = []
        for label, org in (
            ("a", org_a),
            ("b", org_a),
            ("c", org_b),
        ):
            store = Store(
                organization_id=org.id, name=label, slug=f"store-{label}",
                country_code="CO", currency="COP", timezone="UTC",
                shopify_domain=f"{label}.myshopify.com",
            )
            db.add(store)
            stores.append(store)
        db.flush()
        shared = Customer(organization_id=org_a.id, name="Synthetic A", phone="1")
        other = Customer(organization_id=org_b.id, name="Synthetic B", phone="2")
        db.add_all([shared, other])
        db.flush()
        for store, customer in zip(stores, (shared, shared, other)):
            db.add(CustomerStoreProfile(
                organization_id=store.organization_id,
                store_id=store.id, customer_id=customer.id,
                external_customer_id="700", currency="COP",
            ))
            campaign = AutomationCampaign(
                organization_id=store.organization_id,
                store_id=store.id, name=f"campaign-{store.slug}",
                timezone="UTC", message_template="private checkout message",
            )
            db.add(campaign)
            db.flush()
            db.add(AutomationAudienceMember(
                automation_id=campaign.id, customer_id=customer.id
            ))
            run = AutomationRun(
                automation_id=campaign.id,
                organization_id=store.organization_id,
                run_key=f"synthetic-{store.slug}",
            )
            db.add(run)
            db.flush()
            recipient = AutomationRecipientExecution(
                run_id=run.id, customer_id=customer.id, status="sent",
                rendered_message=f"PRIVATE_MESSAGE_{store.slug}",
                template_data={"customer_address": store.slug},
            )
            db.add(recipient)
            db.flush()
            db.add(AutomationDeliveryAttempt(
                recipient_execution_id=recipient.id,
                attempt_number=1, status="sent",
                provider_message_id=f"PRIVATE_PROVIDER_{store.slug}",
            ))
            flow = AutomationFlow(
                organization_id=store.organization_id,
                store_id=store.id, name=f"flow-{store.slug}",
            )
            db.add(flow)
            db.flush()
            version = AutomationFlowVersion(
                flow_id=flow.id, organization_id=store.organization_id,
                version_number=1, graph={},
            )
            db.add(version)
            db.flush()
            flow_run = AutomationFlowRun(
                flow_id=flow.id, flow_version_id=version.id,
                organization_id=store.organization_id, store_id=store.id,
                trigger_context={"customer_name": store.slug},
            )
            db.add(flow_run)
            db.flush()
            flow_recipient = AutomationFlowRecipientExecution(
                flow_run_id=flow_run.id, flow_version_id=version.id,
                customer_id=customer.id, organization_id=store.organization_id,
                status="active",
            )
            db.add(flow_recipient)
            db.flush()
            db.add(AutomationNodeExecution(
                flow_recipient_execution_id=flow_recipient.id,
                node_id="message", node_type="message",
                extra_data={"private_contact": store.slug},
            ))
        receipt = ShopifyPrivacyRequest(
            request_id="s" * 64,
            topic="customers/data_request",
            shop_id="111", shop_domain=stores[0].shopify_domain,
            organization_id=org_a.id, store_id=stores[0].id,
            selector_encrypted=encrypt_shopify_secret(
                json.dumps({"customer": {"id": 700}})
            ),
        )
        db.add(receipt)
        db.commit()
        yield db, receipt
    engine.dispose()


def test_customer_exact_store_and_tenant_only(scenario):
    db, receipt = scenario
    impact = inspect_shopify_automation_privacy_impact(db, receipt)
    assert impact.attribution == "verified_external_customer_id"
    assert (
        impact.audience_members, impact.campaign_recipients,
        impact.delivery_attempts, impact.flow_recipients,
        impact.flow_node_executions,
    ) == (1, 1, 1, 1, 1)
    assert impact.complete is False
    assert impact.copilot_customer_attribution == "unavailable_no_customer_fk"
    result = str(asdict(impact))
    for secret in ("PRIVATE_MESSAGE", "PRIVATE_PROVIDER", "private checkout"):
        assert secret not in result
    assert not db.dirty and not db.new and not db.deleted


def test_unknown_subject_never_includes_shared_or_other_tenant_rows(scenario):
    db, receipt = scenario
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"id": 999999}})
    )
    impact = inspect_shopify_automation_privacy_impact(db, receipt)
    assert impact.attribution == "subject_unresolved"
    assert (
        impact.audience_members, impact.campaign_recipients,
        impact.delivery_attempts, impact.flow_recipients,
        impact.flow_node_executions,
    ) == (0, 0, 0, 0, 0)


def test_shop_redaction_counts_all_store_recipients_without_modifying_them(scenario):
    db, receipt = scenario
    receipt.topic = "shop/redact"
    receipt.selector_encrypted = "no_customer_selector_needed"
    impact = inspect_shopify_automation_privacy_impact(db, receipt)
    assert impact.attribution == "verified_store_scope"
    assert (
        impact.audience_members, impact.campaign_recipients,
        impact.delivery_attempts, impact.flow_recipients,
        impact.flow_node_executions,
    ) == (1, 1, 1, 1, 1)
    assert impact.complete is False
    assert impact.external_processor_coverage == "uncovered"


def test_store_domain_mismatch_rejected_before_automation_queries(scenario):
    db, receipt = scenario
    receipt.shop_domain = "other.myshopify.com"
    with pytest.raises(ShopifyPrivacyScopeError, match="STORE_MISMATCH"):
        inspect_shopify_automation_privacy_impact(db, receipt)


def test_tenant_unresolved_and_malformed_selector_fail_closed(scenario):
    db, receipt = scenario
    receipt.organization_id = None
    with pytest.raises(ShopifyPrivacyScopeError, match="TENANT_UNRESOLVED"):
        inspect_shopify_automation_privacy_impact(db, receipt)
    db.rollback()
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"email": "guess@example.com"}})
    )
    with pytest.raises(ShopifyPrivacyScopeError, match="CUSTOMER_ID_REQUIRED"):
        inspect_shopify_automation_privacy_impact(db, receipt)
