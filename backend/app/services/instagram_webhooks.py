"""Normalize Instagram messaging webhooks into the shared inbox."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..automations import safe_emit_event
from ..instagram_models import InstagramConnection
from ..models import Conversation, Customer, Message


def process_webhook_payload(db: Session, payload: dict) -> dict:
    if payload.get("object") != "instagram":
        return {
            "inbound_conversation_ids": [],
            "new_conversations": [],
            "new_messages": [],
        }

    inbound_ids: list[int] = []
    new_conversations: list[tuple] = []
    new_messages: list[tuple] = []

    for entry in payload.get("entry") or []:
        account_id = str(entry.get("id") or "").strip()
        if not account_id:
            continue
        connection = db.query(InstagramConnection).filter(
            InstagramConnection.instagram_account_id == account_id,
            InstagramConnection.status == "connected",
        ).first()
        if not connection:
            continue

        for event in entry.get("messaging") or []:
            message_payload = event.get("message") or {}
            if message_payload.get("is_echo"):
                continue
            text = (message_payload.get("text") or "").strip()
            external_id = str(message_payload.get("mid") or "").strip()
            sender_id = str((event.get("sender") or {}).get("id") or "").strip()
            if not text or not external_id or not sender_id:
                continue

            customer_key = f"instagram:{sender_id}"
            customer = db.query(Customer).filter(
                Customer.organization_id == connection.organization_id,
                Customer.phone == customer_key,
            ).first()
            if not customer:
                customer = Customer(
                    organization_id=connection.organization_id,
                    name=f"Instagram {sender_id[-6:]}",
                    phone=customer_key,
                )
                db.add(customer)
                db.flush()

            conversation = db.query(Conversation).filter(
                Conversation.organization_id == connection.organization_id,
                Conversation.store_id == connection.store_id,
                Conversation.customer_id == customer.id,
                Conversation.channel == "Instagram",
            ).first()

            if not conversation:
                conversation = Conversation(
                    organization_id=connection.organization_id,
                    store_id=connection.store_id,
                    customer_id=customer.id,
                    channel="Instagram",
                    preview=text,
                    unread=0,
                    mode="ai",
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(conversation)
                db.flush()
                new_conversations.append((conversation, connection))

            existing = db.query(Message).filter(
                Message.conversation_id == conversation.id,
                Message.provider == "instagram",
                Message.external_message_id == external_id,
            ).first()
            if existing:
                continue

            message = Message(
                conversation_id=conversation.id,
                sender="customer",
                text=text,
                provider="instagram",
                external_message_id=external_id,
                delivery_status="delivered",
                created_at=datetime.utcnow(),
            )
            db.add(message)
            conversation.preview = text
            conversation.unread = (conversation.unread or 0) + 1
            conversation.updated_at = datetime.utcnow()
            db.flush()
            inbound_ids.append(conversation.id)
            new_messages.append((message, conversation, connection))

    db.commit()
    return {
        "inbound_conversation_ids": list(dict.fromkeys(inbound_ids)),
        "new_conversations": new_conversations,
        "new_messages": new_messages,
    }


def emit_webhook_events(db: Session, new_conversations: list, new_messages: list) -> None:
    for conversation, _connection in new_conversations:
        safe_emit_event(
            db,
            conversation.organization_id,
            conversation.store_id,
            "conversation.created",
            {
                "conversation": {
                    "id": conversation.id,
                    "store_id": conversation.store_id,
                    "organization_id": conversation.organization_id,
                    "channel": "Instagram",
                    "mode": conversation.mode,
                },
                "customer_id": conversation.customer_id,
            },
            event_id=f"conversation:{conversation.id}:created",
        )

    for message, conversation, _connection in new_messages:
        safe_emit_event(
            db,
            conversation.organization_id,
            conversation.store_id,
            "message.received",
            {
                "customer_id": conversation.customer_id,
                "message": {
                    "id": message.id,
                    "conversation_id": conversation.id,
                    "sender": message.sender,
                    "channel": "instagram",
                    "text": message.text,
                },
                "conversation": {
                    "id": conversation.id,
                    "store_id": conversation.store_id,
                    "organization_id": conversation.organization_id,
                },
            },
            event_id=f"instagram-message:{message.external_message_id}",
        )
