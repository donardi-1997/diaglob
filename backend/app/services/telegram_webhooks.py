"""Telegram webhook orchestration for private text messages."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..automations import safe_emit_event
from ..models import Conversation, Customer, Message
from ..telegram_models import TelegramConnection


def process_webhook_payload(
    db: Session,
    connection: TelegramConnection,
    payload: dict,
) -> dict:
    message_payload = payload.get("message") or {}
    chat = message_payload.get("chat") or {}
    sender = message_payload.get("from") or {}

    if chat.get("type") != "private":
        return {"inbound_conversation_ids": [], "new_conversations": [], "new_messages": []}

    text = (message_payload.get("text") or "").strip()
    message_id = message_payload.get("message_id")
    chat_id = chat.get("id")
    user_id = sender.get("id")
    if not text or message_id is None or chat_id is None or user_id is None:
        return {"inbound_conversation_ids": [], "new_conversations": [], "new_messages": []}

    customer_key = f"telegram:{int(chat_id)}"
    customer = db.query(Customer).filter(
        Customer.organization_id == connection.organization_id,
        Customer.phone == customer_key,
    ).first()
    if not customer:
        full_name = " ".join(
            part for part in [sender.get("first_name"), sender.get("last_name")] if part
        ).strip()
        customer = Customer(
            organization_id=connection.organization_id,
            name=full_name or sender.get("username") or customer_key,
            phone=customer_key,
        )
        db.add(customer)
        db.flush()

    conversation = db.query(Conversation).filter(
        Conversation.organization_id == connection.organization_id,
        Conversation.store_id == connection.store_id,
        Conversation.customer_id == customer.id,
        Conversation.channel == "Telegram",
    ).first()

    new_conversations = []
    if not conversation:
        conversation = Conversation(
            organization_id=connection.organization_id,
            store_id=connection.store_id,
            customer_id=customer.id,
            channel="Telegram",
            preview=text,
            unread=0,
            mode="ai",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(conversation)
        db.flush()
        new_conversations.append((conversation, connection))

    external_id = str(message_id)
    existing = db.query(Message).filter(
        Message.conversation_id == conversation.id,
        Message.provider == "telegram",
        Message.external_message_id == external_id,
    ).first()
    if existing:
        db.commit()
        return {
            "inbound_conversation_ids": [],
            "new_conversations": new_conversations,
            "new_messages": [],
        }

    message = Message(
        conversation_id=conversation.id,
        sender="customer",
        text=text,
        provider="telegram",
        external_message_id=external_id,
        delivery_status="delivered",
        created_at=datetime.utcnow(),
    )
    db.add(message)
    conversation.preview = text
    conversation.unread = (conversation.unread or 0) + 1
    conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)

    return {
        "inbound_conversation_ids": [conversation.id],
        "new_conversations": new_conversations,
        "new_messages": [(message, conversation, connection)],
    }


def emit_webhook_events(db: Session, new_conversations: list, new_messages: list) -> None:
    for conversation, _connection in new_conversations:
        safe_emit_event(
            db=db,
            organization_id=conversation.organization_id,
            store_id=conversation.store_id,
            event_type="conversation.created",
            payload={
                "conversation": {
                    "id": conversation.id,
                    "store_id": conversation.store_id,
                    "organization_id": conversation.organization_id,
                    "channel": conversation.channel,
                    "mode": conversation.mode,
                }
            },
            event_id=f"conversation:{conversation.id}:created",
        )

    for message, conversation, _connection in new_messages:
        safe_emit_event(
            db=db,
            organization_id=conversation.organization_id,
            store_id=conversation.store_id,
            event_type="message.received",
            payload={
                "message": {
                    "id": message.id,
                    "conversation_id": conversation.id,
                    "sender": message.sender,
                    "channel": "telegram",
                    "text": message.text,
                },
                "conversation": {
                    "id": conversation.id,
                    "store_id": conversation.store_id,
                    "organization_id": conversation.organization_id,
                },
            },
            event_id=f"telegram-message:{message.external_message_id}",
        )
