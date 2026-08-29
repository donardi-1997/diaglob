import hashlib
import hmac
import json
import os
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
from app.models import (
    Conversation,
    Customer,
    Message,
    Organization,
    OrganizationMembership,
    Store,
    WhatsAppConnection,
)

SQLALCHEMY_TEST_DATABASE_URL = (
    "sqlite:///./test_whatsapp.db"
)

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
    },
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

TEST_APP_SECRET = "test_app_secret_12345"


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = (
    override_get_db
)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def org(db):
    organization = Organization(
        name="Test Org",
        slug="test-org",
        plan="pro",
        active=True,
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


@pytest.fixture()
def store(db, org):
    store = Store(
        organization_id=org.id,
        name="Test Store",
        slug="test-store",
        country_code="MX",
        currency="MXN",
        timezone="America/Mexico_City",
        default_language="es",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@pytest.fixture()
def membership(db, org):
    membership = OrganizationMembership(
        user_id=1,
        organization_id=org.id,
        role="admin",
        all_stores=True,
        active=True,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


@pytest.fixture()
def wa_connection(db, org, store):
    connection = WhatsAppConnection(
        organization_id=org.id,
        store_id=store.id,
        phone_number_id="123456789",
        business_account_id="biz_123",
        access_token_encrypted="encrypted_token",
        verify_token=secrets.token_urlsafe(48),
        status="connected",
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@pytest.fixture()
def customer(db, org):
    customer = Customer(
        organization_id=org.id,
        name="Test Customer",
        phone="5210000000001",
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@pytest.fixture()
def conversation(db, org, store, customer):
    conv = Conversation(
        organization_id=org.id,
        store_id=store.id,
        customer_id=customer.id,
        channel="WhatsApp",
        preview="",
        unread=0,
        mode="ai",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _make_signature(body: bytes) -> str:
    computed = hmac.new(
        TEST_APP_SECRET.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={computed}"


def _webhook_payload(
    phone_number_id: str,
    wa_id: str,
    msg_id: str,
    text: str,
):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "phone_number_id":
                                    phone_number_id,
                            },
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": msg_id,
                                    "type": "text",
                                    "text": {
                                        "body": text,
                                    },
                                },
                            ],
                            "contacts": [
                                {
                                    "wa_id": wa_id,
                                    "profile": {
                                        "name": "Test User",
                                    },
                                },
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _status_payload(msg_id: str, status: str):
    return {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "phone_number_id":
                                    "123456789",
                            },
                            "statuses": [
                                {
                                    "id": msg_id,
                                    "status": status,
                                },
                            ],
                        },
                    }
                ],
            }
        ],
    }


class TestWebhookSignature:
    def test_invalid_signature_rejected(
        self,
        wa_connection,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        body = json.dumps(
            _webhook_payload(
                "123456789",
                "5210000000001",
                "msg_001",
                "Hello",
            )
        ).encode()

        client = TestClient(app)

        response = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256":
                    "sha256=invalidsignature",
            },
        )

        assert response.status_code == 401

    def test_missing_signature_rejected(
        self,
        wa_connection,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        body = json.dumps(
            _webhook_payload(
                "123456789",
                "5210000000001",
                "msg_001",
                "Hello",
            )
        ).encode()

        client = TestClient(app)

        response = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
            },
        )

        assert response.status_code == 401

    def test_valid_signature_accepted(
        self,
        wa_connection,
        db,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        body = json.dumps(
            _webhook_payload(
                "123456789",
                "5210000000001",
                "msg_002",
                "Hola",
            )
        ).encode()

        client = TestClient(app)

        response = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body),
            },
        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}

        msg = (
            db.query(Message)
            .filter(
                Message.external_message_id
                == "msg_002"
            )
            .first()
        )

        assert msg is not None
        assert msg.text == "Hola"
        assert msg.sender == "customer"
        assert msg.provider == "whatsapp"


class TestIdempotency:
    def test_duplicate_webhook_not_created(
        self,
        wa_connection,
        db,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        body = json.dumps(
            _webhook_payload(
                "123456789",
                "5210000000001",
                "msg_dup_001",
                "Test message",
            )
        ).encode()

        client = TestClient(app)

        response1 = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body),
            },
        )

        assert response1.status_code == 200

        response2 = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body),
            },
        )

        assert response2.status_code == 200

        messages = (
            db.query(Message)
            .filter(
                Message.external_message_id
                == "msg_dup_001"
            )
            .all()
        )

        assert len(messages) == 1

    def test_same_text_different_ids_creates_two(
        self,
        wa_connection,
        db,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        client = TestClient(app)

        for i in range(2):
            msg_id = f"msg_unique_{i}"

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    msg_id,
                    "Same text",
                )
            ).encode()

            response = client.post(
                "/api/webhooks/whatsapp",
                content=body,
                headers={
                    "Content-Type":
                        "application/json",
                    "X-Hub-Signature-256":
                        _make_signature(body),
                },
            )

            assert response.status_code == 200

        messages = (
            db.query(Message)
            .filter(
                Message.text == "Same text",
                Message.sender == "customer",
            )
            .all()
        )

        assert len(messages) == 2

        ids = {
            m.external_message_id
            for m in messages
        }

        assert ids == {
            "msg_unique_0",
            "msg_unique_1",
        }


class TestStoreIsolation:
    def test_webhook_for_wrong_phone_ignored(
        self,
        db,
        org,
        store,
    ):
        other_org = Organization(
            name="Other Org",
            slug="other-org",
            plan="pro",
            active=True,
        )
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        other_store = Store(
            organization_id=other_org.id,
            name="Other Store",
            slug="other-store",
            country_code="MX",
            currency="MXN",
            timezone="America/Mexico_City",
            default_language="es",
            active=True,
            deleted=False,
        )
        db.add(other_store)
        db.commit()
        db.refresh(other_store)

        other_conn = WhatsAppConnection(
            organization_id=other_org.id,
            store_id=other_store.id,
            phone_number_id="999999999",
            business_account_id="biz_999",
            access_token_encrypted="enc",
            verify_token=secrets.token_urlsafe(48),
            status="connected",
        )
        db.add(other_conn)
        db.commit()

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        body = json.dumps(
            _webhook_payload(
                "999999999",
                "5210000000002",
                "msg_iso_001",
                "Hello other store",
            )
        ).encode()

        client = TestClient(app)

        response = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body),
            },
        )

        assert response.status_code == 200

        customer = (
            db.query(Customer)
            .filter(
                Customer.organization_id
                == org.id,
                Customer.phone
                == "5210000000002",
            )
            .first()
        )

        assert customer is None


class TestDeliveryStatuses:
    def test_status_update_delivered(
        self,
        wa_connection,
        conversation,
        db,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        msg = Message(
            conversation_id=conversation.id,
            sender="human",
            text="Sent message",
            provider="whatsapp",
            external_message_id="msg_status_001",
            delivery_status="sent",
        )
        db.add(msg)
        db.commit()

        body = json.dumps(
            _status_payload(
                "msg_status_001",
                "delivered",
            )
        ).encode()

        client = TestClient(app)

        response = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body),
            },
        )

        assert response.status_code == 200

        db.refresh(msg)
        assert msg.delivery_status == "delivered"

    def test_status_update_read(
        self,
        wa_connection,
        conversation,
        db,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        msg = Message(
            conversation_id=conversation.id,
            sender="human",
            text="Sent message",
            provider="whatsapp",
            external_message_id="msg_status_002",
            delivery_status="delivered",
        )
        db.add(msg)
        db.commit()

        body = json.dumps(
            _status_payload(
                "msg_status_002",
                "read",
            )
        ).encode()

        client = TestClient(app)

        response = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body),
            },
        )

        assert response.status_code == 200

        db.refresh(msg)
        assert msg.delivery_status == "read"

    def test_status_update_failed(
        self,
        wa_connection,
        conversation,
        db,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        msg = Message(
            conversation_id=conversation.id,
            sender="human",
            text="Sent message",
            provider="whatsapp",
            external_message_id="msg_status_003",
            delivery_status="sent",
        )
        db.add(msg)
        db.commit()

        body = json.dumps(
            _status_payload(
                "msg_status_003",
                "failed",
            )
        ).encode()

        client = TestClient(app)

        response = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body),
            },
        )

        assert response.status_code == 200

        db.refresh(msg)
        assert msg.delivery_status == "failed"

    def test_status_update_unknown_id_ignored(
        self,
        wa_connection,
        db,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        body = json.dumps(
            _status_payload(
                "msg_nonexistent",
                "delivered",
            )
        ).encode()

        client = TestClient(app)

        response = client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body),
            },
        )

        assert response.status_code == 200


class TestSendEndpoint:
    def test_send_cross_org_fails(
        self,
        db,
        org,
        store,
        membership,
        customer,
        conversation,
    ):
        other_org = Organization(
            name="Other Org",
            slug="other-send-org",
            plan="pro",
            active=True,
        )
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        other_membership = OrganizationMembership(
            user_id=99,
            organization_id=other_org.id,
            role="admin",
            all_stores=True,
            active=True,
        )
        db.add(other_membership)
        db.commit()
        db.refresh(other_membership)

        os.environ.pop(
            "WHATSAPP_APP_SECRET", None
        )

        client = TestClient(app)

        from app.main import (
            get_current_membership,
        )

        original_overrides = dict(
            app.dependency_overrides
        )

        def mock_auth():
            return other_membership

        app.dependency_overrides[
            get_current_membership
        ] = mock_auth

        try:
            response = client.post(
                f"/api/conversations/{conversation.id}/whatsapp/send",
                json={
                    "text": "Hello",
                    "sender": "human",
                },
            )

            assert response.status_code in {
                403,
                404,
            }
        finally:
            app.dependency_overrides[
                get_current_membership
            ] = original_overrides.get(
                get_current_membership,
            )
