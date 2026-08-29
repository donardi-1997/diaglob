from datetime import datetime

from sqlalchemy.orm import Session

from .ai_generation import generate_grounded_answer
from .commerce import search_products
from .db import SessionLocal
from .models import (
    Agent,
    Conversation,
    Message,
    Store,
    WhatsAppConnection,
)
from .rag import retrieve_agent_knowledge
from .whatsapp_client import (
    send_whatsapp_text_message,
)
from .whatsapp_security import (
    decrypt_whatsapp_secret,
)


HANDOFF_KEYWORDS = [
    "hablar con alguien",
    "hablar con un asesor",
    "hablar con una asesora",
    "hablar con una persona",
    "hablar con humano",
    "quiero un asesor",
    "quiero una asesora",
    "atención al cliente",
    "servicio al cliente",
    "agente humano",
    "no eres real",
    "eres un robot",
    "talk to a human",
    "speak to a human",
    "talk to an agent",
    "speak to an agent",
    "talk to a person",
    "customer service",
    "human agent",
    "real person",
    "representative",
    "live agent",
]


def _detect_handoff(text: str) -> bool:
    normalized = text.lower().strip()
    return any(
        keyword in normalized
        for keyword in HANDOFF_KEYWORDS
    )


def _resolve_agent(
    db: Session,
    organization_id: int,
    store_id: int,
) -> Agent | None:
    return (
        db.query(Agent)
        .filter(
            Agent.organization_id
            == organization_id,
            Agent.active.is_(True),
            Agent.stores.any(
                Store.id == store_id
            ),
        )
        .first()
    )


def _build_history_text(
    db: Session,
    conversation_id: int,
) -> str:
    messages = (
        db.query(Message)
        .filter(
            Message.conversation_id
            == conversation_id,
            Message.sender.in_(
                ["customer", "ai", "human"]
            ),
        )
        .order_by(Message.id.desc())
        .limit(10)
        .all()
    )

    messages.reverse()

    lines = []
    for msg in messages:
        if msg.sender == "customer":
            prefix = "Cliente"
        elif msg.sender == "ai":
            prefix = "Asistente"
        else:
            prefix = "Agente"

        lines.append(
            f"{prefix}: {msg.text}"
        )

    return "\n".join(lines)


def generate_auto_reply(
    conversation_id: int,
    db: Session | None = None,
) -> None:
    own_session = db is None

    if own_session:
        db = SessionLocal()

    try:
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id
                == conversation_id,
            )
            .first()
        )

        if not conversation:
            print(
                "[DIAGLOB AUTO-REPLY]",
                "conversation_not_found=",
                conversation_id,
            )
            return

        if conversation.mode != "ai":
            print(
                "[DIAGLOB AUTO-REPLY]",
                "mode_not_ai, conversation=",
                conversation_id,
                "mode=",
                conversation.mode,
            )
            return

        if conversation.agent_id is None:
            agent = _resolve_agent(
                db,
                conversation.organization_id,
                conversation.store_id,
            )

            if agent:
                conversation.agent_id = agent.id
                db.commit()
                db.refresh(conversation)
            else:
                print(
                    "[DIAGLOB AUTO-REPLY]",
                    "no_agent_for_store, conversation=",
                    conversation_id,
                    "store=",
                    conversation.store_id,
                )
                return

        agent = conversation.assigned_agent

        if (
            not agent
            or not agent.active
            or agent.organization_id
            != conversation.organization_id
        ):
            print(
                "[DIAGLOB AUTO-REPLY]",
                "invalid_agent, conversation=",
                conversation_id,
            )
            return

        agent_store_ids = {
            s.id
            for s in agent.stores
            if s.active
        }

        if (
            conversation.store_id
            not in agent_store_ids
        ):
            print(
                "[DIAGLOB AUTO-REPLY]",
                "agent_not_for_store, conversation=",
                conversation_id,
                "store=",
                conversation.store_id,
            )
            return

        last_message = (
            db.query(Message)
            .filter(
                Message.conversation_id
                == conversation_id,
            )
            .order_by(Message.id.desc())
            .first()
        )

        if not last_message:
            return

        if last_message.sender != "customer":
            return

        if _detect_handoff(last_message.text):
            conversation.mode = "human"
            conversation.updated_at = (
                datetime.utcnow()
            )
            db.commit()
            print(
                "[DIAGLOB AUTO-REPLY]",
                "handoff_triggered, conversation=",
                conversation_id,
            )
            return

        history_text = _build_history_text(
            db, conversation_id
        )

        store = conversation.store

        evidence = retrieve_agent_knowledge(
            agent=agent,
            query=last_message.text,
            store_id=conversation.store_id,
            number_of_results=5,
        )

        commerce_results = search_products(
            db=db,
            organization_id=
                conversation.organization_id,
            store_id=
                conversation.store_id,
            query=last_message.text,
            limit=5,
        )

        answer = generate_grounded_answer(
            question=last_message.text,
            evidence=evidence,
            agent_name=agent.name,
            agent_role=agent.role,
            store_name=(
                store.name
                if store
                else None
            ),
            country_code=(
                store.country_code
                if store
                else None
            ),
            currency=(
                store.currency
                if store
                else None
            ),
            timezone=(
                store.timezone
                if store
                else None
            ),
            language=(
                store.default_language
                if store
                else None
            ),
            commerce_results=
                commerce_results,
            conversation_history=
                history_text,
        )

        if not answer:
            print(
                "[DIAGLOB AUTO-REPLY]",
                "empty_answer, conversation=",
                conversation_id,
            )
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
        conversation.updated_at = (
            datetime.utcnow()
        )

        db.commit()
        db.refresh(ai_message)

        connection = (
            db.query(WhatsAppConnection)
            .filter(
                WhatsAppConnection.store_id
                == conversation.store_id,
                WhatsAppConnection.organization_id
                == conversation.organization_id,
                WhatsAppConnection.status
                == "connected",
            )
            .first()
        )

        if not connection:
            ai_message.provider = "whatsapp"
            ai_message.delivery_status = "failed"
            db.commit()
            print(
                "[DIAGLOB AUTO-REPLY]",
                "no_connection, conversation=",
                conversation_id,
            )
            return

        try:
            token = decrypt_whatsapp_secret(
                connection.access_token_encrypted
            )

            result = send_whatsapp_text_message(
                phone_number_id=
                    connection.phone_number_id,
                access_token=token,
                to=conversation.customer.phone,
                text=answer,
            )

            ai_message.provider = "whatsapp"
            ai_message.external_message_id = (
                result.get("message_id")
            )
            ai_message.delivery_status = "sent"
            db.commit()

            print(
                "[DIAGLOB AUTO-REPLY]",
                "sent, conversation=",
                conversation_id,
                "message_id=",
                ai_message.id,
                "ext_id=",
                ai_message.external_message_id,
            )

        except Exception as exc:
            ai_message.provider = "whatsapp"
            ai_message.delivery_status = "failed"
            db.commit()

            print(
                "[DIAGLOB AUTO-REPLY]",
                "send_failed, conversation=",
                conversation_id,
                "error=",
                repr(exc),
            )

    except Exception as exc:
        print(
            "[DIAGLOB AUTO-REPLY]",
            "error, conversation=",
            conversation_id,
            "error=",
            repr(exc),
        )

    finally:
        if own_session:
            db.close()
