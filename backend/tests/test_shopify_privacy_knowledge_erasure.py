"""shop/redact must erase knowledge bases owned only by the redacted store."""
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.services.shopify_privacy_knowledge_erasure as erasure
from app.db import Base
from app.model_domains.knowledge import KnowledgeBase
from app.model_domains.tenancy import knowledge_base_stores
from app.models import ShopifyPrivacyAuditEvent
from app.services.shopify_privacy_attestations import b64encode
from app.services.shopify_privacy_execution_authorization import ShopifyPrivacyExecutionError, policy_snapshot
from tools.shopify_privacy_permit import mint_permit
from tools.shopify_privacy_legal_clearance import sign_case_clearance

ORG, STORE, OTHER = 1, 10, 11
RID = "a" * 64

# Fixed synthetic TEST-ONLY keys; these are not production credentials.
_TECH = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
_LEGAL = Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65)))


def _public(key):
    return b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw))


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("SHOPIFY_PRIVACY_PROCESSING_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256", policy_snapshot()[1])
    monkeypatch.setenv("SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY", _public(_TECH))
    monkeypatch.setenv("SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY", _public(_LEGAL))
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = Session(engine)
    for kb_id, scope, stores in (
        (1, "selected_stores", [STORE]),          # exclusive -> erase
        (2, "selected_stores", [STORE, OTHER]),   # shared -> keep
        (3, "selected_stores", [OTHER]),          # other store -> untouched
        (4, "organization", []),                  # org-wide -> untouched
    ):
        session.add(KnowledgeBase(id=kb_id, organization_id=ORG, name=f"kb{kb_id}", scope=scope))
        session.flush()
        for store_id in stores:
            session.execute(insert(knowledge_base_stores).values(
                knowledge_base_id=kb_id, store_id=store_id))
    session.add(KnowledgeBase(id=5, organization_id=2, name="foreign", scope="selected_stores"))
    session.flush()
    session.execute(insert(knowledge_base_stores).values(knowledge_base_id=5, store_id=STORE))
    session.commit()
    receipt = SimpleNamespace(topic="shop/redact", status="pending_policy_review")
    monkeypatch.setattr(erasure, "require_privacy_owner", lambda *a, **k: None)
    monkeypatch.setattr(erasure, "require_execution_policy", lambda: None)
    monkeypatch.setattr(erasure, "lock_shopify_privacy_scope", lambda *a: None)
    monkeypatch.setattr(erasure, "owned_privacy_receipt", lambda *a, **k: receipt)
    yield session, receipt
    session.close()
    engine.dispose()


def _redacted(session):
    session.add(ShopifyPrivacyAuditEvent(
        request_id=RID, event_type="local_redaction_executed", from_status="x", to_status="x",
        reason_code="d" * 64, actor_type="independently_permitted_worker",
        created_at=datetime.utcnow()))
    session.commit()


def _signed_permits(session):
    plan = erasure.plan_shop_knowledge_erasure(
        session, organization_id=ORG, store_id=STORE)
    digest = erasure.knowledge_erasure_scope_digest(
        session, request_id=RID, organization_id=ORG, store_id=STORE, plan=plan)
    now = int(time.time())
    technical = mint_permit(
        _TECH, now=now, ttl_seconds=600, operation="shop_knowledge_erasure",
        request_id=RID, organization_id=ORG, store_id=STORE,
        scope_sha256=digest,
    )
    legal = sign_case_clearance(
        _LEGAL, now=now, ttl_seconds=600, request_id=RID,
        organization_id=ORG, store_id=STORE, scope_sha256=digest,
        merchant_instruction_evidence_sha256="a" * 64,
        legal_review_evidence_sha256="b" * 64,
        reviewer_role="privacy_counsel",
    )
    return technical, legal


def _run(session, deleter):
    # No credentials are minted when the prerequisite SQL step is absent.
    has_local = erasure._audit_exists(session, RID, "local_redaction_executed")
    tech, legal = _signed_permits(session) if has_local else (None, None)
    return erasure.execute_shop_knowledge_erasure(
        session, request_id=RID, organization_id=ORG, store_id=STORE, user_id=7,
        execution_permit=tech, legal_clearance_token=legal,
        delete_knowledge_base=deleter)


def test_plan_only_includes_bases_exclusive_to_the_store(db):
    session, _ = db
    plan = erasure.plan_shop_knowledge_erasure(session, organization_id=ORG, store_id=STORE)
    assert plan == {"exclusive_knowledge_base_ids": [1], "shared_knowledge_bases_kept": 1}


def test_requires_local_redaction_first(db):
    session, _ = db
    with pytest.raises(ShopifyPrivacyExecutionError, match="LOCAL_REDACTION_REQUIRED_FIRST"):
        _run(session, lambda *a: pytest.fail("must not delete"))


def test_requires_shop_redact_topic(db):
    session, receipt = db
    receipt.topic = "customers/redact"
    _redacted(session)
    with pytest.raises(ShopifyPrivacyExecutionError, match="SHOP_REDACT_TOPIC_REQUIRED"):
        _run(session, lambda *a: pytest.fail("must not delete"))


def test_erases_exclusive_base_and_is_idempotent(db):
    session, _ = db
    _redacted(session)
    deleted = []
    result = _run(session, lambda _db, kb: deleted.append(kb.id))
    assert deleted == [1]
    assert result["knowledge_bases_deleted"] == 1
    assert result["shared_knowledge_bases_kept"] == 1
    assert result["review_required"] is True
    assert result["fulfillment_complete"] is False
    again = _run(session, lambda *a: pytest.fail("must not delete twice"))
    assert again["idempotent"] is True


def test_external_failure_leaves_step_open_for_manual_reconciliation(db):
    session, _ = db
    _redacted(session)

    def failing(_db, _kb):
        raise RuntimeError("bedrock unavailable")

    with pytest.raises(RuntimeError):
        _run(session, failing)
    assert session.query(ShopifyPrivacyAuditEvent).filter_by(
        event_type=erasure.EXECUTED_EVENT).count() == 0


def test_original_authorized_kb_plan_is_recorded_before_any_external_delete(db):
    session, _ = db
    _redacted(session)
    approved = erasure.plan_shop_knowledge_erasure(
        session, organization_id=ORG, store_id=STORE)
    expected_digest = erasure.knowledge_erasure_scope_digest(
        session, request_id=RID, organization_id=ORG, store_id=STORE,
        plan=approved,
    )
    before_call = []

    def delete(_db, kb):
        marker = session.query(ShopifyPrivacyAuditEvent).filter_by(
            request_id=RID, event_type=erasure.STARTED_EVENT,
        ).one()
        assert marker.reason_code == expected_digest
        assert session.query(ShopifyPrivacyAuditEvent).filter_by(
            request_id=RID, event_type=erasure.EXECUTED_EVENT,
        ).count() == 0
        before_call.append(kb.id)

    result = _run(session, delete)
    assert before_call == [1]
    assert result["knowledge_erasure_executed"] is True
    assert session.query(ShopifyPrivacyAuditEvent).filter_by(
        event_type=erasure.STARTED_EVENT,
    ).count() == 1
    assert session.query(ShopifyPrivacyAuditEvent).filter_by(
        event_type=erasure.EXECUTED_EVENT,
    ).count() == 1


def test_interrupted_kb_deletion_must_not_retry_unreviewed(db):
    session, _ = db
    _redacted(session)
    attempted = []
    def failing(_db, kb):
        attempted.append(kb.id)
        raise RuntimeError("synthetic remote failure")

    with pytest.raises(RuntimeError, match="synthetic"):
        _run(session, failing)
    assert attempted == [1]
    marker = session.query(ShopifyPrivacyAuditEvent).filter_by(
        event_type=erasure.STARTED_EVENT,
    ).one()
    assert len(marker.reason_code) == 64
    assert session.query(ShopifyPrivacyAuditEvent).filter_by(
        event_type=erasure.EXECUTED_EVENT,
    ).count() == 0
    with pytest.raises(ShopifyPrivacyExecutionError, match="INTERRUPTED_RECONCILIATION_REQUIRED"):
        _run(session, lambda *_: pytest.fail("never retry unchecked external deletion"))


def test_partial_kb_batch_commits_do_not_falsely_certify_erasure(db):
    session, _ = db
    _redacted(session)
    session.add(KnowledgeBase(
        id=6, organization_id=ORG, name="second-exclusive",
        scope="selected_stores",
    ))
    session.flush()
    session.execute(insert(knowledge_base_stores).values(
        knowledge_base_id=6, store_id=STORE,
    ))
    session.commit()
    deleted = []
    def partial_delete(_db, kb):
        deleted.append(kb.id)
        if len(deleted) == 1:
            session.delete(kb)
            # The real deletion orchestrator commits DB after remote cleanup.
            session.commit()
            return
        raise RuntimeError("synthetic second-resource outage")

    with pytest.raises(RuntimeError, match="second-resource"):
        _run(session, partial_delete)
    assert deleted == [1, 6]
    assert session.query(KnowledgeBase).filter_by(id=1).first() is None
    assert session.query(KnowledgeBase).filter_by(id=6).first() is not None
    assert session.query(ShopifyPrivacyAuditEvent).filter_by(
        event_type=erasure.EXECUTED_EVENT,
    ).count() == 0
    assert session.query(ShopifyPrivacyAuditEvent).filter_by(
        event_type=erasure.STARTED_EVENT,
    ).count() == 1
    # A new plan after the first SQL deletion no longer matches the original
    # approved digest. Never silently claim the whole batch was verified.
    with pytest.raises(ShopifyPrivacyExecutionError, match="INTERRUPTED_RECONCILIATION_REQUIRED"):
        _run(session, lambda *_: pytest.fail("must not run unchecked retry"))


def test_external_knowledge_erasure_requires_separate_technical_and_legal_permits(db):
    session, _ = db
    _redacted(session)
    deleted = []
    with pytest.raises(ShopifyPrivacyExecutionError, match="PRIVACY_EXECUTION_PERMIT_INVALID"):
        erasure.execute_shop_knowledge_erasure(
            session, request_id=RID, organization_id=ORG, store_id=STORE, user_id=7,
            delete_knowledge_base=lambda _db, kb: deleted.append(kb.id),
        )
    technical, legal = _signed_permits(session)
    with pytest.raises(ShopifyPrivacyExecutionError, match="PRIVACY_CASE_LEGAL_CLEARANCE_REQUIRED"):
        erasure.execute_shop_knowledge_erasure(
            session, request_id=RID, organization_id=ORG, store_id=STORE, user_id=7,
            execution_permit=technical, delete_knowledge_base=lambda _db, kb: deleted.append(kb.id),
        )
    assert deleted == []


def test_changing_kb_scope_after_signing_revokes_both_permits(db):
    session, _ = db
    _redacted(session)
    technical, legal = _signed_permits(session)
    # A second store joins what was exclusive after approval; no base may be
    # deleted using the old digest and changing provenance never expands scope.
    session.execute(insert(knowledge_base_stores).values(
        knowledge_base_id=1, store_id=OTHER,
    ))
    session.commit()
    deleted = []
    with pytest.raises(ShopifyPrivacyExecutionError, match="PRIVACY_EXECUTION_PERMIT_SCOPE_MISMATCH"):
        erasure.execute_shop_knowledge_erasure(
            session, request_id=RID, organization_id=ORG, store_id=STORE, user_id=7,
            execution_permit=technical, legal_clearance_token=legal,
            delete_knowledge_base=lambda _db, kb: deleted.append(kb.id),
        )
    assert deleted == []
