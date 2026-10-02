"""Agent capability discovery and authorization preflight endpoints."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..services.action_policy import evaluate_action
from ..services.ai_tool_registry import list_authorized_tools
from .deps import get_current_membership


router = APIRouter()


class ActionAuthorizationRequest(BaseModel):
    action: str = Field(min_length=1, max_length=120)
    store_id: int | None = Field(default=None, ge=1)


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
