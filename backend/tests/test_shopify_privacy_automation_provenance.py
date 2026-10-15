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
    ShopifyPrivacyRequest, ShopifyPrivacyAuditEvent, Store,
)
from app.services.shopify_privacy_automation_provenance import (
    inspect_shopify_automation_privacy_impact,
)
from app.services.shopify_privacy_scope_preview import ShopifyPrivacyScopeError
from app.services.shopify_privacy_local_processor import (
    inspect_local_customer_export_counts,
)
from app.api.shopify_privacy_backlog import inspect_shopify_local_customer_export
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


def test_same_store_different_customer_is_excluded_but_shop_scope_counts_both(
    scenario,
):
    db, receipt = scenario
    target_store_id = receipt.store_id
    separate = Customer(
        organization_id=receipt.organization_id,
        name="Unrelated customer",
        phone="synthetic-2",
    )
    db.add(separate)
    db.flush()
    db.add(CustomerStoreProfile(
        organization_id=receipt.organization_id,
        store_id=target_store_id,
        customer_id=separate.id,
        external_customer_id="701",
        currency="COP",
    ))
    campaign = db.query(AutomationCampaign).filter(
        AutomationCampaign.store_id == target_store_id,
    ).one()
    campaign_run = db.query(AutomationRun).filter(
        AutomationRun.automation_id == campaign.id,
    ).one()
    db.add(AutomationAudienceMember(
        automation_id=campaign.id, customer_id=separate.id,
    ))
    recipient = AutomationRecipientExecution(
        run_id=campaign_run.id, customer_id=separate.id,
        status="sent", rendered_message="PRIVATE_DIFFERENT_SUBJECT",
    )
    db.add(recipient)
    db.flush()
    db.add(AutomationDeliveryAttempt(
        recipient_execution_id=recipient.id,
        attempt_number=1, status="sent",
    ))
    flow_run = db.query(AutomationFlowRun).filter(
        AutomationFlowRun.store_id == target_store_id,
    ).one()
    flow_recipient = AutomationFlowRecipientExecution(
        flow_run_id=flow_run.id,
        flow_version_id=flow_run.flow_version_id,
        organization_id=receipt.organization_id,
        customer_id=separate.id,
        status="active",
    )
    db.add(flow_recipient)
    db.flush()
    db.add(AutomationNodeExecution(
        flow_recipient_execution_id=flow_recipient.id,
        node_id="other-node", node_type="message",
    ))
    db.commit()

    customer_scope = inspect_shopify_automation_privacy_impact(db, receipt)
    assert (
        customer_scope.audience_members,
        customer_scope.campaign_recipients,
        customer_scope.delivery_attempts,
        customer_scope.flow_recipients,
        customer_scope.flow_node_executions,
    ) == (1, 1, 1, 1, 1)

    receipt.topic = "shop/redact"
    shop_scope = inspect_shopify_automation_privacy_impact(db, receipt)
    assert (
        shop_scope.audience_members,
        shop_scope.campaign_recipients,
        shop_scope.delivery_attempts,
        shop_scope.flow_recipients,
        shop_scope.flow_node_executions,
    ) == (2, 2, 2, 2, 2)
    assert shop_scope.complete is False


def test_signed_export_inspection_includes_store_scoped_automation_counts(
    scenario, monkeypatch,
):
    """Compare actual automation impact to the real read-only export endpoint."""
    from datetime import datetime
    from unittest.mock import patch

    db, receipt = scenario
    # Existing automation-only fixtures are intentionally not real signed
    # receipts. Complete exactly one synthetic receipt for this integration.
    receipt.request_id = "a" * 64
    db.add(ShopifyPrivacyAuditEvent(
        request_id=receipt.request_id,
        event_type="received", actor_type="shopify_hmac_verified",
        from_status=None, to_status="pending_policy_review",
        reason_code="tenant_bound", created_at=datetime.utcnow(),
    ))
    db.commit()
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-test-internal-secret")

    with patch(
        "app.services.shopify_privacy_local_processor.encrypt_shopify_secret",
        side_effect=AssertionError("never encrypt or build a personal export"),
    ) as encrypt:
        inspected = inspect_shopify_local_customer_export(
            request_id=receipt.request_id,
            x_internal_secret="synthetic-test-internal-secret", db=db,
        )
    encrypt.assert_not_called()
    assert inspected["automation"] == {
        "audience_members": 1,
        "campaign_recipients": 1,
        "delivery_attempts": 1,
        "flow_recipients": 1,
        "flow_node_executions": 1,
        "attribution": "verified_external_customer_id",
        "export_included": False,
        "coverage": "linked_records_only",
    }
    assert inspected["profiles"] == 1
    assert inspected["orders"] == 0
    assert inspected["complete"] is False
    assert inspected["merchant_delivery_allowed"] is False
    response = str(inspected)
    for secret in (
        "PRIVATE_MESSAGE", "PRIVATE_PROVIDER", "private checkout",
        "customer_address", "other.myshopify.com",
    ):
        assert secret not in response
    # Other-shop automations belong to a shared Customer but are never merged.
    assert db.query(AutomationAudienceMember).count() == 3


def test_export_inspection_automation_subject_cannot_be_guessed_by_email(
    scenario,
):
    """An email address is not enough to authorize an automation data scope."""
    from datetime import datetime
    from app.services.shopify_privacy_local_processor import ShopifyLocalPrivacyError

    db, receipt = scenario
    receipt.request_id = "b" * 64
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"email": "not-a-shopify-id@example.com"}})
    )
    db.add(ShopifyPrivacyAuditEvent(
        request_id=receipt.request_id,
        event_type="received", actor_type="shopify_hmac_verified",
        from_status=None, to_status="pending_policy_review",
        reason_code="tenant_bound", created_at=datetime.utcnow(),
    ))
    db.commit()
    with pytest.raises(ShopifyLocalPrivacyError):
        inspect_local_customer_export_counts(db, request_id=receipt.request_id)


def _authorize_synthetic_export(db, receipt):
    from datetime import datetime

    receipt.request_id = "a" * 64
    receipt.status = "pending_policy_review"
    db.add(ShopifyPrivacyAuditEvent(
        request_id=receipt.request_id,
        event_type="received", actor_type="shopify_hmac_verified",
        from_status=None, to_status="pending_policy_review",
        reason_code="tenant_bound", created_at=datetime.utcnow(),
    ))
    db.commit()


def test_encrypted_automation_fixture_exports_only_signed_customer_store_rows(
    scenario,
):
    from app.services.shopify_privacy_automation_fixture_export import (
        build_encrypted_shopify_automation_fixture,
    )

    db, receipt = scenario
    _authorize_synthetic_export(db, receipt)
    key = Fernet.generate_key()
    artifact = build_encrypted_shopify_automation_fixture(
        db, request_id=receipt.request_id, encryption_key=key,
        fixture_authorized=True,
    )
    assert artifact.fixture_only is True
    assert artifact.delivery_authorized is False
    assert artifact.fulfillment_complete is False
    assert artifact.request_id == receipt.request_id
    assert artifact.source_counts == {
        "audience_members": 1,
        "campaign_recipients": 1,
        "delivery_attempts": 1,
        "flow_recipients": 1,
        "flow_node_executions": 1,
    }
    encrypted = artifact.ciphertext
    assert b"PRIVATE_MESSAGE_store-a" not in encrypted
    assert b"PRIVATE_PROVIDER_store-a" not in encrypted
    document = json.loads(Fernet(key).decrypt(encrypted))
    assert document["request_id"] == receipt.request_id
    assert document["complete"] is False
    assert document["coverage"] == "explicitly_linked_rows_only"
    sources = document["sources"]
    assert sources["campaign_recipients"][0]["rendered_message"] == (
        "PRIVATE_MESSAGE_store-a"
    )
    assert sources["campaign_recipients"][0]["template_data"] == {
        "customer_address": "store-a",
    }
    assert sources["delivery_attempts"][0]["provider_message_id"] == (
        "PRIVATE_PROVIDER_store-a"
    )
    assert sources["flow_node_executions"][0]["extra_data"] == {
        "private_contact": "store-a",
    }
    # Customer exists in another shop; neither its campaign messages nor
    # merchant-wide campaign templates and flow trigger context may leak.
    assert "PRIVATE_MESSAGE_store-b" not in str(document)
    assert "PRIVATE_PROVIDER_store-c" not in str(document)
    assert "private checkout message" not in str(document)
    assert "trigger_context" not in str(document)
    assert db.query(AutomationDeliveryAttempt).count() == 3
    assert db.query(CustomerStoreProfile).count() == 3
    assert not db.dirty and not db.new and not db.deleted


def test_automation_fixture_requires_signed_request_and_exact_subject(scenario):
    from app.services.shopify_privacy_automation_fixture_export import (
        build_encrypted_shopify_automation_fixture,
    )
    from app.services.shopify_privacy_scoped_extraction import (
        ShopifyPrivacyExtractionError,
    )

    db, receipt = scenario
    receipt.request_id = "a" * 64
    db.commit()
    with pytest.raises(ShopifyPrivacyExtractionError, match="SCOPE_UNVERIFIED"):
        build_encrypted_shopify_automation_fixture(
            db, request_id=receipt.request_id,
            encryption_key=Fernet.generate_key(), fixture_authorized=True,
        )
    _authorize_synthetic_export(db, receipt)
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"email": "not-proof@example.com"}})
    )
    db.commit()
    with pytest.raises(ShopifyPrivacyExtractionError):
        build_encrypted_shopify_automation_fixture(
            db, request_id=receipt.request_id,
            encryption_key=Fernet.generate_key(), fixture_authorized=True,
        )


def test_automation_fixture_production_and_feature_gate_fail_before_queries(scenario):
    from app.services.shopify_privacy_automation_fixture_export import (
        build_encrypted_shopify_automation_fixture,
    )
    from app.services.shopify_privacy_scoped_extraction import (
        ShopifyPrivacyExtractionError,
    )

    db, receipt = scenario
    with pytest.raises(ShopifyPrivacyExtractionError, match="DISABLED"):
        build_encrypted_shopify_automation_fixture(
            db, request_id=receipt.request_id,
            encryption_key=Fernet.generate_key(),
        )
    # SQLite without a purely in-memory DB URL is not an eligible fixture.
    with Session(create_engine("sqlite://")) as non_fixture:
        with pytest.raises(ShopifyPrivacyExtractionError, match="DISABLED"):
            build_encrypted_shopify_automation_fixture(
                non_fixture, request_id="a" * 64,
                encryption_key=Fernet.generate_key(), fixture_authorized=True,
            )


def test_automation_fixture_rejects_duplicate_external_subject_link(scenario):
    from app.services.shopify_privacy_automation_fixture_export import (
        build_encrypted_shopify_automation_fixture,
    )
    from app.services.shopify_privacy_scoped_extraction import (
        ShopifyPrivacyExtractionError,
    )

    db, receipt = scenario
    _authorize_synthetic_export(db, receipt)
    other = Customer(
        organization_id=receipt.organization_id,
        name="SYNTHETIC_OTHER_CUSTOMER", phone="888",
    )
    db.add(other)
    db.flush()
    db.add(CustomerStoreProfile(
        organization_id=receipt.organization_id,
        store_id=receipt.store_id, customer_id=other.id,
        external_customer_id="700", currency="COP",
    ))
    db.commit()
    with pytest.raises(ShopifyPrivacyExtractionError, match="SCOPE_UNVERIFIED"):
        build_encrypted_shopify_automation_fixture(
            db, request_id=receipt.request_id,
            encryption_key=Fernet.generate_key(), fixture_authorized=True,
        )


def test_automation_fixture_denies_when_persisted_impact_disagrees(scenario):
    from dataclasses import replace
    from unittest.mock import patch
    from app.services.shopify_privacy_automation_provenance import (
        inspect_shopify_automation_privacy_impact,
    )
    from app.services.shopify_privacy_automation_fixture_export import (
        build_encrypted_shopify_automation_fixture,
    )
    from app.services.shopify_privacy_scoped_extraction import (
        ShopifyPrivacyExtractionError,
    )

    db, receipt = scenario
    _authorize_synthetic_export(db, receipt)
    real = inspect_shopify_automation_privacy_impact(db, receipt)
    corrupted = replace(real, campaign_recipients=999)
    with patch(
        "app.services.shopify_privacy_automation_fixture_export."
        "inspect_shopify_automation_privacy_impact",
        return_value=corrupted,
    ):
        with pytest.raises(ShopifyPrivacyExtractionError, match="SCOPE_CHANGED"):
            build_encrypted_shopify_automation_fixture(
                db, request_id=receipt.request_id,
                encryption_key=Fernet.generate_key(), fixture_authorized=True,
            )
