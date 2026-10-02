"""One-time explicit approvals for agent write/critical actions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..model_domains.ai_agent import AgentActionApproval
from ..models import OrganizationMembership
from .action_policy import ActionDecision


APPROVAL_TTL_MINUTES = 10


class AgentApprovalError(Exception):
    pass


def hash_arguments(arguments: dict) -> str:
    canonical = json.dumps(
        arguments or {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def serialize_approval(approval: AgentActionApproval) -> dict:
    return {
        "id": approval.id,
        "tool_name": approval.tool_name,
        "action": approval.action,
        "risk": approval.risk,
        "confirmation": approval.confirmation,
        "status": approval.status,
        "store_id": approval.store_id,
        "arguments": approval.arguments,
        "expires_at": approval.expires_at.isoformat() + "Z",
        "approved_at": (
            approval.approved_at.isoformat() + "Z"
            if approval.approved_at
            else None
        ),
        "consumed_at": (
            approval.consumed_at.isoformat() + "Z"
            if approval.consumed_at
            else None
        ),
    }


def create_approval(
    db: Session,
    membership: OrganizationMembership,
    *,
    store_id: int,
    tool_name: str,
    action: str,
    arguments: dict,
    decision: ActionDecision,
) -> AgentActionApproval:
    now = datetime.utcnow()
    approval = AgentActionApproval(
        organization_id=membership.organization_id,
        membership_id=membership.id,
        user_id=membership.user_id,
        store_id=store_id,
        tool_name=tool_name,
        action=action,
        risk=decision.risk,
        confirmation=decision.confirmation,
        arguments_hash=hash_arguments(arguments),
        arguments=arguments or {},
        status="pending",
        expires_at=now + timedelta(minutes=APPROVAL_TTL_MINUTES),
        created_at=now,
        updated_at=now,
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def get_approval_for_membership(
    db: Session,
    membership: OrganizationMembership,
    approval_id: int,
) -> AgentActionApproval:
    approval = (
        db.query(AgentActionApproval)
        .filter(
            AgentActionApproval.id == approval_id,
            AgentActionApproval.organization_id == membership.organization_id,
            AgentActionApproval.membership_id == membership.id,
            AgentActionApproval.user_id == membership.user_id,
        )
        .first()
    )
    if approval is None:
        raise AgentApprovalError("APPROVAL_NOT_FOUND")
    return approval


def approve_action(
    db: Session,
    membership: OrganizationMembership,
    approval_id: int,
) -> AgentActionApproval:
    approval = get_approval_for_membership(db, membership, approval_id)
    now = datetime.utcnow()
    if approval.status != "pending":
        raise AgentApprovalError("APPROVAL_NOT_PENDING")
    if approval.expires_at <= now:
        approval.status = "expired"
        approval.updated_at = now
        db.commit()
        raise AgentApprovalError("APPROVAL_EXPIRED")

    approval.status = "approved"
    approval.approved_at = now
    approval.updated_at = now
    db.commit()
    db.refresh(approval)
    return approval


def cancel_action(
    db: Session,
    membership: OrganizationMembership,
    approval_id: int,
) -> AgentActionApproval:
    approval = get_approval_for_membership(db, membership, approval_id)
    if approval.status not in {"pending", "approved"}:
        raise AgentApprovalError("APPROVAL_NOT_CANCELLABLE")
    now = datetime.utcnow()
    approval.status = "cancelled"
    approval.cancelled_at = now
    approval.updated_at = now
    db.commit()
    db.refresh(approval)
    return approval


def validate_approved_action(
    db: Session,
    membership: OrganizationMembership,
    approval_id: int,
    *,
    tool_name: str,
    action: str,
    store_id: int,
    arguments: dict,
) -> AgentActionApproval:
    approval = get_approval_for_membership(db, membership, approval_id)
    now = datetime.utcnow()

    if approval.status != "approved":
        raise AgentApprovalError("APPROVAL_NOT_APPROVED")
    if approval.expires_at <= now:
        approval.status = "expired"
        approval.updated_at = now
        db.commit()
        raise AgentApprovalError("APPROVAL_EXPIRED")
    if approval.store_id != store_id:
        raise AgentApprovalError("APPROVAL_SCOPE_MISMATCH")
    if approval.tool_name != tool_name or approval.action != action:
        raise AgentApprovalError("APPROVAL_ACTION_MISMATCH")
    if approval.arguments_hash != hash_arguments(arguments):
        raise AgentApprovalError("APPROVAL_ARGUMENTS_MISMATCH")

    return approval


def consume_approval(
    db: Session,
    approval: AgentActionApproval,
) -> None:
    if approval.status != "approved":
        raise AgentApprovalError("APPROVAL_NOT_APPROVED")
    now = datetime.utcnow()
    approval.status = "consumed"
    approval.consumed_at = now
    approval.updated_at = now
    db.commit()


__all__ = [
    "APPROVAL_TTL_MINUTES",
    "AgentApprovalError",
    "approve_action",
    "cancel_action",
    "consume_approval",
    "create_approval",
    "hash_arguments",
    "serialize_approval",
    "validate_approved_action",
]
