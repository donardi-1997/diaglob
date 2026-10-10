"""Synthetic-only checks for merchant Copilot storefront privacy inventory."""
from dataclasses import asdict
from datetime import datetime, timedelta
import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.model_domains.ai_agent import (
    AgentActionApproval, AgentChatMessage, AgentChatSession,
    AgentChatToolCall,
)
from app.models import (
    Organization, OrganizationMembership, ShopifyPrivacyRequest, Store, User,
)
from app.services.shopify_privacy_copilot_impact import (
    inspect_shopify_copilot_privacy_impact,
)
from app.services.shopify_privacy_scope_preview import ShopifyPrivacyScopeError
from app.shopify_security import encrypt_shopify_secret


@pytest.fixture
def scenario(monkeypatch):
    monkeypatch.setenv("SHOPIFY_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        a = Organization(name="Synthetic A", slug="synthetic-a")
        b = Organization(name="Synthetic B", slug="synthetic-b")
        db.add_all([a, b])
        db.flush()
        user = User(email="merchant@example.test", name="Merchant")
        user_b = User(email="merchant-b@example.test", name="Merchant B")
        db.add_all([user, user_b])
        db.flush()
        membership_a = OrganizationMembership(
            user_id=user.id, organization_id=a.id,
            role="manager", all_stores=True,
        )
        membership_b = OrganizationMembership(
            user_id=user_b.id, organization_id=b.id,
            role="manager", all_stores=True,
        )
        db.add_all([membership_a, membership_b])
        db.flush()
        stores = []
        for suffix, org in (("a", a), ("b", a), ("c", b)):
            store = Store(
                organization_id=org.id, name=f"Store {suffix}",
                slug=f"store-{suffix}", country_code="CO",
                currency="COP", timezone="UTC",
                shopify_domain=f"{suffix}.myshopify.com",
            )
            db.add(store)
            stores.append(store)
        db.flush()
        for i, store in enumerate(stores):
            membership = membership_a if store.organization_id == a.id else membership_b
            session = AgentChatSession(
                organization_id=store.organization_id,
                store_id=store.id, user_id=membership.user_id,
                membership_id=membership.id,
                title=f"PRIVATE_SESSION_TITLE_{i}",
                context={"copied_customer_email": f"buyer{i}@example.test"},
            )
            db.add(session)
            db.flush()
            message = AgentChatMessage(
                session_id=session.id, provider_role="user",
                text=f"PRIVATE_CUSTOMER_CONTENT_{i}",
                content=[{"text": f"PRIVATE_STRUCTURED_CONTENT_{i}"}],
            )
            db.add(message)
            db.flush()
            approval = AgentActionApproval(
                organization_id=store.organization_id,
                store_id=store.id, membership_id=membership.id,
                user_id=membership.user_id,
                tool_name="orders.list", action="read", risk="low",
                confirmation="not_required", arguments_hash=f"{i:064x}",
                arguments={"customer_email": f"buyer{i}@example.test"},
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
            db.add(approval)
            db.flush()
            db.add(AgentChatToolCall(
                session_id=session.id, message_id=message.id,
                tool_use_id=f"use-{i}", tool_name="orders.list",
                action="read", approval_id=approval.id,
                arguments={"customer_phone": f"synthetic{i}"},
                result={"buyer": f"PRIVATE_RESULT_{i}"},
            ))
        receipt = ShopifyPrivacyRequest(
            request_id="f" * 64,
            topic="customers/data_request",
            shop_id="synthetic-test-shop",
            shop_domain=stores[0].shopify_domain,
            organization_id=a.id, store_id=stores[0].id,
            selector_encrypted=encrypt_shopify_secret(
                json.dumps({"customer": {"id": 700}})
            ),
        )
        db.add(receipt)
        db.commit()
        yield db, receipt
    engine.dispose()


def _assert_store_a_counts(preview):
    assert (
        preview.store_sessions_for_review,
        preview.store_messages_for_review,
        preview.store_tool_calls_for_review,
        preview.store_action_approvals_for_review,
    ) == (1, 1, 1, 1)
    assert preview.content_review_required is True
    assert preview.complete is False
    assert preview.customer_attribution == (
        "unavailable_no_verified_customer_relationship"
    )


def test_customer_data_request_is_store_wide_only_not_buyer_attribution(scenario):
    db, receipt = scenario
    preview = inspect_shopify_copilot_privacy_impact(db, receipt)
    _assert_store_a_counts(preview)
    output = repr(asdict(preview))
    for confidential in (
        "buyer0@", "PRIVATE_CUSTOMER_CONTENT", "PRIVATE_SESSION_TITLE",
        "PRIVATE_STRUCTURED_CONTENT", "PRIVATE_RESULT", "synthetic0",
    ):
        assert confidential not in output
    assert not db.dirty
    assert not db.deleted


def test_customer_redact_does_not_attribute_merchant_chat_to_customer(scenario):
    db, receipt = scenario
    receipt.topic = "customers/redact"
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"id": 999999}})
    )
    preview = inspect_shopify_copilot_privacy_impact(db, receipt)
    _assert_store_a_counts(preview)
    assert preview.topic == "customers/redact"


def test_shop_redact_counts_only_requested_store_not_other_stores(scenario):
    db, receipt = scenario
    receipt.topic = "shop/redact"
    receipt.selector_encrypted = "no-selector-required"
    preview = inspect_shopify_copilot_privacy_impact(db, receipt)
    _assert_store_a_counts(preview)
    assert preview.topic == "shop/redact"


def test_tampered_domain_and_tenant_mapping_rejected(scenario):
    db, receipt = scenario
    receipt.shop_domain = "other.myshopify.com"
    with pytest.raises(ShopifyPrivacyScopeError, match="STORE_MISMATCH"):
        inspect_shopify_copilot_privacy_impact(db, receipt)
    receipt.shop_domain = "a.myshopify.com"
    receipt.organization_id = None
    with pytest.raises(ShopifyPrivacyScopeError, match="TENANT_UNRESOLVED"):
        inspect_shopify_copilot_privacy_impact(db, receipt)


def test_invalid_shopify_event_cannot_probe_copilot_store(scenario):
    db, receipt = scenario
    receipt.topic = "unknown/topic"
    with pytest.raises(ShopifyPrivacyScopeError, match="UNSUPPORTED_PRIVACY_TOPIC"):
        inspect_shopify_copilot_privacy_impact(db, receipt)


def test_changing_buyer_identifier_does_not_change_store_wide_copilot_counts(
    scenario,
):
    db, receipt = scenario
    first = inspect_shopify_copilot_privacy_impact(db, receipt)
    receipt.selector_encrypted = encrypt_shopify_secret(
        json.dumps({"customer": {"id": 999999999}})
    )
    unknown_buyer = inspect_shopify_copilot_privacy_impact(db, receipt)
    assert unknown_buyer == first
    assert unknown_buyer.complete is False
    assert unknown_buyer.content_review_required is True
