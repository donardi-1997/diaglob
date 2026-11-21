"""Synthetic-only test of independently permitted shop-scoped Copilot erasure."""
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.ai_agent import (
    AgentActionApproval, AgentChatMessage, AgentChatSession, AgentChatToolCall,
)
from app.models import (
    Organization, OrganizationMembership, ShopifyPrivacyAuditEvent, Store, User,
)
from app.services.shopify_privacy_attestations import b64encode
from app.services.shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError, policy_snapshot,
)
from tools.shopify_privacy_permit import mint_permit
from tools.shopify_privacy_legal_clearance import sign_case_clearance
import app.services.shopify_privacy_copilot_erasure as privacy

RID = "f" * 64
TECH = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
LEGAL = Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65)))


def public(key):
    return b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    ))


@pytest.fixture
def scenario(monkeypatch):
    monkeypatch.setenv("SHOPIFY_PRIVACY_PROCESSING_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256", policy_snapshot()[1])
    monkeypatch.setenv("SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY", public(TECH))
    monkeypatch.setenv("SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY", public(LEGAL))
    engine = create_engine(
        "sqlite://", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(name="Synthetic Copilot org", slug="copilot-erasure-org")
        foreign_org = Organization(name="Foreign org", slug="copilot-erasure-foreign")
        db.add_all([org, foreign_org])
        db.flush()
        user = User(email="copilot-privacy@example.test", name="Synthetic Owner")
        db.add(user)
        db.flush()
        member = OrganizationMembership(
            organization_id=org.id, user_id=user.id,
            role="owner", all_stores=True,
        )
        foreign_member = OrganizationMembership(
            organization_id=foreign_org.id, user_id=user.id,
            role="owner", all_stores=True,
        )
        db.add_all([member, foreign_member])
        db.flush()
        stores = []
        for n, owner in enumerate((org, org, foreign_org), start=1):
            store = Store(
                organization_id=owner.id, name=f"Shop {n}", slug=f"copilot-shop-{n}",
                shopify_domain=f"synthetic-copilot-{n}.myshopify.com",
                country_code="CO", currency="COP", timezone="UTC",
                active=True, deleted=False,
            )
            db.add(store)
            stores.append(store)
        db.flush()
        records = []
        for n, store in enumerate(stores):
            member_used = member if store.organization_id == org.id else foreign_member
            session = AgentChatSession(
                organization_id=store.organization_id,
                store_id=store.id, membership_id=member_used.id,
                user_id=user.id, title=f"SENSITIVE_TITLE_{n}",
                context={"buyer_email": f"private-{n}@example.test"},
                pending_capacity={"personal": f"secret-{n}"},
            )
            db.add(session)
            db.flush()
            message = AgentChatMessage(
                session_id=session.id, provider_role="user",
                text=f"SENSITIVE_TEXT_{n}",
                content=[{"text": f"SENSITIVE_CONTENT_{n}"}],
            )
            db.add(message)
            db.flush()
            approval = AgentActionApproval(
                organization_id=store.organization_id, store_id=store.id,
                membership_id=member_used.id, user_id=user.id,
                tool_name="orders.search", action="read", risk="low",
                confirmation="not_required", arguments_hash=f"{n + 1:064x}",
                arguments={"email": f"private-{n}@example.test"},
                expires_at=datetime.utcnow() + timedelta(hours=1),
            )
            db.add(approval)
            db.flush()
            tool_call = AgentChatToolCall(
                session_id=session.id, message_id=message.id,
                tool_use_id=f"use-{n}", tool_name="orders.search", action="read",
                approval_id=approval.id,
                arguments={"phone": f"private-phone-{n}"},
                result={"data": f"SENSITIVE_RESULT_{n}"},
            )
            db.add(tool_call)
            records.append((session.id, message.id, approval.id, tool_call))
        db.add(ShopifyPrivacyAuditEvent(
            request_id=RID, event_type="local_redaction_executed",
            reason_code="d" * 64, from_status="pending_policy_review",
            to_status="pending_policy_review",
            actor_type=privacy.ACTOR, created_at=datetime.utcnow(),
        ))
        db.commit()
        receipt = SimpleNamespace(topic="shop/redact", status="pending_policy_review")
        monkeypatch.setattr(privacy, "require_privacy_owner", lambda *a, **k: None)
        monkeypatch.setattr(privacy, "lock_shopify_privacy_scope", lambda *a, **k: None)
        monkeypatch.setattr(privacy, "owned_privacy_receipt", lambda *a, **k: receipt)
        yield db, org, stores, user, records, receipt
    engine.dispose()


def arguments(scenario):
    db, org, stores, user, *_ = scenario
    return dict(
        request_id=RID, organization_id=org.id,
        store_id=stores[0].id, user_id=user.id,
    )


def signed(scenario):
    args = arguments(scenario)
    db = scenario[0]
    plan = privacy.plan_shop_copilot_erasure(
        db, organization_id=args["organization_id"], store_id=args["store_id"],
    )
    digest = privacy.copilot_erasure_scope_digest(db, plan=plan,
        request_id=RID, organization_id=args["organization_id"], store_id=args["store_id"],
    )
    now = int(time.time())
    tech = mint_permit(
        TECH, now=now, ttl_seconds=600, operation="shop_copilot_erasure",
        request_id=RID, organization_id=args["organization_id"],
        store_id=args["store_id"], scope_sha256=digest,
    )
    legal = sign_case_clearance(
        LEGAL, now=now, ttl_seconds=600, request_id=RID,
        organization_id=args["organization_id"], store_id=args["store_id"],
        scope_sha256=digest, merchant_instruction_evidence_sha256="a" * 64,
        legal_review_evidence_sha256="b" * 64, reviewer_role="privacy_counsel",
    )
    return tech, legal


def test_preview_is_counts_and_digest_only_without_content(scenario):
    db, _, _, _, records, _ = scenario
    original = db.query(AgentChatSession).count()
    report = privacy.preview_shop_copilot_erasure(db, **arguments(scenario))
    assert report["counts"] == {
        "session": 1, "message": 1, "tool_call": 1, "approval": 1,
    }
    assert len(report["scope_sha256"]) == 64
    assert report["subject_level_attribution"] is False
    assert report["fulfillment_complete"] is False
    for value in ("SENSITIVE", "private-", "orders.search", "synthetic-copilot"):
        assert value not in str(report)
    assert db.query(AgentChatSession).count() == original
    assert not db.dirty


def test_requires_both_permits_before_any_sql_deletion(scenario):
    db = scenario[0]
    with pytest.raises(ShopifyPrivacyExecutionError, match="PRIVACY_EXECUTION_PERMIT_INVALID"):
        privacy.execute_shop_copilot_erasure(db, **arguments(scenario))
    tech, legal = signed(scenario)
    with pytest.raises(ShopifyPrivacyExecutionError, match="PRIVACY_CASE_LEGAL_CLEARANCE_REQUIRED"):
        privacy.execute_shop_copilot_erasure(
            db, **arguments(scenario), execution_permit=tech,
        )
    assert db.query(AgentChatSession).count() == 3
    assert db.query(AgentChatToolCall).count() == 3
    assert db.query(AgentActionApproval).count() == 3


def test_deletes_only_target_store_and_does_not_touch_other_store_or_tenant(scenario):
    db, org, stores, user, records, _ = scenario
    tech, legal = signed(scenario)
    out = privacy.execute_shop_copilot_erasure(
        db, **arguments(scenario), execution_permit=tech, legal_clearance_token=legal,
    )
    assert out["copilot_erasure_executed"] is True
    assert out["counts"] == {"session": 1, "message": 1, "tool_call": 1, "approval": 1}
    assert out["external_ai_provider_deletion_verified"] is False
    assert out["fulfillment_complete"] is False
    for model, index in (
        (AgentChatSession, 0), (AgentChatMessage, 1), (AgentActionApproval, 2),
    ):
        assert db.get(model, records[0][index]) is None
        assert db.get(model, records[1][index]) is not None
        assert db.get(model, records[2][index]) is not None
    assert db.get(AgentChatToolCall, records[0][3].id) is None
    assert db.get(AgentChatToolCall, records[1][3].id) is not None
    assert db.query(ShopifyPrivacyAuditEvent).filter_by(
        event_type=privacy.EXECUTED_EVENT,
    ).count() == 1
    again = privacy.execute_shop_copilot_erasure(
        db, **arguments(scenario), execution_permit=tech,
        legal_clearance_token=legal,
    )
    assert again["idempotent"] is True


def test_customer_redact_cannot_delete_store_wide_copilot(scenario):
    db, _, _, _, _, receipt = scenario
    receipt.topic = "customers/redact"
    tech, legal = signed(scenario)
    with pytest.raises(ShopifyPrivacyExecutionError, match="COPILOT_SHOP_REDACT_ONLY"):
        privacy.execute_shop_copilot_erasure(
            db, **arguments(scenario), execution_permit=tech,
            legal_clearance_token=legal,
        )
    assert db.query(AgentChatSession).count() == 3


def test_new_message_invalidates_signed_scope_without_mutations(scenario):
    db, _, _, _, records, _ = scenario
    tech, legal = signed(scenario)
    db.add(AgentChatMessage(
        session_id=records[0][0], provider_role="assistant",
        text="ADDED_AFTER_PERMIT", content=[{"text": "SENSITIVE"}],
    ))
    db.commit()
    with pytest.raises(ShopifyPrivacyExecutionError, match="PRIVACY_EXECUTION_PERMIT_SCOPE_MISMATCH"):
        privacy.execute_shop_copilot_erasure(
            db, **arguments(scenario), execution_permit=tech,
            legal_clearance_token=legal,
        )
    assert db.query(AgentChatSession).count() == 3


def test_cross_store_approval_reference_fails_closed(scenario):
    db, _, _, _, records, _ = scenario
    records[0][3].approval_id = records[1][2]
    db.commit()
    with pytest.raises(ShopifyPrivacyExecutionError, match="COPILOT_CROSS_STORE_REFERENCE"):
        privacy.preview_shop_copilot_erasure(db, **arguments(scenario))
    assert db.query(AgentChatSession).count() == 3


def test_foreign_tool_call_using_target_message_fails_closed(scenario):
    db, _, _, _, records, _ = scenario
    records[1][3].message_id = records[0][1]
    db.commit()
    with pytest.raises(ShopifyPrivacyExecutionError, match="COPILOT_CROSS_STORE_MESSAGE_REFERENCE"):
        privacy.preview_shop_copilot_erasure(db, **arguments(scenario))
    assert db.query(AgentChatMessage).count() == 3


def test_foreign_tool_call_using_approved_target_approval_fails_closed(scenario):
    db, _, _, _, records, _ = scenario
    records[1][3].approval_id = records[0][2]
    db.commit()
    with pytest.raises(ShopifyPrivacyExecutionError, match="COPILOT_SHARED_APPROVAL_REFERENCE"):
        privacy.preview_shop_copilot_erasure(db, **arguments(scenario))
    assert db.query(AgentChatSession).count() == 3
