"""Telegram V1 channel-delivery regression tests."""

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import ai_reply_service
from app.db import Base
from app.models import Conversation, Customer, Message, Organization, Store
from app.services.conversation_service import create_message_with_ai
from app.telegram_models import TelegramConnection
from app.telegram_security import encrypt_telegram_secret


def _session(monkeypatch):
    monkeypatch.setenv(
        "TELEGRAM_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode(),
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(Organization(id=1, name="Org", slug="org", plan="starter"))
    db.add(
        Store(
            id=1,
            organization_id=1,
            name="Store",
            slug="store",
            country_code="CO",
            currency="COP",
            timezone="America/Bogota",
            active=True,
        )
    )
    db.commit()
    return db


def _telegram_conversation(db):
    customer = Customer(
        organization_id=1,
        name="Ana",
        phone="telegram:9988",
    )
    db.add(customer)
    db.flush()
    conversation = Conversation(
        organization_id=1,
        store_id=1,
        customer_id=customer.id,
        channel="Telegram",
        mode="human",
    )
    db.add(conversation)
    db.flush()
    db.add(
        TelegramConnection(
            organization_id=1,
            store_id=1,
            bot_id=123,
            bot_username="diaglob_test_bot",
            bot_token_encrypted=encrypt_telegram_secret("123:secret"),
            webhook_secret_encrypted=encrypt_telegram_secret("hook-secret"),
            webhook_path_token="path-token",
            status="connected",
        )
    )
    db.commit()
    return conversation


def test_unified_inbox_human_reply_is_delivered_to_telegram(monkeypatch):
    db = _session(monkeypatch)
    conversation = _telegram_conversation(db)
    captured = {}

    def fake_send(token, *, chat_id, text):
        captured.update(token=token, chat_id=chat_id, text=text)
        return {"message_id": 501}

    from app.services import telegram_service

    monkeypatch.setattr(
        telegram_service,
        "telegram_send_message",
        fake_send,
    )

    result = create_message_with_ai(
        db=db,
        conversation=conversation,
        sender="human",
        text="Hola desde Diaglob",
    )

    assert captured == {
        "token": "123:secret",
        "chat_id": 9988,
        "text": "Hola desde Diaglob",
    }
    assert result["sender"] == "human"
    assert result["text"] == "Hola desde Diaglob"
    persisted = db.query(Message).one()
    assert persisted.provider == "telegram"
    assert persisted.external_message_id == "501"
    assert persisted.delivery_status == "sent"


def test_ai_delivery_uses_telegram_for_telegram_conversation(monkeypatch):
    db = _session(monkeypatch)
    conversation = _telegram_conversation(db)
    ai_message = Message(
        conversation_id=conversation.id,
        sender="ai",
        text="Respuesta IA",
        provider="internal",
    )
    db.add(ai_message)
    db.commit()
    captured = {}

    def fake_send(token, *, chat_id, text):
        captured.update(token=token, chat_id=chat_id, text=text)
        return {"message_id": 777}

    monkeypatch.setattr(
        ai_reply_service,
        "send_telegram_text_message",
        fake_send,
    )

    ai_reply_service._deliver_answer(
        db,
        conversation,
        ai_message,
        "Respuesta IA",
    )

    db.refresh(ai_message)
    assert captured == {
        "token": "123:secret",
        "chat_id": 9988,
        "text": "Respuesta IA",
    }
    assert ai_message.provider == "telegram"
    assert ai_message.external_message_id == "777"
    assert ai_message.delivery_status == "sent"
