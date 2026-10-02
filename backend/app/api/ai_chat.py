"""HTTP API for the Diaglob operations copilot."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..services.agent_chat_service import (
    AgentChatError,
    approve_chat_action,
    archive_chat_session,
    cancel_chat_action,
    create_chat_session,
    get_chat_session,
    list_chat_sessions,
    send_chat_message,
)
from ..services.bedrock_agent_chat import AgentModelError
from .deps import get_current_membership


router = APIRouter()


class ChatSessionCreateRequest(BaseModel):
    store_id: int = Field(ge=1)
    title: str | None = Field(default=None, max_length=200)
    context: dict = Field(default_factory=dict)


class ChatMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    context: dict = Field(default_factory=dict)


def _map_chat_error(exc: Exception):
    code = str(exc)
    if isinstance(exc, AgentModelError):
        raise HTTPException(
            status_code=503,
            detail={"code": "AGENT_MODEL_UNAVAILABLE", "message": code},
        ) from exc

    status = 409
    if code == "CHAT_SESSION_NOT_FOUND":
        status = 404
    elif code in {"STORE_NOT_FOUND", "STORE_ACCESS_DENIED", "PERMISSION_DENIED"}:
        status = 403
    elif code in {
        "CHAT_MESSAGE_REQUIRED",
        "CHAT_MESSAGE_TOO_LONG",
        "CHAT_SESSION_NOT_ACTIVE",
    }:
        status = 400
    elif code in {
        "AI_USAGE_EXHAUSTED",
        "TRIAL_AI_LIMIT_REACHED",
        "TRIAL_EXPIRED",
        "TRIAL_BLOCKED",
        "TRIAL_PENDING",
    }:
        status = 402

    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": code.replace("_", " ").title()},
    ) from exc


@router.get("/api/ai/chat/sessions")
def get_ai_chat_sessions(
    store_id: int = Query(ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        items = list_chat_sessions(
            db,
            membership,
            store_id=store_id,
            limit=limit,
        )
    except AgentChatError as exc:
        _map_chat_error(exc)
    return {"items": items, "total": len(items)}


@router.post("/api/ai/chat/sessions")
def create_ai_chat_session(
    payload: ChatSessionCreateRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        return create_chat_session(
            db,
            membership,
            store_id=payload.store_id,
            title=payload.title,
            context=payload.context,
        )
    except AgentChatError as exc:
        _map_chat_error(exc)


@router.get("/api/ai/chat/sessions/{session_id}")
def get_ai_chat_session(
    session_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        return get_chat_session(db, membership, session_id)
    except AgentChatError as exc:
        _map_chat_error(exc)


@router.delete("/api/ai/chat/sessions/{session_id}")
def archive_ai_chat_session(
    session_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        return archive_chat_session(db, membership, session_id)
    except AgentChatError as exc:
        _map_chat_error(exc)


@router.post("/api/ai/chat/sessions/{session_id}/messages")
def create_ai_chat_message(
    session_id: int,
    payload: ChatMessageRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        return send_chat_message(
            db,
            membership,
            session_id,
            text=payload.text,
            context=payload.context,
        )
    except (AgentChatError, AgentModelError) as exc:
        _map_chat_error(exc)


@router.post(
    "/api/ai/chat/sessions/{session_id}/approvals/{approval_id}/approve"
)
def approve_ai_chat_action(
    session_id: int,
    approval_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        return approve_chat_action(
            db,
            membership,
            session_id,
            approval_id,
        )
    except (AgentChatError, AgentModelError) as exc:
        _map_chat_error(exc)


@router.post(
    "/api/ai/chat/sessions/{session_id}/approvals/{approval_id}/cancel"
)
def cancel_ai_chat_action(
    session_id: int,
    approval_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    try:
        return cancel_chat_action(
            db,
            membership,
            session_id,
            approval_id,
        )
    except (AgentChatError, AgentModelError) as exc:
        _map_chat_error(exc)


__all__ = ["router"]
