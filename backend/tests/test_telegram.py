"""Telegram V1 regression coverage."""

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Conversation, Customer, Message, Organization, Store
from app.services import telegram_service
from app.services.telegram_webhooks import process_webhook_payload
from app.telegram_models import TelegramConnection


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    session.add(Organization(id=1, name="Org", slug="org", plan="starter"))
    session.add(
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
    session.commit()
    return session


def test_connect_validates_bot_registers_webhook_and_encrypts(monkeypatch):
    db = _session()
    monkeypatch.setenv("TELEGRAM_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("TELEGRAM_WEBHOOK_BASE_URL", "https://api.diaglob.tech")

    captured = {}
    monkeypatch.setattr(
        telegram_service,
        "get_me",
        lambda token: {
            "id": 123456789,
            "is_bot": True,
            "username": "diaglob_test_bot",
            "first_name": "Diaglob Test",
        },
    )

    def fake_set_webhook(token, *, webhook_url, secret_token):
        captured.update(
            token=token,
            webhook_url=webhook_url,
            secret_token=secret_token,
        )
        return True

    monkeypatch.setattr(telegram_service, "set_webhook", fake_set_webhook)

    result = telegram_service.connect(db, 1, 1, "123:secret")
    connection = db.query(TelegramConnection).one()

    assert result["connected"] is True
    assert result["bot_username"] == "diaglob_test_bot"
    assert captured["token"] == "123:secret"
    assert captured["webhook_url"].startswith(
        "https://api.diaglob.tech/api/webhooks/telegram/"
    )
    assert connection.bot_token_encrypted != "123:secret"
    assert connection.webhook_secret_encrypted != captured["secret_token"]
    assert "123:secret" not in captured["webhook_url"]


def test_private_text_webhook_creates_customer_conversation_and_message(monkeypatch):
    db = _session()
    monkeypatch.setenv("TELEGRAM_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    connection = TelegramConnection(
        organization_id=1,
        store_id=1,
        bot_id=123,
        bot_username="diaglob_test_bot",
        bot_name="Diaglob",
        bot_token_encrypted="encrypted",
        webhook_secret_encrypted="encrypted",
        webhook_path_token="path",
        status="connected",
    )
    db.add(connection)
    db.commit()

    payload = {
        "update_id": 10,
        "message": {
            "message_id": 77,
            "from": {
                "id": 9988,
                "is_bot": False,
                "first_name": "Ana",
                "username": "ana_test",
            },
            "chat": {"id": 9988, "type": "private"},
            "text": "Hola, necesito ayuda",
        },
    }

    result = process_webhook_payload(db, connection, payload)

    customer = db.query(Customer).one()
    conversation = db.query(Conversation).one()
    message = db.query(Message).one()

    assert customer.phone == "telegram:9988"
    assert conversation.channel == "Telegram"
    assert conversation.store_id == 1
    assert message.provider == "telegram"
    assert message.external_message_id == "77"
    assert result["inbound_conversation_ids"] == [conversation.id]


def test_duplicate_message_is_idempotent(monkeypatch):
    db = _session()
    monkeypatch.setenv("TELEGRAM_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    connection = TelegramConnection(
        organization_id=1,
        store_id=1,
        bot_id=123,
        bot_username="bot",
        bot_token_encrypted="encrypted",
        webhook_secret_encrypted="encrypted",
        webhook_path_token="path",
        status="connected",
    )
    db.add(connection)
    db.commit()
    payload = {
        "message": {
            "message_id": 5,
            "from": {"id": 44, "first_name": "Jo"},
            "chat": {"id": 44, "type": "private"},
            "text": "hola",
        }
    }

    process_webhook_payload(db, connection, payload)
    second = process_webhook_payload(db, connection, payload)

    assert db.query(Message).filter(Message.provider == "telegram").count() == 1
    assert second["inbound_conversation_ids"] == []
    assert second["new_messages"] == []


def test_group_messages_are_ignored():
    db = _session()
    connection = TelegramConnection(
        organization_id=1,
        store_id=1,
        bot_id=123,
        bot_token_encrypted="encrypted",
        webhook_secret_encrypted="encrypted",
        webhook_path_token="path",
        status="connected",
    )
    db.add(connection)
    db.commit()

    result = process_webhook_payload(
        db,
        connection,
        {
            "message": {
                "message_id": 1,
                "from": {"id": 8},
                "chat": {"id": -100123, "type": "group"},
                "text": "hola grupo",
            }
        },
    )

    assert result["inbound_conversation_ids"] == []
    assert db.query(Customer).count() == 0
    assert db.query(Conversation).count() == 0


def test_manual_send_uses_telegram_chat_id(monkeypatch):
    db = _session()
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("TELEGRAM_TOKEN_ENCRYPTION_KEY", key)
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

    from app.telegram_security import encrypt_telegram_secret

    db.add(
        TelegramConnection(
            organization_id=1,
            store_id=1,
            bot_id=123,
            bot_token_encrypted=encrypt_telegram_secret("123:secret"),
            webhook_secret_encrypted=encrypt_telegram_secret("hook-secret"),
            webhook_path_token="path",
            status="connected",
        )
    )
    db.commit()

    captured = {}

    def fake_send(token, *, chat_id, text):
        captured.update(token=token, chat_id=chat_id, text=text)
        return {"message_id": 91}

    monkeypatch.setattr(telegram_service, "telegram_send_message", fake_send)

    result = telegram_service.send_message(db, 1, conversation.id, "Respuesta")

    assert result["ok"] is True
    assert captured == {
        "token": "123:secret",
        "chat_id": 9988,
        "text": "Respuesta",
    }
    message = db.query(Message).filter(Message.provider == "telegram").one()
    assert message.sender == "human"
    assert message.external_message_id == "91"
