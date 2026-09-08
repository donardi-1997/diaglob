"""Conversation business orchestration service.

Handles AI/RAG message generation and commerce context coordination.
Does NOT import FastAPI.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..ai_generation import generate_grounded_answer
from ..commerce import search_products
from ..models import Agent, Conversation, Message
from ..rag import retrieve_agent_knowledge

logger = logging.getLogger(__name__)


class ConversationNotFoundError(Exception):
    pass


def create_message_with_ai(
    db: Session,
    conversation: Conversation,
    sender: str,
    text: str,
) -> dict:
    """Persist user message, optionally generate AI response.

    CRITICAL: User message is committed BEFORE AI generation runs.
    This ensures the message is never lost even if AI fails.

    Returns serialized message dict.
    """
    message = Message(
        conversation_id=conversation.id,
        sender=sender,
        text=text,
        agent_id=(
            conversation.agent_id
            if sender == "ai"
            else None
        ),
    )

    db.add(message)

    conversation.preview = text
    conversation.updated_at = datetime.utcnow()

    if sender == "customer":
        conversation.unread = (conversation.unread or 0) + 1
    else:
        conversation.unread = 0

    # CRITICAL: commit user message before AI generation
    db.commit()
    db.refresh(message)

    serialized_message = {
        "id": message.id,
        "sender": message.sender,
        "text": message.text,
        "time": message.created_at.strftime("%H:%M"),
    }

    if message.agent:
        serialized_message["agent"] = {
            "id": message.agent.id,
            "name": message.agent.name,
            "role": message.agent.role,
        }

    # Decide if AI should respond
    should_generate_ai = (
        sender == "customer"
        and conversation.mode == "ai"
        and conversation.agent_id is not None
    )

    if not should_generate_ai:
        return serialized_message

    agent = conversation.assigned_agent

    if (
        not agent
        or not agent.active
        or agent.organization_id != conversation.organization_id
    ):
        return serialized_message

    # Agent must serve this store
    agent_store_ids = {
        agent_store.id
        for agent_store in agent.stores
        if agent_store.active
    }

    if conversation.store_id not in agent_store_ids:
        return serialized_message

    # RAG + AI generation
    try:
        evidence = retrieve_agent_knowledge(
            agent=agent,
            query=text,
            store_id=conversation.store_id,
            number_of_results=5,
        )

        conversation_store = conversation.store

        commerce_results = search_products(
            db=db,
            organization_id=conversation.organization_id,
            store_id=conversation.store_id,
            query=text,
            limit=5,
        )

        ai_result = generate_grounded_answer(
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
            commerce_results=commerce_results,
        )

        # Handle both dict and string returns (backward compatibility)
        if isinstance(ai_result, dict):
            answer = ai_result.get("answer", "")
            input_tokens = ai_result.get("input_tokens", 0)
            output_tokens = ai_result.get("output_tokens", 0)
        else:
            answer = ai_result
            input_tokens = 0
            output_tokens = 0

        if not answer:
            return serialized_message

        # Analytics: AI usage metering
        from .product_analytics import capture
        if input_tokens > 0 or output_tokens > 0:
            capture(
                "ai_interaction_completed",
                distinct_id=f"org:{conversation.organization_id}",
                properties={
                    "organization_id": conversation.organization_id,
                    "store_id": conversation.store_id,
                    "feature": "conversation_reply",
                    "model": "amazon.nova-2-lite-v1",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                },
            )

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

        # Analytics: first WhatsApp AI reply per store (not per conversation)
        from .product_analytics import track_first_whatsapp_ai_reply
        from ..models import Conversation as ConversationModel, Message as MessageModel
        prior_ai_message = (
            db.query(MessageModel)
            .join(ConversationModel, MessageModel.conversation_id == ConversationModel.id)
            .filter(
                ConversationModel.organization_id == conversation.organization_id,
                ConversationModel.store_id == conversation.store_id,
                ConversationModel.channel == "WhatsApp",
                MessageModel.sender == "ai",
                MessageModel.id != ai_message.id,
            )
            .first()
        )
        if prior_ai_message is None:
            track_first_whatsapp_ai_reply(
                organization_id=conversation.organization_id,
                store_id=conversation.store_id,
                conversation_id=conversation.id,
            )

    except Exception:
        db.rollback()

    return serialized_message
