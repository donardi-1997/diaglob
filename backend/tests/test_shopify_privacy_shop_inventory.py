"""Synthetic SQLite checks for the per-shop effective privacy inventory.

The inventory orchestrates verified read-only inspectors: counts and coverage
labels only, strict tenant isolation, and a permanently fail-closed posture.
No personal value (name, phone, chat title, message, object key, email) may
appear in any result, and no area may be reported as approved or complete.
"""
import json
from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.shopify_privacy_backlog import (
    get_shopify_privacy_case_subprocessors,
    get_shopify_privacy_shop_inventory,
)
from app.db import Base
from app.model_domains.ai_agent import AgentChatMessage, AgentChatSession
from app.model_domains.knowledge import KnowledgeBase, KnowledgeSource
from app.model_domains.paddle_billing import PaddleBillingCustomer
from app.model_domains.tenancy import knowledge_base_stores
from app.models import (
    AutomationAudienceMember,
    AutomationCampaign,
    CommerceConnection,
    Customer,
    CustomerStoreProfile,
    Organization,
    OrganizationMembership,
    PaymentConnection,
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    Store,
    User,
)
from app.services.shopify_privacy_controls import ShopifyPrivacyControlError
from app.services.shopify_privacy_shop_inventory import (
    build_shopify_privacy_shop_inventory,
)
from app.shopify_security import encrypt_shopify_secret

_REQUIRED_AREAS = {
    "local_structured_records",
    "ai_and_unstructured_content",
    "automation_and_queues",
    "files_and_object_storage",
    "external_processors",
    "retention_and_legal_holds",
    "backups_and_reingestion",
}

_REQUIRED_BLOCKERS = {
    "RECORD_PROVENANCE_INCOMPLETE",
    "UNSTRUCTURED_SUBJECT_LINKAGE_UNVERIFIED",
    "QUEUED_PAYLOAD_COVERAGE_UNVERIFIED",
    "EXTERNAL_PROCESSOR_COVERAGE_UNVERIFIED",
    "LEGAL_RETENTION_POLICY_NOT_APPROVED",
    "BACKUP_RESTORE_COVERAGE_UNVERIFIED",
}


@pytest.fixture
def scenario(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org_a = Organization(name="Org A", slug="org-a", plan="starter")
        org_b = Organization(name="Org B", slug="org-b", plan="starter")
        db.add_all([org_a, org_b])
        db.flush()
        user_a = User(email="manager-a@example.test", name="Manager A")
        user_b = User(email="manager-b@example.test", name="Manager B")
        db.add_all([user_a, user_b])
        db.flush()
        membership_a = OrganizationMembership(
            user_id=user_a.id, organization_id=org_a.id,
            role="manager", all_stores=True,
        )
        membership_b = OrganizationMembership(
            user_id=user_b.id, organization_id=org_b.id,
            role="manager", all_stores=True,
        )
        db.add_all([membership_a, membership_b])
        db.flush()

        stores = {}
        for suffix, org in (("a", org_a), ("b", org_a), ("c", org_b)):
            store = Store(
                organization_id=org.id, name=f"Store {suffix}",
                slug=f"store-{suffix}", country_code="CO", currency="COP",
                timezone="UTC", shopify_domain=f"{suffix}.myshopify.com",
            )
            db.add(store)
            stores[suffix] = store
        db.flush()

        shared = Customer(
            organization_id=org_a.id,
            name="PII_SECRET_BUYER_NAME", phone="+573001112233",
        )
        foreign = Customer(
            organization_id=org_b.id,
            name="PII_FOREIGN_BUYER_NAME", phone="+573009998888",
        )
        db.add_all([shared, foreign])
        db.flush()
        for store, customer in (
            (stores["a"], shared), (stores["b"], shared), (stores["c"], foreign),
        ):
            db.add(CustomerStoreProfile(
                organization_id=store.organization_id, store_id=store.id,
                customer_id=customer.id, external_customer_id="700",
                currency="COP",
            ))

        for suffix in ("a", "b"):
            store = stores[suffix]
            campaign = AutomationCampaign(
                organization_id=store.organization_id, store_id=store.id,
                name=f"campaign-{suffix}", timezone="UTC",
                message_template="PII_SECRET_TEMPLATE",
            )
            db.add(campaign)
            db.flush()
            db.add(AutomationAudienceMember(
                automation_id=campaign.id, customer_id=shared.id,
            ))
            membership = membership_a
            session = AgentChatSession(
                organization_id=store.organization_id, store_id=store.id,
                user_id=membership.user_id, membership_id=membership.id,
                title=f"PII_CHAT_TITLE_{suffix.upper()}",
                context={"copied_customer_email": "buyer@example.test"},
            )
            db.add(session)
            db.flush()
            db.add(AgentChatMessage(
                session_id=session.id, provider_role="user",
                text=f"PII_CHAT_MESSAGE_{suffix.upper()}",
                content=[{"text": "PII_STRUCTURED_CONTENT"}],
            ))

        kb_org = KnowledgeBase(
            organization_id=org_a.id, name="KB Org Wide", scope="organization",
        )
        kb_selected = KnowledgeBase(
            organization_id=org_a.id, name="KB For Store B",
            scope="selected_stores",
        )
        db.add_all([kb_org, kb_selected])
        db.flush()
        db.execute(knowledge_base_stores.insert().values(
            knowledge_base_id=kb_selected.id, store_id=stores["b"].id,
        ))
        db.add_all([
            KnowledgeSource(
                organization_id=org_a.id, knowledge_base_id=kb_org.id,
                name="Org Doc", s3_bucket="diaglob-bucket",
                s3_key="organizations/1/knowledge-bases/1/documents/org-doc.pdf",
            ),
            KnowledgeSource(
                organization_id=org_a.id, knowledge_base_id=kb_selected.id,
                name="Store B Doc", s3_bucket="diaglob-bucket",
                s3_key="organizations/1/knowledge-bases/2/documents/store-b-doc.pdf",
            ),
        ])

        db.add_all([
            CommerceConnection(
                organization_id=org_a.id, store_id=stores["a"].id,
                provider="shopify", external_store_url="a.myshopify.com",
                status="connected",
            ),
            CommerceConnection(
                organization_id=org_a.id, store_id=stores["b"].id,
                provider="nuvemshop", external_store_url="b.nuvemshop.com",
                status="connected",
            ),
            PaymentConnection(
                organization_id=org_a.id, store_id=stores["a"].id,
                provider="nequi", status="connected",
            ),
            PaddleBillingCustomer(
                customer_id="cusc_test_a", organization_id=org_a.id,
                email="billing-secret@example.com",
            ),
        ])

        receipt_customer = ShopifyPrivacyRequest(
            request_id="a" * 64,
            topic="customers/data_request",
            shop_id="111", shop_domain="a.myshopify.com",
            organization_id=org_a.id, store_id=stores["a"].id,
            selector_encrypted=encrypt_shopify_secret(
                json.dumps({"customer": {"id": 700}})
            ),
        )
        receipt_shop = ShopifyPrivacyRequest(
            request_id="b" * 64,
            topic="shop/redact",
            shop_id="222", shop_domain="b.myshopify.com",
            organization_id=org_a.id, store_id=stores["b"].id,
            selector_encrypted=encrypt_shopify_secret(json.dumps({})),
        )
        db.add_all([receipt_customer, receipt_shop])
        db.flush()
        for receipt in (receipt_customer, receipt_shop):
            db.add(ShopifyPrivacyAuditEvent(
                request_id=receipt.request_id,
                event_type="received", actor_type="shopify_hmac_verified",
                from_status=None, to_status="pending_policy_review",
                reason_code="tenant_bound", created_at=datetime.utcnow(),
            ))
        db.commit()
        yield db, receipt_customer, receipt_shop
    engine.dispose()


def _assert_fail_closed(result):
    assert set(result["areas"]) >= _REQUIRED_AREAS
    assert _REQUIRED_BLOCKERS <= set(result["blockers"])
    assert result["signed_intake_verified"] is True
    assert result["shop_identity_verified"] is True
    assert result["independent_review_completed"] is False
    assert result["ready_for_live_privacy_processing"] is False
    assert result["requires_manual_review"] is True
    assert result["fulfillment_authorized"] is False
    assert result["fulfillment_complete"] is False


def _assert_no_pii(result):
    rendered = str(result)
    for secret in (
        "PII_SECRET_BUYER_NAME",
        "PII_FOREIGN_BUYER_NAME",
        "+573001112233",
        "+573009998888",
        "PII_CHAT_TITLE",
        "PII_CHAT_MESSAGE",
        "PII_SECRET_TEMPLATE",
        "billing-secret@example.com",
        "store-b-doc.pdf",
        "org-doc.pdf",
        "a.myshopify.com",
        "buyer@example.test",
    ):
        assert secret not in rendered


def test_customer_scope_inventory_covers_all_areas_fail_closed(scenario):
    db, receipt_customer, _ = scenario
    result = build_shopify_privacy_shop_inventory(
        db, request_id=receipt_customer.request_id,
    )
    _assert_fail_closed(result)
    _assert_no_pii(result)
    assert result["shop_scope"] == "customer_scope_preview_only"

    structured = result["areas"]["local_structured_records"]
    assert structured["counts"] == {
        "customer_profiles": 1, "orders": 0,
        "conversations": 0, "conversational_checkouts": 0,
    }
    # Store b holds another profile of the very same shared customer.
    assert structured["shared_customers_protected"] == 1
    assert structured["local_execution_disabled_by_default"] is True

    ai = result["areas"]["ai_and_unstructured_content"]
    assert ai["coverage"] == "uncovered"
    assert ai["copilot_store_wide"]["sessions"] == 1
    assert ai["copilot_store_wide"]["messages"] == 1
    assert ai["copilot_store_wide"]["customer_attribution"] == (
        "unavailable_no_verified_customer_relationship"
    )
    knowledge = ai["knowledge_and_files"]
    assert knowledge["knowledge_bases_organization_total"] == 2
    assert knowledge["knowledge_bases_visible_to_store"] == 1
    assert knowledge["knowledge_bases_selected_for_store"] == 0
    assert knowledge["knowledge_sources_organization_total"] == 2
    assert knowledge["knowledge_sources_visible_to_store"] == 1
    assert knowledge["content_read"] is False
    assert ai["legacy_attribution"]["live_export_authorized"] is False

    automation = result["areas"]["automation_and_queues"]
    assert automation["coverage"] == "uncovered"
    assert automation["counts"]["audience_members"] == 1
    assert automation["attribution"] == "verified_external_customer_id"
    assert automation["legacy_payload_export"] == "not_exported"

    files = result["areas"]["files_and_object_storage"]
    assert files["knowledge_sources_organization_total"] == 2
    assert files["knowledge_sources_visible_to_store"] == 1
    assert files["object_keys_read"] is False
    assert files["objects_exported_or_deleted"] is False

    processors = result["areas"]["external_processors"]
    assert set(processors["active_processors"]) == {
        "shopify_admin_api", "nequi_payments", "paddle_billing",
        "aws_bedrock", "files_and_object_storage",
    }
    assert processors["active_processor_count"] == 5

    retention = result["areas"]["retention_and_legal_holds"]
    assert retention["independent_legal_approval"] is False
    assert retention["destruction_authorized"] is False

    backups = result["areas"]["backups_and_reingestion"]
    assert backups["restore_verified"] is False
    assert backups["fulfillment_complete"] is False


def test_shop_scope_inventory_uses_store_b_only(scenario):
    db, _, receipt_shop = scenario
    result = build_shopify_privacy_shop_inventory(
        db, request_id=receipt_shop.request_id,
    )
    _assert_fail_closed(result)
    _assert_no_pii(result)
    assert result["shop_scope"] == "shop_scope_preview_only"

    ai = result["areas"]["ai_and_unstructured_content"]
    # Store a's Copilot session must never leak into store b's inventory.
    assert ai["copilot_store_wide"]["sessions"] == 1
    assert ai["knowledge_and_files"]["knowledge_bases_visible_to_store"] == 2
    assert ai["knowledge_and_files"]["knowledge_bases_selected_for_store"] == 1
    assert ai["knowledge_and_files"]["knowledge_sources_visible_to_store"] == 2

    automation = result["areas"]["automation_and_queues"]
    assert automation["counts"]["audience_members"] == 1
    assert automation["attribution"] == "verified_store_scope"

    processors = result["areas"]["external_processors"]
    assert set(processors["active_processors"]) == {
        "nuvemshop_admin_api", "paddle_billing",
        "aws_bedrock", "files_and_object_storage",
    }
    assert "shopify_admin_api" not in processors["active_processors"]
    assert "nequi_payments" not in processors["active_processors"]


def test_inventory_requires_signed_intake(scenario):
    db, _, _ = scenario
    unsigned = ShopifyPrivacyRequest(
        request_id="c" * 64,
        topic="customers/data_request",
        shop_id="333", shop_domain="z.myshopify.com",
        organization_id=None, store_id=None,
        selector_encrypted=encrypt_shopify_secret(json.dumps({})),
    )
    db.add(unsigned)
    db.commit()
    with pytest.raises(ShopifyPrivacyControlError) as exc:
        build_shopify_privacy_shop_inventory(db, request_id=unsigned.request_id)
    assert str(exc.value) == "SIGNED_INTAKE_REQUIRED"


def test_inventory_endpoints_require_internal_secret(scenario, monkeypatch):
    db, receipt_customer, _ = scenario
    monkeypatch.setenv("DIAGLOB_INTERNAL_SECRET", "synthetic-test-internal-secret")

    with pytest.raises(HTTPException) as unauthorized:
        get_shopify_privacy_shop_inventory(
            request_id=receipt_customer.request_id,
            x_internal_secret="wrong", db=db,
        )
    assert unauthorized.value.status_code == 401

    with pytest.raises(HTTPException) as missing:
        get_shopify_privacy_shop_inventory(
            request_id="0" * 64,
            x_internal_secret="synthetic-test-internal-secret", db=db,
        )
    assert missing.value.status_code == 404

    result = get_shopify_privacy_shop_inventory(
        request_id=receipt_customer.request_id,
        x_internal_secret="synthetic-test-internal-secret", db=db,
    )
    _assert_fail_closed(result)
    _assert_no_pii(result)

    processors = get_shopify_privacy_case_subprocessors(
        request_id=receipt_customer.request_id,
        x_internal_secret="synthetic-test-internal-secret", db=db,
    )
    assert processors["manifest_entry_count"] == 16
    assert processors["active_processor_count"] == 5
    assert processors["controls_without_manifest_entry"] == []
    assert processors["fulfillment_complete"] is False
    _assert_no_pii(processors)
