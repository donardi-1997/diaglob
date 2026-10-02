"""Instagram connection lifecycle and outbound messaging."""

from __future__ import annotations

import os
from datetime import datetime

from sqlalchemy.orm import Session

from ..instagram_models import InstagramConnection
from ..instagram_security import (
    decrypt_instagram_secret,
    encrypt_instagram_secret,
)
from ..integrations.instagram.client import (
    InstagramClientError,
    get_account,
    send_message as instagram_send_message,
)
from ..models import Conversation, Customer, Message, Store


class InstagramConnectionError(Exception):
    pass


class InstagramNotConnectedError(Exception):
    pass


class InstagramNotFoundError(Exception):
    pass


class InstagramSendError(Exception):
    pass


def webhook_url() -> str:
    base = os.getenv(
        "INSTAGRAM_WEBHOOK_BASE_URL",
        os.getenv("PUBLIC_API_BASE_URL", "https://api.diaglob.tech"),
    ).rstrip("/")
    return f"{base}/api/webhooks/instagram"


def webhook_verify_token() -> str | None:
    token = os.getenv("INSTAGRAM_WEBHOOK_VERIFY_TOKEN", "").strip()
    return token or None


def get_connection(db: Session, organization_id: int, store_id: int) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise InstagramNotFoundError("Store not found")

    connection = db.query(InstagramConnection).filter(
        InstagramConnection.organization_id == organization_id,
        InstagramConnection.store_id == store_id,
    ).first()
    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "instagram_account_id": None,
            "page_id": None,
            "username": None,
            "connected_at": None,
            "last_error": None,
            "webhook_url": webhook_url(),
            "webhook_ready": webhook_verify_token() is not None,
        }

    return {
        "connected": connection.status == "connected",
        "status": connection.status,
        "instagram_account_id": connection.instagram_account_id,
        "page_id": connection.page_id,
        "username": connection.username,
        "connected_at": (
            connection.connected_at.isoformat() + "Z"
            if connection.connected_at
            else None
        ),
        "last_error": connection.last_error,
        "webhook_url": webhook_url(),
        "webhook_ready": webhook_verify_token() is not None,
    }


def connect(
    db: Session,
    organization_id: int,
    store_id: int,
    instagram_account_id: str,
    page_id: str | None,
    access_token: str,
) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise InstagramNotFoundError("Store not found")
    if not store.active:
        raise InstagramConnectionError("STORE_NOT_ACTIVE")

    account_id = (instagram_account_id or "").strip()
    token = (access_token or "").strip()
    if not account_id or not token:
        raise InstagramConnectionError("INSTAGRAM_FIELDS_REQUIRED")

    existing = db.query(InstagramConnection).filter(
        InstagramConnection.store_id == store_id
    ).first()
    if existing:
        raise InstagramConnectionError("INSTAGRAM_ALREADY_CONNECTED")

    conflicting = db.query(InstagramConnection).filter(
        InstagramConnection.instagram_account_id == account_id
    ).first()
    if conflicting:
        raise InstagramConnectionError("INSTAGRAM_ACCOUNT_IN_USE")

    try:
        account = get_account(token, account_id)
    except InstagramClientError as exc:
        raise InstagramConnectionError("INSTAGRAM_TOKEN_INVALID") from exc

    try:
        encrypted = encrypt_instagram_secret(token)
    except (RuntimeError, ValueError) as exc:
        raise InstagramConnectionError("INSTAGRAM_ENCRYPTION_FAILED") from exc

    now = datetime.utcnow()
    connection = InstagramConnection(
        organization_id=organization_id,
        store_id=store_id,
        instagram_account_id=account_id,
        page_id=(page_id or "").strip() or None,
        username=account.get("username") or account.get("name"),
        access_token_encrypted=encrypted,
        status="connected",
        connected_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(connection)
    try:
        db.commit()
        db.refresh(connection)
    except Exception as exc:
        db.rollback()
        raise InstagramConnectionError("INSTAGRAM_SAVE_FAILED") from exc

    return {
        "ok": True,
        "connected": True,
        "store_id": store_id,
        "status": connection.status,
        "instagram_account_id": connection.instagram_account_id,
        "page_id": connection.page_id,
        "username": connection.username,
        "webhook_url": webhook_url(),
        "webhook_ready": webhook_verify_token() is not None,
    }


def disconnect(db: Session, organization_id: int, store_id: int) -> dict:
    connection = db.query(InstagramConnection).filter(
        InstagramConnection.organization_id == organization_id,
        InstagramConnection.store_id == store_id,
    ).first()
    if not connection:
        raise InstagramNotConnectedError("INSTAGRAM_NOT_CONNECTED")
    db.delete(connection)
    db.commit()
    return {"ok": True, "connected": False, "store_id": store_id}


def send_message(
    db: Session,
    organization_id: int,
    conversation_id: int,
    text: str,
    *,
    sender: str = "human",
) -> dict:
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.organization_id == organization_id,
    ).first()
    if not conversation:
        raise InstagramNotFoundError("Conversation not found")
    if (conversation.channel or "").lower() != "instagram":
        raise InstagramSendError("INSTAGRAM_CONVERSATION_REQUIRED")

    connection = db.query(InstagramConnection).filter(
        InstagramConnection.organization_id == organization_id,
        InstagramConnection.store_id == conversation.store_id,
        InstagramConnection.status == "connected",
    ).first()
    if not connection:
        raise InstagramNotConnectedError("INSTAGRAM_NOT_CONNECTED")

    customer = db.query(Customer).filter(
        Customer.id == conversation.customer_id,
        Customer.organization_id == organization_id,
    ).first()
    if not customer or not customer.phone.startswith("instagram:"):
        raise InstagramSendError("INSTAGRAM_RECIPIENT_NOT_FOUND")

    clean_text = (text or "").strip()
    if not clean_text:
        raise InstagramSendError("Message text is required")

    recipient_id = customer.phone.split(":", 1)[1]
    try:
        token = decrypt_instagram_secret(connection.access_token_encrypted)
        result = instagram_send_message(
            token,
            instagram_account_id=connection.instagram_account_id,
            recipient_id=recipient_id,
            text=clean_text,
        )
    except (RuntimeError, InstagramClientError) as exc:
        connection.last_error = "INSTAGRAM_SEND_FAILED"
        db.commit()
        raise InstagramSendError("INSTAGRAM_SEND_FAILED") from exc

    external_id = (
        str(result.get("message_id") or result.get("id") or "").strip()
        or None
    )
    message = Message(
        conversation_id=conversation.id,
        sender=sender,
        text=clean_text,
        provider="instagram",
        external_message_id=external_id,
        delivery_status="sent",
        created_at=datetime.utcnow(),
    )
    db.add(message)
    conversation.preview = clean_text
    conversation.unread = 0
    conversation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(message)
    return {
        "ok": True,
        "message_id": message.id,
        "external_message_id": external_id,
        "id": message.id,
        "sender": message.sender,
        "text": message.text,
        "time": message.created_at.strftime("%H:%M"),
    }
