"""Agent capability discovery and authorization preflight endpoints."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..services.action_policy import evaluate_action
from ..services.agent_approvals import (
    AgentApprovalError,
    approve_action,
    cancel_action,
    get_approval_for_membership,
    serialize_approval,
)
from ..services.agent_tool_executor import execute_agent_tool
from ..services.ai_tool_registry import list_authorized_tools
from .deps import get_current_membership


router = APIRouter()


class ActionAuthorizationRequest(BaseModel):
    action: str = Field(min_length=1, max_length=120)
    store_id: int | None = Field(default=None, ge=1)


class ToolExecutionRequest(BaseModel):
    store_id: int = Field(ge=1)
    arguments: dict = Field(default_factory=dict)
    approval_id: int | None = Field(default=None, ge=1)


@router.get("/api/ai/tools")
def list_ai_tools(
    store_id: int = Query(ge=1),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    tools = list_authorized_tools(
        db,
        membership,
        store_id=store_id,
        include_denied=False,
    )
    return {
        "organization_id": membership.organization_id,
        "store_id": store_id,
        "role": membership.role,
        "tools": tools,
        "total": len(tools),
    }


@router.post("/api/ai/tools/{tool_name}/execute")
def execute_ai_tool(
    tool_name: str,
    payload: ToolExecutionRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    return execute_agent_tool(
        db,
        membership,
        tool_name=tool_name,
        store_id=payload.store_id,
        arguments=payload.arguments,
        approval_id=payload.approval_id,
    )


@router.get("/api/ai/approvals/{approval_id}")
def get_ai_approval(
    approval_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        approval = get_approval_for_membership(
            db,
            membership,
            approval_id,
        )
    except AgentApprovalError as exc:
        return {"ok": False, "code": str(exc)}
    return {"ok": True, "approval": serialize_approval(approval)}


@router.post("/api/ai/approvals/{approval_id}/approve")
def approve_ai_action(
    approval_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        approval = approve_action(db, membership, approval_id)
    except AgentApprovalError as exc:
        return {"ok": False, "code": str(exc)}
    return {"ok": True, "approval": serialize_approval(approval)}


@router.post("/api/ai/approvals/{approval_id}/cancel")
def cancel_ai_action(
    approval_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        approval = cancel_action(db, membership, approval_id)
    except AgentApprovalError as exc:
        return {"ok": False, "code": str(exc)}
    return {"ok": True, "approval": serialize_approval(approval)}


@router.post("/api/ai/actions/authorize")
def authorize_ai_action(
    payload: ActionAuthorizationRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    decision = evaluate_action(
        db,
        membership,
        payload.action,
        store_id=payload.store_id,
    )
    return decision.as_dict()


__all__ = ["router"]
