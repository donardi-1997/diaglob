"""Channel-agnostic auto-reply dispatcher for conversational checkout turns."""
from datetime import datetime

from sqlalchemy.orm import Session

from .. import ai_reply_service
from ..models import Conversation, Message
from .conversational_checkout_service import process_conversational_checkout_turn


def generate_checkout_or_auto_reply(
    conversation_id: int,
    db: Session | None = None,
) -> None:
    """Use deterministic checkout state first; fall back to the normal LLM.

    When a background task owns the session, use the session factory exposed by
    ``ai_reply_service``. That is the existing auto-reply boundary and keeps
    tests, alternate DB bindings and production behavior on the same factory.
    """
    own_session = db is None
    if own_session:
        db = ai_reply_service.SessionLocal()

    assert db is not None
    try:
        conversation = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id)
            .first()
        )
        if not conversation or conversation.mode != "ai":
            return

        last_message = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .first()
        )
        if not last_message or last_message.sender != "customer":
            return

        if conversation.agent_id is None:
            agent = ai_reply_service._resolve_agent(
                db,
                conversation.organization_id,
                conversation.store_id,
            )
            if agent:
                conversation.agent_id = agent.id
                db.commit()
                db.refresh(conversation)
        agent = conversation.assigned_agent
        if (
            not agent
            or not agent.active
            or agent.organization_id != conversation.organization_id
        ):
            ai_reply_service.generate_auto_reply(conversation_id, db=db)
            return

        store_ids = {store.id for store in agent.stores if store.active}
        if conversation.store_id not in store_ids:
            ai_reply_service.generate_auto_reply(conversation_id, db=db)
            return

        answer = process_conversational_checkout_turn(
            db,
            conversation,
            agent,
            last_message.text,
        )
        if answer is None:
            ai_reply_service.generate_auto_reply(conversation_id, db=db)
            return

        ai_message = Message(
            conversation_id=conversation.id,
            agent_id=agent.id,
            sender="ai",
            text=answer,
            provider="internal",
            created_at=datetime.utcnow(),
        )
        db.add(ai_message)
        conversation.preview = answer
        conversation.unread = 0
        conversation.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(ai_message)

        try:
            ai_reply_service._deliver_answer(
                db,
                conversation,
                ai_message,
                answer,
            )
        except Exception:
            ai_message.provider = (conversation.channel or "internal").lower()
            ai_message.delivery_status = "failed"
            db.commit()
    finally:
        if own_session:
            db.close()
