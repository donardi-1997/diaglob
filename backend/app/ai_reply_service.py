from datetime import datetime

from sqlalchemy.orm import Session

from .ai_generation import generate_grounded_answer
from .commerce import search_products
from .db import SessionLocal
from .integrations.telegram.client import send_message as send_telegram_text_message
from .models import (
    Agent,
    Conversation,
    Message,
    Store,
    WhatsAppConnection,
)
from .rag import retrieve_agent_knowledge
from .services.ai_usage_service import acquire_ai_capacity, refund_ai_capacity
from .services.order_intelligence import build_customer_order_context
from .telegram_models import TelegramConnection
from .telegram_security import decrypt_telegram_secret
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


def _deliver_answer(
    db: Session,
    conversation: Conversation,
    ai_message: Message,
    answer: str,
) -> None:
    channel = (conversation.channel or "").lower()

    if channel == "telegram":
        connection = (
            db.query(TelegramConnection)
            .filter(
                TelegramConnection.store_id == conversation.store_id,
                TelegramConnection.organization_id == conversation.organization_id,
                TelegramConnection.status == "connected",
            )
            .first()
        )
        ai_message.provider = "telegram"
        customer_phone = (
            conversation.customer.phone
            if conversation.customer
            else None
        )
        if (
            not connection
            or not customer_phone
            or not customer_phone.startswith("telegram:")
        ):
            ai_message.delivery_status = "failed"
            db.commit()
            return

        token = decrypt_telegram_secret(connection.bot_token_encrypted)
        chat_id = int(customer_phone.split(":", 1)[1])
        result = send_telegram_text_message(token, chat_id=chat_id, text=answer)
        ai_message.external_message_id = (
            str(result.get("message_id"))
            if result.get("message_id") is not None
            else None
        )
        ai_message.delivery_status = "sent"
        db.commit()
        return

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id == conversation.store_id,
            WhatsAppConnection.organization_id == conversation.organization_id,
            WhatsAppConnection.status == "connected",
        )
        .first()
    )
    ai_message.provider = "whatsapp"
    if not connection:
        ai_message.delivery_status = "failed"
        db.commit()
        return

    token = decrypt_whatsapp_secret(connection.access_token_encrypted)
    result = send_whatsapp_text_message(
        phone_number_id=connection.phone_number_id,
        access_token=token,
        to=conversation.customer.phone,
        text=answer,
    )
    ai_message.external_message_id = result.get("message_id")
    ai_message.delivery_status = "sent"
    db.commit()


def generate_auto_reply(
    conversation_id: int,
    db: Session | None = None,
) -> None:
    own_session = db is None

    if own_session:
        db = SessionLocal()

    capacity_reservation = None
    capacity_consumed = False

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

        capacity_reservation = acquire_ai_capacity(
            db, conversation.organization_id
        )
        if not capacity_reservation.get("available"):
            print(
                "[DIAGLOB AUTO-REPLY]",
                "ai_usage_exhausted, organization=",
                conversation.organization_id,
                "conversation=",
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

        order_context = build_customer_order_context(
            db,
            organization_id=conversation.organization_id,
            store_id=conversation.store_id,
            customer_id=conversation.customer_id,
            question=last_message.text,
        )

        if order_context is None:
            commerce_results = search_products(
                db=db,
                organization_id=
                    conversation.organization_id,
                store_id=
                    conversation.store_id,
                query=last_message.text,
                limit=5,
            )
        else:
            commerce_results = []

        ai_result = generate_grounded_answer(
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
            order_context=
                order_context,
        )

        if isinstance(ai_result, dict):
            answer = ai_result.get("answer", "")
            input_tokens = ai_result.get("input_tokens", 0)
            output_tokens = ai_result.get("output_tokens", 0)
        else:
            answer = ai_result
            input_tokens = 0
            output_tokens = 0

        if not answer:
            refund_ai_capacity(db, capacity_reservation)
            capacity_reservation = None
            print(
                "[DIAGLOB AUTO-REPLY]",
                "empty_answer, conversation=",
                conversation_id,
            )
            return

        if input_tokens > 0 or output_tokens > 0:
            from .services.product_analytics import capture

            capture(
                "ai_interaction_completed",
                distinct_id=f"org:{conversation.organization_id}",
                properties={
                    "organization_id": conversation.organization_id,
                    "store_id": conversation.store_id,
                    "feature": "conversation_auto_reply",
                    "channel": (conversation.channel or "internal").lower(),
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
            provider="internal",
            created_at=datetime.utcnow(),
        )

        db.add(ai_message)
        conversation.preview = answer
        conversation.unread = 0
        conversation.updated_at = datetime.utcnow()
        db.commit()
        capacity_consumed = True
        db.refresh(ai_message)

        try:
            _deliver_answer(db, conversation, ai_message, answer)
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
            ai_message.provider = (conversation.channel or "internal").lower()
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
        if capacity_reservation and not capacity_consumed:
            try:
                db.rollback()
                refund_ai_capacity(db, capacity_reservation)
            except Exception as refund_exc:
                print(
                    "[DIAGLOB AUTO-REPLY]",
                    "capacity_refund_failed, conversation=",
                    conversation_id,
                    "error=",
                    repr(refund_exc),
                )
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