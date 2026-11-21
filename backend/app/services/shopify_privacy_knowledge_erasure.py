"""Erase knowledge bases owned exclusively by a redacted Shopify store.

Local `shop/redact` execution covers SQL records only. Knowledge bases keep
merchant documents in S3, Bedrock vectors and Google Drive/Sheets copies, so
they are erased in this separate, externally-effecting step.

Safety rules:
- Runs only after the permitted local `shop/redact` redaction succeeded for
  the same request, inheriting that independently signed scope.
- Deletes only bases scoped to selected stores whose ONLY store is the
  redacted one. Organization-wide or shared bases are never deleted; they are
  reported as blockers for review.
- Idempotent: once recorded, repeated calls perform no deletion.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..model_domains.knowledge import KnowledgeBase
from ..model_domains.tenancy import knowledge_base_stores
from ..models import ShopifyPrivacyAuditEvent
from .shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError,
    require_execution_policy,
    verify_execution_permit,
)
from .shopify_privacy_local_execution import owned_privacy_receipt, require_privacy_owner
from .shopify_privacy_lock import lock_shopify_privacy_scope
from .shopify_privacy_legal_clearance import verify_case_legal_clearance

EXECUTED_EVENT = "knowledge_erasure_executed"
STARTED_EVENT = "knowledge_erasure_started"
_ACTOR = "independently_permitted_worker"


def _audit_exists(db: Session, request_id: str, event_type: str) -> bool:
    return db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == event_type,
        ShopifyPrivacyAuditEvent.actor_type == _ACTOR,
    ).first() is not None


def plan_shop_knowledge_erasure(db: Session, *, organization_id: int, store_id: int) -> dict:
    """IDs of bases exclusive to the store, plus count of shared bases kept."""
    link_counts = select(
        knowledge_base_stores.c.knowledge_base_id.label("kb_id"),
        func.count().label("stores"),
    ).group_by(knowledge_base_stores.c.knowledge_base_id).subquery()
    linked = select(knowledge_base_stores.c.knowledge_base_id).where(
        knowledge_base_stores.c.store_id == store_id,
    )
    rows = db.query(KnowledgeBase.id, KnowledgeBase.scope, link_counts.c.stores).outerjoin(
        link_counts, link_counts.c.kb_id == KnowledgeBase.id,
    ).filter(
        KnowledgeBase.organization_id == organization_id,
        KnowledgeBase.id.in_(linked),
    ).all()
    exclusive = sorted(
        kb_id for kb_id, scope, stores in rows if scope == "selected_stores" and stores == 1
    )
    return {"exclusive_knowledge_base_ids": exclusive,
            "shared_knowledge_bases_kept": len(rows) - len(exclusive)}


def knowledge_erasure_scope_digest(
    db: Session, *, request_id: str, organization_id: int, store_id: int,
    plan: dict,
) -> str:
    """Bind KB candidates to the previously permitted SQL redaction scope."""
    audit = db.query(ShopifyPrivacyAuditEvent.reason_code).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "local_redaction_executed",
        ShopifyPrivacyAuditEvent.actor_type == _ACTOR,
    ).first()
    if audit is None or not isinstance(audit[0], str) or len(audit[0]) != 64:
        raise ShopifyPrivacyExecutionError("LOCAL_REDACTION_SCOPE_EVIDENCE_REQUIRED")
    payload = [
        "diaglob.shopify.knowledge-erasure.v1", request_id,
        organization_id, store_id, audit[0],
        sorted(plan["exclusive_knowledge_base_ids"]),
        plan["shared_knowledge_bases_kept"],
    ]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def execute_shop_knowledge_erasure(
    db: Session, *, request_id: str, organization_id: int, store_id: int, user_id: int,
    execution_permit: str | None = None, legal_clearance_token: str | None = None,
    delete_knowledge_base=None,
) -> dict:
    if delete_knowledge_base is None:
        from .knowledge_bases import delete_knowledge_base
    require_privacy_owner(db, organization_id=organization_id, store_id=store_id, user_id=user_id)
    require_execution_policy()
    lock_shopify_privacy_scope(db, organization_id, store_id)
    receipt = owned_privacy_receipt(
        db, request_id=request_id, organization_id=organization_id, store_id=store_id,
    )
    if receipt.topic != "shop/redact":
        raise ShopifyPrivacyExecutionError("SHOP_REDACT_TOPIC_REQUIRED")
    if not _audit_exists(db, request_id, "local_redaction_executed"):
        raise ShopifyPrivacyExecutionError("LOCAL_REDACTION_REQUIRED_FIRST")
    if _audit_exists(db, request_id, EXECUTED_EVENT):
        return {"knowledge_erasure_executed": True, "idempotent": True,
                "fulfillment_complete": False}
    if _audit_exists(db, request_id, STARTED_EVENT):
        # The underlying S3/Bedrock KB deletion orchestrator commits inside
        # each deletion. A crashed or partially failed batch may have already
        # removed remote objects, while changing the next planned KB digest.
        # An independent reconciliation of the original signed plan is needed
        # before any retry; do not infer remote deletion from missing SQL rows.
        raise ShopifyPrivacyExecutionError(
            "KNOWLEDGE_ERASURE_INTERRUPTED_RECONCILIATION_REQUIRED"
        )

    plan = plan_shop_knowledge_erasure(db, organization_id=organization_id, store_id=store_id)
    digest = knowledge_erasure_scope_digest(db, request_id=request_id,
        organization_id=organization_id, store_id=store_id, plan=plan)
    # External S3/Bedrock deletions must NOT inherit permission merely from
    # prior SQL erasure: independently authorize their own exact KB plan.
    verify_execution_permit(execution_permit, operation="shop_knowledge_erasure",
        request_id=request_id, organization_id=organization_id,
        store_id=store_id, scope_sha256=digest)
    verify_case_legal_clearance(legal_clearance_token, request_id=request_id,
        organization_id=organization_id, store_id=store_id, scope_sha256=digest)

    # Persist the exact original approved digest BEFORE the first irreversible
    # provider operation. Each underlying delete may commit separately, so
    # a single surrounding SQL transaction cannot make this step atomic.
    # This PII-free marker is deliberately never cleared on exception.
    db.add(ShopifyPrivacyAuditEvent(
        request_id=request_id, event_type=STARTED_EVENT,
        from_status=receipt.status, to_status=receipt.status,
        reason_code=digest, actor_type=_ACTOR, created_at=datetime.utcnow(),
    ))
    db.commit()
    deleted = 0
    for kb_id in plan["exclusive_knowledge_base_ids"]:
        # Revalidate ownership immediately before each non-atomic external call:
        # between approval and this iteration another merchant could have
        # attached this KB to a second store, making it shared.
        current_plan = plan_shop_knowledge_erasure(
            db, organization_id=organization_id, store_id=store_id,
        )
        if kb_id not in current_plan["exclusive_knowledge_base_ids"]:
            raise ShopifyPrivacyExecutionError(
                "KNOWLEDGE_ERASURE_OWNERSHIP_CHANGED_RECONCILIATION_REQUIRED"
            )
        knowledge_base = db.get(KnowledgeBase, kb_id)
        if knowledge_base is None or knowledge_base.organization_id != organization_id:
            raise ShopifyPrivacyExecutionError(
                "KNOWLEDGE_ERASURE_RESOURCE_DISAPPEARED_RECONCILIATION_REQUIRED"
            )
        # Deletes S3 documents and Bedrock resources; raises on external failure,
        # leaving no completion audit so the step can be safely retried.
        delete_knowledge_base(db, knowledge_base)
        deleted += 1
    db.add(ShopifyPrivacyAuditEvent(
        request_id=request_id, event_type=EXECUTED_EVENT,
        from_status=receipt.status, to_status=receipt.status,
        reason_code=f"deleted={deleted};shared_kept={plan['shared_knowledge_bases_kept']}",
        actor_type=_ACTOR, created_at=datetime.utcnow(),
    ))
    db.commit()
    return {
        "knowledge_erasure_executed": True, "idempotent": False,
        "knowledge_bases_deleted": deleted,
        "shared_knowledge_bases_kept": plan["shared_knowledge_bases_kept"],
        "review_required": plan["shared_knowledge_bases_kept"] > 0,
        "fulfillment_complete": False,
    }
