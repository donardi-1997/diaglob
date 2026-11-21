"""Separately permitted, store-specific merchant Copilot SQL erasure.

Only Shopify shop/redact may erase merchant Copilot data, because there is no
verified relation from Copilot prompts/messages to a particular Shopify buyer.
This is a SQL-only operation. It cannot certify copies held by AI providers,
logs, backups, or a Shopify privacy case's total fulfillment.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from ..model_domains.ai_agent import (
    AgentActionApproval, AgentChatMessage, AgentChatSession, AgentChatToolCall,
)
from ..models import ShopifyPrivacyAuditEvent
from .shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError, require_execution_policy, verify_execution_permit,
)
from .shopify_privacy_legal_clearance import verify_case_legal_clearance
from .shopify_privacy_local_execution import owned_privacy_receipt, require_privacy_owner
from .shopify_privacy_lock import lock_shopify_privacy_scope

EXECUTED_EVENT = "copilot_erasure_executed"
ACTOR = "independently_permitted_worker"
MAX_ROWS_PER_TABLE = 10_000


def _ids(query, label: str) -> list[int]:
    ids = [int(row[0]) for row in query.order_by(None).limit(MAX_ROWS_PER_TABLE + 1).all()]
    if len(ids) > MAX_ROWS_PER_TABLE or len(ids) != len(set(ids)):
        raise ShopifyPrivacyExecutionError("COPILOT_ERASURE_SCOPE_LIMIT_OR_DUPLICATES")
    return sorted(ids)


def _content_digest(db: Session, sessions: list[int], messages: list[int],
                    calls: list[int], approvals: list[int]) -> str:
    """Fingerprint mutable Copilot content without returning/logging any PII.

    Row IDs alone are insufficient: a new message body or tool result with the
    same ID after signing must invalidate both short-lived permits.
    """
    records = []
    specs = (
        (AgentChatSession, sessions, lambda r: (
            r.title, r.context, r.pending_capacity, r.status,
        )),
        (AgentChatMessage, messages, lambda r: (
            r.provider_role, r.text, r.content, r.model_id, r.stop_reason,
        )),
        (AgentChatToolCall, calls, lambda r: (
            r.session_id, r.message_id, r.approval_id, r.tool_use_id,
            r.arguments, r.result, r.status,
        )),
        (AgentActionApproval, approvals, lambda r: (
            r.membership_id, r.user_id, r.tool_name, r.action, r.risk,
            r.confirmation, r.arguments_hash, r.arguments, r.status,
            r.error_message,
        )),
    )
    for model, ids, extract in specs:
        if not ids:
            continue
        rows = db.query(model).filter(model.id.in_(ids)).all()
        if len(rows) != len(ids):
            raise ShopifyPrivacyExecutionError("COPILOT_SCOPE_CONCURRENT_DRIFT")
        for row in rows:
            records.append((model.__tablename__, row.id, extract(row)))
    raw = json.dumps(records, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def plan_shop_copilot_erasure(db: Session, *, organization_id: int, store_id: int) -> dict:
    """Read-only exact-ID plan, never inferred from message text or buyer ID."""
    if (type(organization_id) is not int or organization_id <= 0
            or type(store_id) is not int or store_id <= 0):
        raise ShopifyPrivacyExecutionError("COPILOT_SCOPE_INVALID")
    sessions = _ids(db.query(AgentChatSession.id).filter(
        AgentChatSession.organization_id == organization_id,
        AgentChatSession.store_id == store_id,
    ), "sessions")
    messages = _ids(db.query(AgentChatMessage.id).filter(
        AgentChatMessage.session_id.in_(sessions),
    ), "messages") if sessions else []
    calls = _ids(db.query(AgentChatToolCall.id).filter(
        AgentChatToolCall.session_id.in_(sessions),
    ), "tools") if sessions else []
    approvals = _ids(db.query(AgentActionApproval.id).filter(
        AgentActionApproval.organization_id == organization_id,
        AgentActionApproval.store_id == store_id,
    ), "approvals")

    # A corrupted/mixed FK must fail closed; never remove shared/foreign rows.
    if calls:
        selected_calls = db.query(
            AgentChatToolCall.message_id, AgentChatToolCall.approval_id,
        ).filter(AgentChatToolCall.id.in_(calls)).all()
        message_set, approval_set = set(messages), set(approvals)
        for message_id, approval_id in selected_calls:
            if message_id not in message_set or (
                approval_id is not None and approval_id not in approval_set
            ):
                raise ShopifyPrivacyExecutionError("COPILOT_CROSS_STORE_REFERENCE")
    if messages:
        foreign_message_reference = db.query(AgentChatToolCall.id).filter(
            AgentChatToolCall.message_id.in_(messages),
            ~AgentChatToolCall.id.in_(calls),
        ).first()
        if foreign_message_reference is not None:
            raise ShopifyPrivacyExecutionError("COPILOT_CROSS_STORE_MESSAGE_REFERENCE")
    if approvals:
        external_approval = db.query(AgentChatToolCall.id).filter(
            AgentChatToolCall.approval_id.in_(approvals),
            ~AgentChatToolCall.id.in_(calls),
        ).first()
        if external_approval is not None:
            raise ShopifyPrivacyExecutionError("COPILOT_SHARED_APPROVAL_REFERENCE")

    return {
        "session_ids": sessions, "message_ids": messages,
        "tool_call_ids": calls, "approval_ids": approvals,
        "snapshot_sha256": _content_digest(db, sessions, messages, calls, approvals),
    }


def _local_redaction_digest(db: Session, request_id: str) -> str:
    item = db.query(ShopifyPrivacyAuditEvent.reason_code).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "local_redaction_executed",
        ShopifyPrivacyAuditEvent.actor_type == ACTOR,
    ).first()
    if not item or not isinstance(item[0], str) or len(item[0]) != 64:
        raise ShopifyPrivacyExecutionError("COPILOT_LOCAL_REDACTION_REQUIRED")
    return item[0]


def copilot_erasure_scope_digest(
    db: Session, *, request_id: str, organization_id: int, store_id: int,
    plan: dict,
) -> str:
    """Bind all exact row IDs to the case and the prior signed SQL operation."""
    subject = _local_redaction_digest(db, request_id)
    payload = [
        "diaglob.shopify.copilot-erasure.v1", request_id,
        organization_id, store_id, subject,
        plan["session_ids"], plan["message_ids"],
        plan["tool_call_ids"], plan["approval_ids"],
        plan["snapshot_sha256"],
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def preview_shop_copilot_erasure(
    db: Session, *, request_id: str, organization_id: int,
    store_id: int, user_id: int,
) -> dict:
    require_privacy_owner(db, organization_id=organization_id,
                          store_id=store_id, user_id=user_id)
    receipt = owned_privacy_receipt(
        db, request_id=request_id, organization_id=organization_id, store_id=store_id,
    )
    if receipt.topic != "shop/redact":
        raise ShopifyPrivacyExecutionError("COPILOT_SHOP_REDACT_ONLY")
    plan = plan_shop_copilot_erasure(db, organization_id=organization_id, store_id=store_id)
    digest = copilot_erasure_scope_digest(
        db, request_id=request_id, organization_id=organization_id, store_id=store_id,
        plan=plan,
    )
    return {
        "request_id": request_id,
        "operation": "shop_copilot_erasure",
        "scope_sha256": digest,
        "counts": {key.removesuffix("_ids"): len(value) for key, value in plan.items()
                   if key.endswith("_ids")},
        "subject_level_attribution": False,
        "external_ai_provider_deletion_verified": False,
        "fulfillment_complete": False,
    }


def execute_shop_copilot_erasure(
    db: Session, *, request_id: str, organization_id: int, store_id: int,
    user_id: int, execution_permit: str | None = None,
    legal_clearance_token: str | None = None,
) -> dict:
    require_privacy_owner(db, organization_id=organization_id,
                          store_id=store_id, user_id=user_id)
    require_execution_policy()
    lock_shopify_privacy_scope(db, organization_id, store_id)
    receipt = owned_privacy_receipt(
        db, request_id=request_id, organization_id=organization_id, store_id=store_id,
    )
    if receipt.topic != "shop/redact":
        raise ShopifyPrivacyExecutionError("COPILOT_SHOP_REDACT_ONLY")
    audit = db.query(ShopifyPrivacyAuditEvent.reason_code).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == EXECUTED_EVENT,
        ShopifyPrivacyAuditEvent.actor_type == ACTOR,
    ).first()
    if audit is not None:
        verify_execution_permit(
            execution_permit, operation="shop_copilot_erasure",
            request_id=request_id, organization_id=organization_id,
            store_id=store_id, scope_sha256=audit[0],
        )
        verify_case_legal_clearance(
            legal_clearance_token, request_id=request_id,
            organization_id=organization_id, store_id=store_id,
            scope_sha256=audit[0],
        )
        return {"copilot_erasure_executed": True, "idempotent": True,
                "external_ai_provider_deletion_verified": False,
                "fulfillment_complete": False}
    plan = plan_shop_copilot_erasure(db, organization_id=organization_id, store_id=store_id)
    digest = copilot_erasure_scope_digest(
        db, request_id=request_id, organization_id=organization_id,
        store_id=store_id, plan=plan,
    )
    verify_execution_permit(
        execution_permit, operation="shop_copilot_erasure",
        request_id=request_id, organization_id=organization_id,
        store_id=store_id, scope_sha256=digest,
    )
    verify_case_legal_clearance(
        legal_clearance_token, request_id=request_id,
        organization_id=organization_id, store_id=store_id, scope_sha256=digest,
    )
    try:
        # All four tables are owned by the same verified store. Audit and
        # deletions commit together; failures rollback without partial SQL.
        # Do not emit IDs, message contents or provider inputs in logs.
        for model, ids_key in (
            (AgentChatToolCall, "tool_call_ids"),
            (AgentChatMessage, "message_ids"),
            (AgentChatSession, "session_ids"),
            (AgentActionApproval, "approval_ids"),
        ):
            ids = plan[ids_key]
            if ids:
                count = db.query(model).filter(model.id.in_(ids)).delete(synchronize_session=False)
                if count != len(ids):
                    raise ShopifyPrivacyExecutionError("COPILOT_ERASURE_CONCURRENT_DRIFT")
        db.add(ShopifyPrivacyAuditEvent(
            request_id=request_id, event_type=EXECUTED_EVENT,
            from_status=receipt.status, to_status=receipt.status,
            reason_code=digest, actor_type=ACTOR, created_at=datetime.utcnow(),
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "copilot_erasure_executed": True, "idempotent": False,
        "counts": {key.removesuffix("_ids"): len(value) for key, value in plan.items()
                   if key.endswith("_ids")},
        "external_ai_provider_deletion_verified": False,
        "backup_erasure_verified": False,
        "fulfillment_complete": False,
    }
