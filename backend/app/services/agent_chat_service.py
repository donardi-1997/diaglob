"""Persistence and orchestration for the Diaglob operations copilot."""

from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy.orm import Session

from ..model_domains.ai_agent import (
    AgentActionApproval,
    AgentChatMessage,
    AgentChatSession,
    AgentChatToolCall,
)
from ..models import OrganizationMembership
from ..settings import get_settings
from .action_policy import evaluate_action
from .agent_approvals import (
    AgentApprovalError,
    approve_action,
    cancel_action,
    serialize_approval,
)
from .agent_tool_executor import execute_agent_tool
from .ai_tool_registry import get_tool, list_authorized_tools
from .ai_usage_service import acquire_ai_capacity, refund_ai_capacity
from .bedrock_agent_chat import AgentModelError, converse


CHAT_HISTORY_MESSAGE_LIMIT = 40


_RESOLVED_TOOL_STATUSES = {
    "success",
    "error",
    "denied",
    "unavailable",
    "cancelled",
}


class AgentChatError(Exception):
    pass


def _json_safe(value):
    return json.loads(json.dumps(value, default=str))


def _require_chat_access(
    db: Session,
    membership: OrganizationMembership,
    store_id: int,
) -> None:
    decision = evaluate_action(
        db,
        membership,
        "chat.use",
        store_id=store_id,
    )
    if not decision.allowed:
        raise AgentChatError(decision.code or "CHAT_ACCESS_DENIED")


def _require_session(
    db: Session,
    membership: OrganizationMembership,
    session_id: int,
) -> AgentChatSession:
    session = (
        db.query(AgentChatSession)
        .filter(
            AgentChatSession.id == session_id,
            AgentChatSession.organization_id == membership.organization_id,
            AgentChatSession.membership_id == membership.id,
            AgentChatSession.user_id == membership.user_id,
        )
        .first()
    )
    if session is None:
        raise AgentChatError("CHAT_SESSION_NOT_FOUND")
    _require_chat_access(db, membership, session.store_id)
    return session


def _approval_payload(
    db: Session,
    approval_id: int | None,
) -> dict | None:
    if approval_id is None:
        return None
    approval = (
        db.query(AgentActionApproval)
        .filter(AgentActionApproval.id == approval_id)
        .first()
    )
    return serialize_approval(approval) if approval is not None else None


def serialize_tool_call(
    db: Session,
    call: AgentChatToolCall,
) -> dict:
    tool = get_tool(call.tool_name)
    return {
        "id": call.id,
        "tool_use_id": call.tool_use_id,
        "tool_name": call.tool_name,
        "title": tool.title if tool else call.tool_name,
        "description": tool.description if tool else None,
        "arguments": call.arguments,
        "status": call.status,
        "result": call.result,
        "approval": _approval_payload(db, call.approval_id),
        "created_at": call.created_at.isoformat() + "Z",
    }


def serialize_message(
    db: Session,
    message: AgentChatMessage,
) -> dict:
    calls = (
        db.query(AgentChatToolCall)
        .filter(AgentChatToolCall.message_id == message.id)
        .order_by(AgentChatToolCall.id.asc())
        .all()
    )
    return {
        "id": message.id,
        "role": message.provider_role,
        "text": message.text or "",
        "model_id": message.model_id,
        "billable": message.billable,
        "created_at": message.created_at.isoformat() + "Z",
        "tool_calls": [serialize_tool_call(db, call) for call in calls],
    }


def serialize_session(
    db: Session,
    session: AgentChatSession,
    *,
    include_messages: bool = True,
) -> dict:
    payload = {
        "id": session.id,
        "store_id": session.store_id,
        "title": session.title,
        "context": session.context or {},
        "status": session.status,
        "has_pending_turn": session.pending_capacity is not None,
        "created_at": session.created_at.isoformat() + "Z",
        "updated_at": session.updated_at.isoformat() + "Z",
    }
    if include_messages:
        messages = (
            db.query(AgentChatMessage)
            .filter(AgentChatMessage.session_id == session.id)
            .order_by(AgentChatMessage.id.asc())
            .all()
        )
        payload["messages"] = [
            serialize_message(db, message)
            for message in messages
        ]
        payload["pending_actions"] = [
            tool_call
            for message in payload["messages"]
            for tool_call in message["tool_calls"]
            if tool_call["status"] == "approval_required"
        ]
    return payload


def create_chat_session(
    db: Session,
    membership: OrganizationMembership,
    *,
    store_id: int,
    title: str | None = None,
    context: dict | None = None,
) -> dict:
    _require_chat_access(db, membership, store_id)
    now = datetime.utcnow()
    session = AgentChatSession(
        organization_id=membership.organization_id,
        membership_id=membership.id,
        user_id=membership.user_id,
        store_id=store_id,
        title=(title or "Nuevo chat").strip()[:200] or "Nuevo chat",
        context=context or {},
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return serialize_session(db, session)


def list_chat_sessions(
    db: Session,
    membership: OrganizationMembership,
    *,
    store_id: int,
    limit: int = 50,
) -> list[dict]:
    _require_chat_access(db, membership, store_id)
    sessions = (
        db.query(AgentChatSession)
        .filter(
            AgentChatSession.organization_id == membership.organization_id,
            AgentChatSession.membership_id == membership.id,
            AgentChatSession.user_id == membership.user_id,
            AgentChatSession.store_id == store_id,
            AgentChatSession.status != "archived",
        )
        .order_by(AgentChatSession.updated_at.desc())
        .limit(max(1, min(limit, 100)))
        .all()
    )
    return [
        serialize_session(db, session, include_messages=False)
        for session in sessions
    ]


def get_chat_session(
    db: Session,
    membership: OrganizationMembership,
    session_id: int,
) -> dict:
    session = _require_session(db, membership, session_id)
    return serialize_session(db, session)


def archive_chat_session(
    db: Session,
    membership: OrganizationMembership,
    session_id: int,
) -> dict:
    session = _require_session(db, membership, session_id)
    if session.pending_capacity:
        raise AgentChatError("CHAT_TURN_PENDING")
    session.status = "archived"
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return serialize_session(db, session, include_messages=False)


def _history(
    db: Session,
    session: AgentChatSession,
) -> list[dict]:
    messages = list(
        reversed(
            db.query(AgentChatMessage)
            .filter(AgentChatMessage.session_id == session.id)
            .order_by(AgentChatMessage.id.desc())
            .limit(CHAT_HISTORY_MESSAGE_LIMIT)
            .all()
        )
    )
    history: list[dict] = []

    for message in messages:
        history.append(
            {
                "role": message.provider_role,
                "content": list(message.content or []),
            }
        )

        if message.provider_role != "assistant":
            continue

        calls = (
            db.query(AgentChatToolCall)
            .filter(AgentChatToolCall.message_id == message.id)
            .order_by(AgentChatToolCall.id.asc())
            .all()
        )
        if not calls:
            continue
        if any(call.status not in _RESOLVED_TOOL_STATUSES for call in calls):
            break

        tool_results = []
        for call in calls:
            status = "success" if call.status == "success" else "error"
            tool_results.append(
                {
                    "toolResult": {
                        "toolUseId": call.tool_use_id,
                        "content": [
                            {
                                "json": call.result
                                or {
                                    "status": call.status,
                                    "tool_name": call.tool_name,
                                }
                            }
                        ],
                        "status": status,
                    }
                }
            )
        history.append({"role": "user", "content": tool_results})

    return history


def _assistant_text(content: list[dict]) -> str:
    return "\n".join(
        str(block.get("text") or "").strip()
        for block in content
        if isinstance(block, dict) and block.get("text")
    ).strip()


def _tool_uses(content: list[dict]) -> list[dict]:
    result = []
    for block in content:
        if not isinstance(block, dict):
            continue
        tool_use = block.get("toolUse")
        if isinstance(tool_use, dict):
            result.append(tool_use)
    return result


def _pending_calls(
    db: Session,
    session_id: int,
) -> list[AgentChatToolCall]:
    return (
        db.query(AgentChatToolCall)
        .filter(
            AgentChatToolCall.session_id == session_id,
            AgentChatToolCall.status == "approval_required",
        )
        .order_by(AgentChatToolCall.id.asc())
        .all()
    )


def _clear_capacity(
    db: Session,
    session: AgentChatSession,
) -> None:
    session.pending_capacity = None
    session.updated_at = datetime.utcnow()
    db.commit()


def _fail_pending_turn(
    db: Session,
    session: AgentChatSession,
) -> None:
    refund_ai_capacity(db, session.pending_capacity)
    _clear_capacity(db, session)


def _run_model_until_pause_or_answer(
    db: Session,
    membership: OrganizationMembership,
    session: AgentChatSession,
) -> dict:
    settings = get_settings()
    tools = list_authorized_tools(
        db,
        membership,
        store_id=session.store_id,
        include_denied=False,
    )

    for _round in range(settings.agent_max_tool_rounds):
        try:
            response = converse(
                messages=_history(db, session),
                tools=tools,
                store_id=session.store_id,
                context=session.context or {},
            )
        except AgentModelError:
            _fail_pending_turn(db, session)
            raise

        content = list(response["message"].get("content") or [])
        tool_uses = _tool_uses(content)
        final_response = not tool_uses
        usage = response.get("usage") or {}

        message = AgentChatMessage(
            session_id=session.id,
            provider_role="assistant",
            text=_assistant_text(content),
            content=content,
            model_id=response.get("model_id"),
            stop_reason=response.get("stop_reason"),
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            billable=final_response,
            created_at=datetime.utcnow(),
        )
        db.add(message)
        db.flush()

        if final_response:
            session.updated_at = datetime.utcnow()
            session.pending_capacity = None
            db.commit()
            db.refresh(session)
            return serialize_session(db, session)

        for tool_use in tool_uses:
            tool_name = str(tool_use.get("name") or "")
            arguments = tool_use.get("input")
            if not isinstance(arguments, dict):
                arguments = {}
            tool = get_tool(tool_name)
            call = AgentChatToolCall(
                session_id=session.id,
                message_id=message.id,
                tool_use_id=str(tool_use.get("toolUseId") or ""),
                tool_name=tool_name,
                action=tool.action if tool else "",
                arguments=_json_safe(arguments),
                status="pending",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(call)
            db.flush()

            execution = execute_agent_tool(
                db,
                membership,
                tool_name=tool_name,
                store_id=session.store_id,
                arguments=arguments,
            )
            call.result = _json_safe(execution)
            if execution.get("status") == "confirmation_required":
                call.status = "approval_required"
                approval = execution.get("approval") or {}
                call.approval_id = approval.get("id")
            else:
                call.status = str(execution.get("status") or "error")
                if call.status not in _RESOLVED_TOOL_STATUSES:
                    call.status = "error"
            call.updated_at = datetime.utcnow()
            db.commit()

        session.updated_at = datetime.utcnow()
        db.commit()

        if _pending_calls(db, session.id):
            db.refresh(session)
            return serialize_session(db, session)

    fallback = AgentChatMessage(
        session_id=session.id,
        provider_role="assistant",
        text=(
            "No pude completar el flujo de herramientas dentro del límite seguro "
            "de esta ejecución. Revisa los resultados y vuelve a intentarlo."
        ),
        content=[
            {
                "text": (
                    "No pude completar el flujo de herramientas dentro del límite "
                    "seguro de esta ejecución. Revisa los resultados y vuelve a intentarlo."
                )
            }
        ],
        model_id=settings.agent_model_id,
        stop_reason="tool_round_limit",
        billable=True,
        created_at=datetime.utcnow(),
    )
    db.add(fallback)
    session.pending_capacity = None
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return serialize_session(db, session)


def send_chat_message(
    db: Session,
    membership: OrganizationMembership,
    session_id: int,
    *,
    text: str,
    context: dict | None = None,
) -> dict:
    session = _require_session(db, membership, session_id)
    if session.status != "active":
        raise AgentChatError("CHAT_SESSION_NOT_ACTIVE")
    if _pending_calls(db, session.id) or session.pending_capacity is not None:
        raise AgentChatError("CHAT_APPROVAL_PENDING")

    clean_text = (text or "").strip()
    if not clean_text:
        raise AgentChatError("CHAT_MESSAGE_REQUIRED")
    if len(clean_text) > 8000:
        raise AgentChatError("CHAT_MESSAGE_TOO_LONG")

    reservation = acquire_ai_capacity(
        db,
        membership.organization_id,
    )
    if not reservation.get("available"):
        raise AgentChatError(
            str(reservation.get("reason") or "AI_USAGE_EXHAUSTED").upper()
        )

    session.pending_capacity = reservation
    if context:
        merged_context = dict(session.context or {})
        merged_context.update(context)
        session.context = merged_context
    if session.title == "Nuevo chat":
        session.title = clean_text.replace("\n", " ")[:80]
    session.updated_at = datetime.utcnow()

    message = AgentChatMessage(
        session_id=session.id,
        provider_role="user",
        text=clean_text,
        content=[{"text": clean_text}],
        billable=False,
        created_at=datetime.utcnow(),
    )
    db.add(message)
    db.commit()

    try:
        return _run_model_until_pause_or_answer(
            db,
            membership,
            session,
        )
    except Exception:
        if session.pending_capacity:
            _fail_pending_turn(db, session)
        raise


def _require_chat_tool_call(
    db: Session,
    membership: OrganizationMembership,
    session: AgentChatSession,
    approval_id: int,
) -> AgentChatToolCall:
    call = (
        db.query(AgentChatToolCall)
        .filter(
            AgentChatToolCall.session_id == session.id,
            AgentChatToolCall.approval_id == approval_id,
            AgentChatToolCall.status == "approval_required",
        )
        .first()
    )
    if call is None:
        raise AgentChatError("CHAT_APPROVAL_NOT_FOUND")
    return call


def _resume_if_ready(
    db: Session,
    membership: OrganizationMembership,
    session: AgentChatSession,
) -> dict:
    if _pending_calls(db, session.id):
        db.refresh(session)
        return serialize_session(db, session)
    if session.pending_capacity is None:
        raise AgentChatError("CHAT_TURN_NOT_PENDING")
    return _run_model_until_pause_or_answer(db, membership, session)


def approve_chat_action(
    db: Session,
    membership: OrganizationMembership,
    session_id: int,
    approval_id: int,
) -> dict:
    session = _require_session(db, membership, session_id)
    call = _require_chat_tool_call(
        db,
        membership,
        session,
        approval_id,
    )
    try:
        approve_action(db, membership, approval_id)
    except AgentApprovalError as exc:
        raise AgentChatError(str(exc)) from exc

    execution = execute_agent_tool(
        db,
        membership,
        tool_name=call.tool_name,
        store_id=session.store_id,
        arguments=dict(call.arguments or {}),
        approval_id=approval_id,
    )
    call.result = _json_safe(execution)
    call.status = str(execution.get("status") or "error")
    if call.status not in _RESOLVED_TOOL_STATUSES:
        call.status = "error"
    call.updated_at = datetime.utcnow()
    db.commit()

    return _resume_if_ready(db, membership, session)


def cancel_chat_action(
    db: Session,
    membership: OrganizationMembership,
    session_id: int,
    approval_id: int,
) -> dict:
    session = _require_session(db, membership, session_id)
    call = _require_chat_tool_call(
        db,
        membership,
        session,
        approval_id,
    )
    try:
        cancel_action(db, membership, approval_id)
    except AgentApprovalError as exc:
        raise AgentChatError(str(exc)) from exc

    call.status = "cancelled"
    call.result = {
        "status": "cancelled",
        "tool_name": call.tool_name,
        "message": "User cancelled the proposed action.",
    }
    call.updated_at = datetime.utcnow()
    db.commit()

    return _resume_if_ready(db, membership, session)


__all__ = [
    "AgentChatError",
    "approve_chat_action",
    "archive_chat_session",
    "cancel_chat_action",
    "create_chat_session",
    "get_chat_session",
    "list_chat_sessions",
    "send_chat_message",
    "serialize_session",
]
