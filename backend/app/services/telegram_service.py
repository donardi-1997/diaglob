"""Telegram connection lifecycle and outbound messaging service."""

from __future__ import annotations

import os
import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from ..integrations.telegram.client import (
    TelegramClientError,
    delete_webhook,
    get_me,
    send_message as telegram_send_message,
    set_webhook,
)
from ..models import Conversation, Customer, Message, Store
from ..telegram_models import TelegramConnection
from ..telegram_security import decrypt_telegram_secret, encrypt_telegram_secret


class TelegramConnectionError(Exception):
    pass


class TelegramNotConnectedError(Exception):
    pass


class TelegramNotFoundError(Exception):
    pass


class TelegramSendError(Exception):
    pass


def _webhook_base_url() -> str:
    return os.getenv("TELEGRAM_WEBHOOK_BASE_URL", "https://api.diaglob.tech").rstrip("/")


def get_connection(db: Session, organization_id: int, store_id: int) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise TelegramNotFoundError("Store not found")

    connection = db.query(TelegramConnection).filter(
        TelegramConnection.organization_id == organization_id,
        TelegramConnection.store_id == store_id,
    ).first()
    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "bot_id": None,
            "bot_username": None,
            "bot_name": None,
            "connected_at": None,
            "last_error": None,
        }

    return {
        "connected": connection.status == "connected",
        "status": connection.status,
        "bot_id": connection.bot_id,
        "bot_username": connection.bot_username,
        "bot_name": connection.bot_name,
        "connected_at": connection.connected_at.isoformat() + "Z" if connection.connected_at else None,
        "last_error": connection.last_error,
    }


def connect(db: Session, organization_id: int, store_id: int, bot_token: str) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise TelegramNotFoundError("Store not found")
    if not store.active:
        raise TelegramConnectionError("STORE_NOT_ACTIVE")

    existing = db.query(TelegramConnection).filter(
        TelegramConnection.store_id == store_id
    ).first()
    if existing:
        raise TelegramConnectionError("TELEGRAM_ALREADY_CONNECTED")

    token = (bot_token or "").strip()
    if not token:
        raise TelegramConnectionError("TELEGRAM_TOKEN_REQUIRED")

    try:
        bot = get_me(token)
    except TelegramClientError as exc:
        raise TelegramConnectionError("TELEGRAM_TOKEN_INVALID") from exc

    bot_id = int(bot["id"])
    conflicting = db.query(TelegramConnection).filter(
        TelegramConnection.bot_id == bot_id
    ).first()
    if conflicting:
        raise TelegramConnectionError("TELEGRAM_BOT_IN_USE")

    webhook_secret = secrets.token_urlsafe(32)
    webhook_path_token = secrets.token_urlsafe(36)

    try:
        encrypted_token = encrypt_telegram_secret(token)
        encrypted_webhook_secret = encrypt_telegram_secret(webhook_secret)
    except (RuntimeError, ValueError) as exc:
        raise TelegramConnectionError("TELEGRAM_ENCRYPTION_FAILED") from exc

    webhook_url = (
        f"{_webhook_base_url()}/api/webhooks/telegram/{webhook_path_token}"
    )
    try:
        if not set_webhook(
            token,
            webhook_url=webhook_url,
            secret_token=webhook_secret,
        ):
            raise TelegramClientError("Telegram rejected webhook")
    except TelegramClientError as exc:
        raise TelegramConnectionError("TELEGRAM_WEBHOOK_FAILED") from exc

    now = datetime.utcnow()
    connection = TelegramConnection(
        organization_id=organization_id,
        store_id=store_id,
        bot_id=bot_id,
        bot_username=bot.get("username"),
        bot_name=bot.get("first_name"),
        bot_token_encrypted=encrypted_token,
        webhook_secret_encrypted=encrypted_webhook_secret,
        webhook_path_token=webhook_path_token,
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
        try:
            delete_webhook(token)
        except Exception:
            pass
        raise TelegramConnectionError("TELEGRAM_SAVE_FAILED") from exc

    return {
        "ok": True,
        "connected": True,
        "store_id": store_id,
        "status": connection.status,
        "bot_id": connection.bot_id,
        "bot_username": connection.bot_username,
        "bot_name": connection.bot_name,
    }


def disconnect(db: Session, organization_id: int, store_id: int) -> dict:
    connection = db.query(TelegramConnection).filter(
        TelegramConnection.organization_id == organization_id,
        TelegramConnection.store_id == store_id,
    ).first()
    if not connection:
        raise TelegramNotConnectedError("TELEGRAM_NOT_CONNECTED")

    try:
        token = decrypt_telegram_secret(connection.bot_token_encrypted)
        delete_webhook(token)
    except Exception as exc:
        connection.last_error = str(exc)
        db.commit()
        raise TelegramConnectionError("TELEGRAM_DISCONNECT_FAILED") from exc

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
        raise TelegramNotFoundError("Conversation not found")
    if (conversation.channel or "").lower() != "telegram":
        raise TelegramSendError("TELEGRAM_CONVERSATION_REQUIRED")

    connection = db.query(TelegramConnection).filter(
        TelegramConnection.organization_id == organization_id,
        TelegramConnection.store_id == conversation.store_id,
        TelegramConnection.status == "connected",
    ).first()
    if not connection:
        raise TelegramNotConnectedError("TELEGRAM_NOT_CONNECTED")

    customer = db.query(Customer).filter(Customer.id == conversation.customer_id).first()
    if not customer or not customer.phone.startswith("telegram:"):
        raise TelegramSendError("TELEGRAM_CHAT_NOT_FOUND")

    clean_text = (text or "").strip()
    if not clean_text:
        raise TelegramSendError("Message text is required")

    try:
        chat_id = int(customer.phone.split(":", 1)[1])
        token = decrypt_telegram_secret(connection.bot_token_encrypted)
        result = telegram_send_message(token, chat_id=chat_id, text=clean_text)
    except (ValueError, RuntimeError, TelegramClientError) as exc:
        connection.last_error = str(exc)
        db.commit()
        raise TelegramSendError("TELEGRAM_SEND_FAILED") from exc

    external_id = str(result.get("message_id")) if result.get("message_id") is not None else None
    message = Message(
        conversation_id=conversation.id,
        sender=sender,
        text=clean_text,
        provider="telegram",
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
