"""HTTP layer for AI agent management, scoped by membership permissions."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..services.agent_management import (
    AgentAccessError,
    AgentNotFoundError,
    AgentValidationError,
    create_agent as svc_create_agent,
    list_agents as svc_list_agents,
    serialize_agent,
    update_agent as svc_update_agent,
)
from .deps import require_permission

router = APIRouter()


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    role: str = Field(min_length=1, max_length=50)
    active: bool = True
    store_ids: list[int] = Field(default_factory=list)
    knowledge_base_ids: list[int] = Field(default_factory=list)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    role: str | None = Field(default=None, min_length=1, max_length=50)
    active: bool | None = None
    store_ids: list[int] | None = None
    knowledge_base_ids: list[int] | None = None


def _translate_error(exc: Exception):
    if isinstance(exc, AgentNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, AgentAccessError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, AgentValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/api/agents")
def list_agents(
    membership: OrganizationMembership = Depends(
        require_permission("agents.read")
    ),
    db: Session = Depends(get_db),
):
    agents = svc_list_agents(db, membership)
    return {
        "items": [serialize_agent(agent, membership) for agent in agents],
        "total": len(agents),
    }


@router.post("/api/agents")
def create_agent(
    payload: AgentCreate,
    membership: OrganizationMembership = Depends(
        require_permission("agents.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        agent = svc_create_agent(
            db, membership,
            name=payload.name,
            role=payload.role,
            active=payload.active,
            store_ids=payload.store_ids,
            knowledge_base_ids=payload.knowledge_base_ids,
        )
    except (AgentNotFoundError, AgentAccessError, AgentValidationError) as exc:
        _translate_error(exc)
    return serialize_agent(agent, membership)


@router.patch("/api/agents/{agent_id}")
def update_agent(
    agent_id: int,
    payload: AgentUpdate,
    membership: OrganizationMembership = Depends(
        require_permission("agents.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        agent = svc_update_agent(
            db, membership, agent_id,
            updates=payload.model_dump(exclude_unset=True),
        )
    except (AgentNotFoundError, AgentAccessError, AgentValidationError) as exc:
        _translate_error(exc)
    return serialize_agent(agent, membership)
