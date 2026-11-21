"""shop/redact must erase knowledge bases owned only by the redacted store."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.services.shopify_privacy_knowledge_erasure as erasure
from app.db import Base
from app.model_domains.knowledge import KnowledgeBase
from app.model_domains.tenancy import knowledge_base_stores
from app.models import ShopifyPrivacyAuditEvent
from app.services.shopify_privacy_execution_authorization import ShopifyPrivacyExecutionError

ORG, STORE, OTHER = 1, 10, 11
RID = "a" * 64


@pytest.fixture
def db(monkeypatch):
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


def _run(session, deleter):
    return erasure.execute_shop_knowledge_erasure(
        session, request_id=RID, organization_id=ORG, store_id=STORE, user_id=7,
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


def test_external_failure_leaves_step_retryable(db):
    session, _ = db
    _redacted(session)

    def failing(_db, _kb):
        raise RuntimeError("bedrock unavailable")

    with pytest.raises(RuntimeError):
        _run(session, failing)
    assert session.query(ShopifyPrivacyAuditEvent).filter_by(
        event_type=erasure.EXECUTED_EVENT).count() == 0
