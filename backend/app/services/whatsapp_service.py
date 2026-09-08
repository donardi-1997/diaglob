"""WhatsApp connection and outbound message service.

Handles connection CRUD, template management, and outbound message orchestration.
Does NOT import FastAPI.
"""
import logging
import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import (
    Conversation,
    Customer,
    Message,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
    Store,
)
from ..whatsapp_client import (
    list_whatsapp_templates,
    send_whatsapp_text_message,
)
from ..whatsapp_security import (
    decrypt_whatsapp_secret,
    encrypt_whatsapp_secret,
)

logger = logging.getLogger(__name__)


class WhatsAppConnectionError(Exception):
    pass


class WhatsAppNotConnectedError(Exception):
    pass


class WhatsAppNotFoundError(Exception):
    pass


class WhatsAppSendError(Exception):
    pass


def _serialize_whatsapp_template(template) -> dict:
    return {
        "id": template.id,
        "provider_template_name": template.provider_template_name,
        "language_code": template.language_code,
        "category": template.category,
        "status": template.status,
        "components": template.components,
        "updated_at": template.updated_at.isoformat() + "Z" if template.updated_at else None,
    }


def get_connection(db: Session, organization_id: int, store_id: int) -> dict:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if not store:
        raise WhatsAppNotFoundError("Store not found")

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id == store.id,
            WhatsAppConnection.organization_id == organization_id,
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "phone_number_id": None,
            "business_account_id": None,
            "connected_at": None,
            "last_error": None,
        }

    return {
        "connected": connection.status == "connected",
        "status": connection.status,
        "phone_number_id": connection.phone_number_id,
        "business_account_id": connection.business_account_id,
        "verify_token": connection.verify_token,
        "connected_at": (
            connection.connected_at.isoformat() + "Z"
            if connection.connected_at
            else None
        ),
        "last_error": connection.last_error,
    }


def connect(db: Session, organization_id: int, store_id: int, phone_number_id: str, business_account_id: str, access_token: str) -> dict:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if not store:
        raise WhatsAppNotFoundError("Store not found")

    if not store.active:
        raise WhatsAppConnectionError("STORE_NOT_ACTIVE")

    existing = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.store_id == store.id)
        .first()
    )
    if existing:
        raise WhatsAppConnectionError("WHATSAPP_ALREADY_CONNECTED")

    phone_id = (phone_number_id or "").strip()
    biz_id = (business_account_id or "").strip()
    token = (access_token or "").strip()

    if not (phone_id and biz_id and token):
        raise WhatsAppConnectionError("WHATSAPP_FIELDS_REQUIRED")

    conflicting = (
        db.query(WhatsAppConnection)
        .filter(WhatsAppConnection.phone_number_id == phone_id)
        .first()
    )
    if conflicting:
        raise WhatsAppConnectionError("WHATSAPP_PHONE_IN_USE")

    try:
        encrypted_token = encrypt_whatsapp_secret(token)
    except (RuntimeError, ValueError) as exc:
        raise WhatsAppConnectionError("WHATSAPP_ENCRYPTION_FAILED") from exc

    now = datetime.utcnow()
    verify_token = secrets.token_urlsafe(48)

    connection = WhatsAppConnection(
        organization_id=organization_id,
        store_id=store.id,
        phone_number_id=phone_id,
        business_account_id=biz_id,
        access_token_encrypted=encrypted_token,
        verify_token=verify_token,
        status="connected",
        connected_at=now,
        last_error=None,
        created_at=now,
        updated_at=now,
    )

    db.add(connection)

    try:
        db.commit()
        db.refresh(connection)
    except Exception:
        db.rollback()
        raise WhatsAppConnectionError("WHATSAPP_SAVE_FAILED")

    return {
        "ok": True,
        "connected": True,
        "store_id": store.id,
        "status": connection.status,
        "phone_number_id": connection.phone_number_id,
        "verify_token": connection.verify_token,
    }


def disconnect(db: Session, organization_id: int, store_id: int) -> dict:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if not store:
        raise WhatsAppNotFoundError("Store not found")

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id == store.id,
            WhatsAppConnection.organization_id == organization_id,
        )
        .first()
    )
    if not connection:
        raise WhatsAppNotConnectedError("WHATSAPP_NOT_CONNECTED")

    db.delete(connection)
    db.commit()

    return {"ok": True, "connected": False, "store_id": store.id}


def list_templates(db: Session, organization_id: int, store_id: int) -> dict:
    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id == store_id,
            WhatsAppConnection.organization_id == organization_id,
        )
        .first()
    )
    if not connection:
        return {"items": []}

    templates = (
        db.query(WhatsAppMessageTemplate)
        .filter(
            WhatsAppMessageTemplate.organization_id == organization_id,
            WhatsAppMessageTemplate.whatsapp_connection_id == connection.id,
        )
        .order_by(WhatsAppMessageTemplate.provider_template_name)
        .all()
    )
    return {"items": [_serialize_whatsapp_template(item) for item in templates]}


def sync_templates(db: Session, organization_id: int, store_id: int) -> dict:
    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id == store_id,
            WhatsAppConnection.organization_id == organization_id,
            WhatsAppConnection.status == "connected",
        )
        .first()
    )
    if not connection:
        raise WhatsAppConnectionError("WhatsApp connection is not connected")

    try:
        provider_templates = list_whatsapp_templates(
            connection.business_account_id,
            decrypt_whatsapp_secret(connection.access_token_encrypted),
        )
    except Exception as exc:
        raise WhatsAppConnectionError("Unable to sync WhatsApp templates") from exc

    for item in provider_templates:
        name, language = item.get("name"), item.get("language")
        if not name or not language:
            continue

        template = (
            db.query(WhatsAppMessageTemplate)
            .filter(
                WhatsAppMessageTemplate.whatsapp_connection_id == connection.id,
                WhatsAppMessageTemplate.provider_template_name == name,
                WhatsAppMessageTemplate.language_code == language,
            )
            .first()
        )

        values = {
            "provider_template_id": item.get("id"),
            "category": item.get("category"),
            "status": str(item.get("status", "pending")).lower(),
            "components": {"items": item.get("components") or []},
        }

        if template:
            for key, value in values.items():
                setattr(template, key, value)
        else:
            db.add(WhatsAppMessageTemplate(
                organization_id=organization_id,
                whatsapp_connection_id=connection.id,
                provider_template_name=name,
                language_code=language,
                **values,
            ))

    db.commit()
    return list_templates(db, organization_id, store_id)


def send_message(db: Session, organization_id: int, conversation_id: int, text: str) -> dict:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
        )
        .first()
    )
    if not conversation:
        raise WhatsAppNotFoundError("Conversation not found")

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id == conversation.store_id,
            WhatsAppConnection.organization_id == organization_id,
            WhatsAppConnection.status == "connected",
        )
        .first()
    )
    if not connection:
        raise WhatsAppNotConnectedError("WHATSAPP_NOT_CONNECTED")

    customer = db.query(Customer).filter(Customer.id == conversation.customer_id).first()
    if not customer:
        raise WhatsAppNotFoundError("Customer not found")

    text = (text or "").strip()
    if not text:
        raise WhatsAppSendError("Message text is required")

    try:
        token = decrypt_whatsapp_secret(connection.access_token_encrypted)
        result = send_whatsapp_text_message(
            phone_number_id=connection.phone_number_id,
            access_token=token,
            to=customer.phone,
            text=text,
        )
    except RuntimeError as exc:
        connection.last_error = str(exc)
        db.commit()
        raise WhatsAppSendError("WHATSAPP_SEND_FAILED") from exc

    external_id = result.get("message_id")

    message = Message(
        conversation_id=conversation.id,
        sender="human",
        text=text,
        provider="whatsapp",
        external_message_id=external_id,
        delivery_status="sent",
        created_at=datetime.utcnow(),
    )

    db.add(message)
    conversation.preview = text
    conversation.updated_at = datetime.utcnow()
    db.commit()

    return {"ok": True, "message_id": message.id}
