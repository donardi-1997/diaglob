"""Conversations HTTP router."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai_generation import generate_grounded_answer
from ..commerce import search_products
from ..db import get_db
from ..models import (
    Agent,
    Conversation,
    Message,
    OrganizationMembership,
    Store,
)
from ..rag import retrieve_agent_knowledge
from .deps import get_allowed_store_ids, get_current_membership, get_store_scope, require_permission

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================
# DTO
# ============================================================

class MessageCreate(BaseModel):
    text: str
    sender: str = "human"

# ============================================================
# HELPERS
# ============================================================


def serialize_conversation(
    conversation: Conversation,
):
    customer = conversation.customer
    store = conversation.store

    profile = next(
        (
            item
            for item in customer.store_profiles
            if item.store_id == store.id
        ),
        None,
    )

    return {
        "id": conversation.id,

        "organization_id":
            conversation.organization_id,

        "store": {
            "id": store.id,
            "name": store.name,
            "country_code":
                store.country_code,
            "currency":
                store.currency,
            "timezone":
                store.timezone,
            "default_language":
                store.default_language,
        },

        "name": customer.name,
        "preview": conversation.preview,
        "time": format_relative_time(
            conversation.updated_at,
        ),
        "unread": conversation.unread,
        "channel": conversation.channel,
        "phone": customer.phone,
        "email": customer.email,
        "country_code":
            customer.country_code,

        "orders":
            profile.orders_count
            if profile
            else 0,

        "total_spent":
            float(profile.total_spent)
            if profile
            else 0,

        "currency":
            profile.currency
            if profile
            else store.currency,

        "last_order":
            profile.last_order_ref
            if profile
            else None,

        "agent": (
            {
                "id":
                    conversation.assigned_agent.id,
                "name":
                    conversation.assigned_agent.name,
                "role":
                    conversation.assigned_agent.role,
            }
            if conversation.assigned_agent
            else None
        ),

        "mode":
            conversation.mode,

        "tags": [
            tag
            for tag in conversation.tags.split(",")
            if tag
        ],
    }


def serialize_message(
    message: Message,
):
    data = {
        "id": message.id,
        "sender": message.sender,
        "text": message.text,
        "time": message.created_at.strftime(
            "%H:%M"
        ),
    }

    if message.agent:
        data["agent"] = {
            "id": message.agent.id,
            "name": message.agent.name,
            "role": message.agent.role,
        }

    return data


def format_relative_time(
    timestamp: datetime,
):
    delta = datetime.utcnow() - timestamp

    minutes = max(
        0,
        int(delta.total_seconds() / 60),
    )

    if minutes < 1:
        return "ahora"

    if minutes < 60:
        return f"{minutes} min"

    hours = minutes // 60

    if hours < 24:
        return f"{hours} h"

    days = hours // 24

    return f"{days} d"


def get_scoped_conversation(
    conversation_id: int,
    membership: OrganizationMembership,
    store: Store | None,
    db: Session,
):
    query = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.organization_id
            == membership.organization_id,
        )
    )

    if store is not None:
        query = query.filter(
            Conversation.store_id == store.id
        )

    else:
        allowed_store_ids = get_allowed_store_ids(
            membership
        )

        if allowed_store_ids is not None:
            if not allowed_store_ids:
                raise HTTPException(
                    status_code=404,
                    detail="Conversation not found",
                )

            query = query.filter(
                Conversation.store_id.in_(
                    allowed_store_ids
                )
            )

    conversation = query.first()

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return conversation


# ============================================================
# ROUTES
# ============================================================


@router.get("/api/conversations")
def list_conversations(
    membership: OrganizationMembership = Depends(
        require_permission("conversations.read")
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Conversation)
        .filter(
            Conversation.organization_id
            == membership.organization_id
        )
    )

    if store is not None:
        query = query.filter(
            Conversation.store_id == store.id
        )

    else:
        allowed_store_ids = get_allowed_store_ids(
            membership
        )

        if allowed_store_ids is not None:
            if not allowed_store_ids:
                conversations = []
            else:
                query = query.filter(
                    Conversation.store_id.in_(
                        allowed_store_ids
                    )
                )

                conversations = (
                    query
                    .order_by(
                        Conversation.updated_at.desc()
                    )
                    .all()
                )
        else:
            conversations = (
                query
                .order_by(
                    Conversation.updated_at.desc()
                )
                .all()
            )

    if store is not None:
        conversations = (
            query
            .order_by(
                Conversation.updated_at.desc()
            )
            .all()
        )

    return {
        "scope": {
            "organization_id":
                membership.organization_id,

            "store_id":
                store.id
                if store
                else None,

            "aggregate_view":
                store is None,

            "permission_scope":
                "all_stores"
                if membership.all_stores
                else "allowed_stores",
        },

        "items": [
            serialize_conversation(
                conversation
            )
            for conversation in conversations
        ],

        "total":
            len(conversations),
    }


@router.get(
    "/api/conversations/{conversation_id}"
)
def get_conversation(
    conversation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("conversations.read")
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    conversation = get_scoped_conversation(
        conversation_id,
        membership,
        store,
        db,
    )

    return {
        **serialize_conversation(
            conversation
        ),
        "messages": [
            serialize_message(message)
            for message in conversation.messages
        ],
    }


@router.patch(
    "/api/conversations/{conversation_id}/mode"
)
def update_conversation_mode(
    conversation_id: int,
    mode: str,
    membership: OrganizationMembership = Depends(
        require_permission("conversations.write")
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    if mode not in {"ai", "human"}:
        raise HTTPException(
            status_code=400,
            detail="Mode must be ai or human",
        )

    conversation = get_scoped_conversation(
        conversation_id,
        membership,
        store,
        db,
    )

    conversation.mode = mode
    conversation.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(conversation)

    return {
        "id": conversation.id,
        "mode": conversation.mode,
    }


@router.post(
    "/api/conversations/{conversation_id}/messages"
)
def create_message(
    conversation_id: int,
    payload: MessageCreate,
    membership: OrganizationMembership = Depends(
        require_permission("conversations.write")
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    conversation = get_scoped_conversation(
        conversation_id,
        membership,
        store,
        db,
    )

    text = payload.text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    if payload.sender not in {
        "human",
        "ai",
        "customer",
    }:
        raise HTTPException(
            status_code=400,
            detail="Invalid sender",
        )

    # ========================================================
    # 1. GUARDAR EL MENSAJE ORIGINAL
    # ========================================================

    message = Message(
        conversation_id=conversation.id,
        sender=payload.sender,
        text=text,
        agent_id=(
            conversation.agent_id
            if payload.sender == "ai"
            else None
        ),
    )

    db.add(message)

    conversation.preview = text
    conversation.updated_at = datetime.utcnow()

    if payload.sender == "customer":
        conversation.unread = (
            conversation.unread or 0
        ) + 1
    else:
        conversation.unread = 0

    # Confirmamos el mensaje antes de llamar a Bedrock.
    # Así nunca se pierde aunque falle la IA.
    db.commit()
    db.refresh(message)

    serialized_message = serialize_message(
        message
    )

    # ========================================================
    # 2. DECIDIR SI DEBE RESPONDER LA IA
    # ========================================================

    should_generate_ai = (
        payload.sender == "customer"
        and conversation.mode == "ai"
        and conversation.agent_id is not None
    )

    print(
        "[DIAGLOB AI]",
        "conversation=",
        conversation.id,
        "sender=",
        payload.sender,
        "mode=",
        conversation.mode,
        "agent_id=",
        conversation.agent_id,
        "should_generate=",
        should_generate_ai,
    )

    if not should_generate_ai:
        return serialized_message

    # ========================================================
    # 3. VALIDAR AGENTE
    # ========================================================

    agent = conversation.assigned_agent

    if (
        not agent
        or not agent.active
        or agent.organization_id
        != conversation.organization_id
    ):
        print(
            "[DIAGLOB AI SKIP]",
            "invalid_agent",
        )

        return serialized_message

    # El agente debe atender esta tienda.
    agent_store_ids = {
        agent_store.id
        for agent_store in agent.stores
        if agent_store.active
    }

    if conversation.store_id not in agent_store_ids:
        print(
            "[DIAGLOB AI SKIP]",
            "agent_not_available_for_store",
            conversation.store_id,
        )

        return serialized_message

    # ========================================================
    # 4. RAG + NOVA
    # ========================================================

    try:
        evidence = retrieve_agent_knowledge(
            agent=agent,
            query=text,
            store_id=conversation.store_id,
            number_of_results=5,
        )

        print(
            "[DIAGLOB AI]",
            "retrieval_results=",
            len(evidence),
        )

        conversation_store = conversation.store

        commerce_results = search_products(
            db=db,
            organization_id=
                conversation.organization_id,
            store_id=
                conversation.store_id,
            query=text,
            limit=5,
        )

        print(
            "[DIAGLOB COMMERCE]",
            "conversation=",
            conversation.id,
            "results=",
            len(commerce_results),
        )

        answer = generate_grounded_answer(
            question=text,
            evidence=evidence,
            agent_name=agent.name,
            agent_role=agent.role,
            store_name=(
                conversation_store.name
                if conversation_store
                else None
            ),
            country_code=(
                conversation_store.country_code
                if conversation_store
                else None
            ),
            currency=(
                conversation_store.currency
                if conversation_store
                else None
            ),
            timezone=(
                conversation_store.timezone
                if conversation_store
                else None
            ),
            language=(
                conversation_store.default_language
                if conversation_store
                else None
            ),
            commerce_results=
                commerce_results,
        )

        if not answer:
            print(
                "[DIAGLOB AI SKIP]",
                "empty_answer",
            )

            return serialized_message

        # ====================================================
        # 5. GUARDAR RESPUESTA IA
        # ====================================================

        ai_message = Message(
            conversation_id=conversation.id,
            agent_id=agent.id,
            sender="ai",
            text=answer,
        )

        db.add(ai_message)

        conversation.preview = answer
        conversation.unread = 0
        conversation.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(ai_message)

        print(
            "[DIAGLOB AI SUCCESS]",
            "conversation=",
            conversation.id,
            "message_id=",
            ai_message.id,
            "agent=",
            agent.name,
        )

    except Exception as exc:
        db.rollback()

        print(
            "[DIAGLOB AI ERROR]",
            "conversation=",
            conversation.id,
            "agent=",
            conversation.agent_id,
            "error=",
            repr(exc),
        )

    # Mantenemos el contrato original:
    # POST /messages devuelve el mensaje enviado.
    return serialized_message
