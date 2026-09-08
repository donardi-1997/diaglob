"""WhatsApp webhook event orchestration service.

Handles inbound message processing, status updates, automation event creation,
and AI auto-reply coordination. Does NOT import FastAPI.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..ai_reply_service import generate_auto_reply, _detect_handoff
from ..automations import safe_emit_event
from ..models import (
    Conversation,
    Customer,
    Message,
    WhatsAppConnection,
)

logger = logging.getLogger(__name__)


class WhatsAppWebhookError(Exception):
    pass


def process_webhook_payload(db: Session, payload: dict) -> dict:
    """Process a verified WhatsApp webhook payload.

    Returns dict with:
      - inbound_conversation_ids: list of conversation IDs that received messages
      - new_conversations: list of (conversation, connection) tuples for event emission
      - new_messages: list of (message, conversation, connection) tuples for event emission
    """
    entries = payload.get("entry") or []

    inbound_conversation_ids = []
    new_conversations = []
    new_messages = []

    for entry in entries:
        changes = entry.get("changes") or []

        for change in changes:
            if change.get("field") != "messages":
                continue

            value = change.get("value") or {}

            phone_number_id = (
                value.get("metadata", {}).get("phone_number_id") or ""
            )

            if not phone_number_id:
                continue

            connection = (
                db.query(WhatsAppConnection)
                .filter(
                    WhatsAppConnection.phone_number_id == phone_number_id,
                    WhatsAppConnection.status == "connected",
                )
                .first()
            )

            if not connection:
                continue

            messages = value.get("messages") or []
            statuses = value.get("statuses") or []
            contacts = value.get("contacts") or []

            contact_map = {
                c.get("wa_id"): c
                for c in contacts
                if c.get("wa_id")
            }

            for msg in messages:
                wa_id = msg.get("from") or ""
                msg_id = msg.get("id") or ""
                msg_type = msg.get("type") or ""

                if not wa_id or not msg_id:
                    continue

                if msg_type != "text":
                    continue

                text_body = msg.get("text", {}).get("body") or ""

                if not text_body:
                    continue

                customer = (
                    db.query(Customer)
                    .filter(
                        Customer.organization_id == connection.organization_id,
                        Customer.phone == wa_id,
                    )
                    .first()
                )

                if not customer:
                    contact = contact_map.get(wa_id) or {}
                    profile = contact.get("profile") or {}
                    name = profile.get("name") or wa_id

                    customer = Customer(
                        organization_id=connection.organization_id,
                        name=name,
                        phone=wa_id,
                    )
                    db.add(customer)
                    db.flush()

                conversation = (
                    db.query(Conversation)
                    .filter(
                        Conversation.organization_id == connection.organization_id,
                        Conversation.store_id == connection.store_id,
                        Conversation.customer_id == customer.id,
                        Conversation.channel == "WhatsApp",
                    )
                    .first()
                )

                if not conversation:
                    conversation = Conversation(
                        organization_id=connection.organization_id,
                        store_id=connection.store_id,
                        customer_id=customer.id,
                        channel="WhatsApp",
                        preview=text_body,
                        unread=1,
                        mode="ai",
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                    db.add(conversation)
                    db.flush()
                    new_conversations.append((conversation, connection))

                existing_msg = (
                    db.query(Message)
                    .filter(
                        Message.conversation_id == conversation.id,
                        Message.provider == "whatsapp",
                        Message.external_message_id == msg_id,
                    )
                    .first()
                )

                if not existing_msg:
                    message = Message(
                        conversation_id=conversation.id,
                        sender="customer",
                        text=text_body,
                        provider="whatsapp",
                        external_message_id=msg_id,
                        delivery_status="delivered",
                        created_at=datetime.utcnow(),
                    )
                    db.add(message)
                    new_messages.append((message, conversation, connection))

                    conversation.preview = text_body
                    conversation.unread += 1
                    conversation.updated_at = datetime.utcnow()

                    if conversation.id not in inbound_conversation_ids:
                        inbound_conversation_ids.append(conversation.id)

            for status_event in statuses:
                ext_msg_id = status_event.get("id") or ""
                new_status = status_event.get("status") or ""

                if not ext_msg_id or not new_status:
                    continue

                valid_statuses = {"sent", "delivered", "read", "failed"}

                if new_status not in valid_statuses:
                    continue

                existing = (
                    db.query(Message)
                    .filter(
                        Message.provider == "whatsapp",
                        Message.external_message_id == ext_msg_id,
                    )
                    .first()
                )

                if existing:
                    existing.delivery_status = new_status

                    conversation = (
                        db.query(Conversation)
                        .filter(Conversation.id == existing.conversation_id)
                        .first()
                    )

                    if conversation:
                        conversation.updated_at = datetime.utcnow()

    db.commit()

    return {
        "inbound_conversation_ids": inbound_conversation_ids,
        "new_conversations": new_conversations,
        "new_messages": new_messages,
    }


def emit_webhook_events(db: Session, new_conversations: list, new_messages: list):
    """Emit automation events for new conversations and messages."""
    from .product_analytics import track_first_whatsapp_inbound

    for conversation, connection in new_conversations:
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

        # Analytics: first WhatsApp inbound (new conversation = first contact)
        track_first_whatsapp_inbound(
            organization_id=conversation.organization_id,
            store_id=conversation.store_id,
            conversation_id=conversation.id,
        )

    for message, conversation, connection in new_messages:
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
                    "channel": "whatsapp",
                    "text": message.text,
                },
                "conversation": {
                    "id": conversation.id,
                    "store_id": conversation.store_id,
                    "organization_id": conversation.organization_id,
                },
            },
            event_id=f"whatsapp-message:{message.external_message_id}",
        )


def schedule_ai_replies(db: Session, inbound_conversation_ids: list[int], background_tasks) -> list[int]:
    """Check AI auto-reply eligibility and schedule background tasks.

    Returns list of conversation IDs that were handed off to human mode.
    """
    handed_off = []

    for cid in inbound_conversation_ids:
        conv = db.query(Conversation).filter(Conversation.id == cid).first()

        if not conv:
            continue

        if conv.mode != "ai":
            continue

        last_msg = (
            db.query(Message)
            .filter(Message.conversation_id == cid)
            .order_by(Message.id.desc())
            .first()
        )

        if not last_msg:
            continue

        if _detect_handoff(last_msg.text):
            conv.mode = "human"
            conv.updated_at = datetime.utcnow()
            db.commit()
            handed_off.append(cid)
            continue

        background_tasks.add_task(
            generate_auto_reply,
            conversation_id=cid,
        )

    return handed_off
