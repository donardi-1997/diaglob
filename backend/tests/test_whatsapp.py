import hashlib
import hmac
import json
import os
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db, SessionLocal as RealSessionLocal
from app.main import app
from app.models import (
    Agent,
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


@pytest.fixture(autouse=True)
def _setup_overrides():
    original = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = (
        override_get_db
    )
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original)

import app.ai_reply_service as _ai_svc

_ai_svc_orig_session = _ai_svc.SessionLocal
_ai_svc.SessionLocal = TestingSessionLocal


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
        subscription_status="active",
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
        role="owner",
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
            subscription_status="active",
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
            subscription_status="active",
            active=True,
        )
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        other_membership = OrganizationMembership(
            user_id=99,
            organization_id=other_org.id,
            role="owner",
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


class TestWebhookVerify:
    def test_verify_correct_token(
        self,
        wa_connection,
    ):
        client = TestClient(app)

        response = client.get(
            "/api/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token":
                    wa_connection.verify_token,
                "hub.challenge":
                    "CHALLENGE_VALUE",
            },
        )

        assert response.status_code == 200
        assert (
            response.text == "CHALLENGE_VALUE"
        )

    def test_verify_incorrect_token(
        self,
        wa_connection,
    ):
        client = TestClient(app)

        response = client.get(
            "/api/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token":
                    "wrong_token_12345",
                "hub.challenge":
                    "CHALLENGE_VALUE",
            },
        )

        assert response.status_code == 403

    def test_verify_missing_mode(
        self,
        wa_connection,
    ):
        client = TestClient(app)

        response = client.get(
            "/api/webhooks/whatsapp",
            params={
                "hub.verify_token":
                    wa_connection.verify_token,
                "hub.challenge":
                    "CHALLENGE_VALUE",
            },
        )

        assert response.status_code == 400

    def test_verify_missing_challenge(
        self,
        wa_connection,
    ):
        client = TestClient(app)

        response = client.get(
            "/api/webhooks/whatsapp",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token":
                    wa_connection.verify_token,
            },
        )

        assert response.status_code == 400


class TestWebhookUnknownPhone:
    def test_unknown_phone_number_ignored(
        self,
        wa_connection,
        db,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        body = json.dumps(
            _webhook_payload(
                "000000000",
                "5210000000003",
                "msg_unknown_001",
                "Hello unknown",
            )
        ).encode()

        client = TestClient(app)

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

        msg = (
            db.query(Message)
            .filter(
                Message.external_message_id
                == "msg_unknown_001"
            )
            .first()
        )

        assert msg is None


class TestConnectionPerStore:
    def test_get_returns_verify_token(
        self,
        wa_connection,
        membership,
    ):
        from app.main import (
            get_current_membership,
        )

        client = TestClient(app)

        original = dict(
            app.dependency_overrides
        )

        app.dependency_overrides[
            get_current_membership
        ] = lambda: membership

        try:
            response = client.get(
                f"/api/stores/{wa_connection.store_id}/whatsapp",
            )

            assert (
                response.status_code == 200
            )

            data = response.json()

            assert data["connected"] is True
            assert (
                data["phone_number_id"]
                == "123456789"
            )
            assert (
                data["verify_token"]
                == wa_connection.verify_token
            )
            assert (
                "access_token"
                not in json.dumps(data)
            )
        finally:
            app.dependency_overrides[
                get_current_membership
            ] = original.get(
                get_current_membership,
            )

    def test_token_never_in_get_response(
        self,
        wa_connection,
        membership,
    ):
        from app.main import (
            get_current_membership,
        )

        client = TestClient(app)

        original = dict(
            app.dependency_overrides
        )

        app.dependency_overrides[
            get_current_membership
        ] = lambda: membership

        try:
            response = client.get(
                f"/api/stores/{wa_connection.store_id}/whatsapp",
            )

            data = response.json()
            raw = json.dumps(data)

            assert (
                "access_token" not in raw
            )
            assert (
                "encrypted" not in raw
            )
        finally:
            app.dependency_overrides[
                get_current_membership
            ] = original.get(
                get_current_membership,
            )


class TestVerifyTokenAuthorization:
    def test_read_only_role_no_verify_token(
        self,
        wa_connection,
        org,
        store,
        db,
    ):
        from app.main import (
            get_current_membership,
        )

        operator = OrganizationMembership(
            user_id=2,
            organization_id=org.id,
            role="operator",
            all_stores=True,
            active=True,
        )
        db.add(operator)
        db.commit()
        db.refresh(operator)

        client = TestClient(app)

        original = dict(
            app.dependency_overrides
        )

        app.dependency_overrides[
            get_current_membership
        ] = lambda: operator

        try:
            response = client.get(
                f"/api/stores/{wa_connection.store_id}/whatsapp",
            )

            assert (
                response.status_code == 200
            )

            data = response.json()

            assert data["connected"] is True
            assert (
                data["phone_number_id"]
                == "123456789"
            )
            assert (
                data["verify_token"] is None
            )
            assert (
                "access_token"
                not in json.dumps(data)
            )
        finally:
            app.dependency_overrides[
                get_current_membership
            ] = original.get(
                get_current_membership,
            )

    def test_analyst_role_no_verify_token(
        self,
        wa_connection,
        org,
        store,
        db,
    ):
        from app.main import (
            get_current_membership,
        )

        analyst = OrganizationMembership(
            user_id=3,
            organization_id=org.id,
            role="analyst",
            all_stores=True,
            active=True,
        )
        db.add(analyst)
        db.commit()
        db.refresh(analyst)

        client = TestClient(app)

        original = dict(
            app.dependency_overrides
        )

        app.dependency_overrides[
            get_current_membership
        ] = lambda: analyst

        try:
            response = client.get(
                f"/api/stores/{wa_connection.store_id}/whatsapp",
            )

            assert (
                response.status_code == 200
            )

            data = response.json()

            assert (
                data["verify_token"] is None
            )
        finally:
            app.dependency_overrides[
                get_current_membership
            ] = original.get(
                get_current_membership,
            )

    def test_manager_role_sees_verify_token(
        self,
        wa_connection,
        org,
        store,
        db,
    ):
        from app.main import (
            get_current_membership,
        )

        manager = OrganizationMembership(
            user_id=4,
            organization_id=org.id,
            role="manager",
            all_stores=True,
            active=True,
        )
        db.add(manager)
        db.commit()
        db.refresh(manager)

        client = TestClient(app)

        original = dict(
            app.dependency_overrides
        )

        app.dependency_overrides[
            get_current_membership
        ] = lambda: manager

        try:
            response = client.get(
                f"/api/stores/{wa_connection.store_id}/whatsapp",
            )

            assert (
                response.status_code == 200
            )

            data = response.json()

            assert (
                data["verify_token"]
                == wa_connection.verify_token
            )
        finally:
            app.dependency_overrides[
                get_current_membership
            ] = original.get(
                get_current_membership,
            )


class TestCrossTenantIsolation:
    def test_webhook_cross_tenant_ignored(
        self,
        db,
        org,
        store,
    ):
        other_org = Organization(
            name="Tenant B",
            slug="tenant-b",
            plan="pro",
            subscription_status="active",
            active=True,
        )
        db.add(other_org)
        db.commit()
        db.refresh(other_org)

        other_store = Store(
            organization_id=other_org.id,
            name="Store B",
            slug="store-b",
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
            phone_number_id="555555555",
            business_account_id="biz_555",
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
                "555555555",
                "5219999999999",
                "msg_tenant_001",
                "Cross tenant msg",
            )
        ).encode()

        client = TestClient(app)

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

        customer = (
            db.query(Customer)
            .filter(
                Customer.organization_id
                == org.id,
                Customer.phone
                == "5219999999999",
            )
            .first()
        )

        assert customer is None

        other_customer = (
            db.query(Customer)
            .filter(
                Customer.organization_id
                == other_org.id,
                Customer.phone
                == "5219999999999",
            )
            .first()
        )

        assert other_customer is not None


class TestDisconnection:
    def test_disconnect_removes_connection(
        self,
        wa_connection,
        membership,
        db,
    ):
        from app.main import (
            get_current_membership,
        )

        client = TestClient(app)

        original = dict(
            app.dependency_overrides
        )

        app.dependency_overrides[
            get_current_membership
        ] = lambda: membership

        try:
            response = client.delete(
                f"/api/stores/{wa_connection.store_id}/whatsapp/disconnect",
            )

            assert (
                response.status_code == 200
            )
            assert (
                response.json()["connected"]
                is False
            )

            remaining = (
                db.query(WhatsAppConnection)
                .filter(
                    WhatsAppConnection.id
                    == wa_connection.id
                )
                .first()
            )

            assert remaining is None
        finally:
            app.dependency_overrides[
                get_current_membership
            ] = original.get(
                get_current_membership,
            )


class TestDuplicateMessages:
    def test_same_wa_id_different_text_both_saved(
        self,
        wa_connection,
        db,
    ):
        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        client = TestClient(app)

        body1 = json.dumps(
            _webhook_payload(
                "123456789",
                "5210000000001",
                "msg_dup_a",
                "First message",
            )
        ).encode()

        response1 = client.post(
            "/api/webhooks/whatsapp",
            content=body1,
            headers={
                "Content-Type":
                    "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body1),
            },
        )
        assert response1.status_code == 200

        body2 = json.dumps(
            _webhook_payload(
                "123456789",
                "5210000000001",
                "msg_dup_b",
                "Second message",
            )
        ).encode()

        response2 = client.post(
            "/api/webhooks/whatsapp",
            content=body2,
            headers={
                "Content-Type":
                    "application/json",
                "X-Hub-Signature-256":
                    _make_signature(body2),
            },
        )
        assert response2.status_code == 200

        messages = (
            db.query(Message)
            .filter(
                Message.provider
                == "whatsapp",
                Message.sender
                == "customer",
            )
            .all()
        )

        assert len(messages) == 2

        texts = {
            m.text for m in messages
        }

        assert texts == {
            "First message",
            "Second message",
        }


@pytest.fixture()
def agent(db, org, store):
    from app.models import agent_stores

    agent = Agent(
        organization_id=org.id,
        name="Test Agent",
        role="ventas",
        active=True,
    )
    db.add(agent)
    db.flush()

    stmt = agent_stores.insert().values(
        agent_id=agent.id,
        store_id=store.id,
    )
    db.execute(stmt)
    db.commit()
    db.refresh(agent)
    return agent


class TestAutoReply:
    def test_inbound_triggers_ai_reply(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        from app.main import (
            get_current_membership,
        )

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        mock_answer = "Gracias por tu pregunta. Tenemos disponibilidad."

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
            return_value=mock_answer,
        ), patch(
            "app.ai_reply_service.retrieve_agent_knowledge",
            return_value=[],
        ), patch(
            "app.ai_reply_service.search_products",
            return_value=[],
        ), patch(
            "app.ai_reply_service.send_whatsapp_text_message",
            return_value={
                "message_id": "wamid.test123",
                "response": {},
            },
        ), patch(
            "app.ai_reply_service.decrypt_whatsapp_secret",
            return_value="fake_token",
        ):
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_auto_001",
                    "Hola, ¿tienen productos?",
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

            assert (
                response.status_code == 200
            )

        conv = (
            db.query(Conversation)
            .filter(
                Conversation.store_id
                == wa_connection.store_id,
            )
            .first()
        )

        assert conv is not None
        assert conv.agent_id == agent.id

        ai_msgs = (
            db.query(Message)
            .filter(
                Message.conversation_id
                == conv.id,
                Message.sender == "ai",
            )
            .all()
        )

        assert len(ai_msgs) == 1
        assert (
            ai_msgs[0].text == mock_answer
        )
        assert (
            ai_msgs[0].provider == "whatsapp"
        )
        assert (
            ai_msgs[0].delivery_status == "sent"
        )
        assert (
            ai_msgs[0].external_message_id
            == "wamid.test123"
        )

    def test_duplicate_inbound_no_second_reply(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        call_count = 0

        def counting_generate(**kwargs):
            nonlocal call_count
            call_count += 1
            return "Reply"

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
            side_effect=counting_generate,
        ), patch(
            "app.ai_reply_service.retrieve_agent_knowledge",
            return_value=[],
        ), patch(
            "app.ai_reply_service.search_products",
            return_value=[],
        ), patch(
            "app.ai_reply_service.send_whatsapp_text_message",
            return_value={
                "message_id": "wamid.dup1",
                "response": {},
            },
        ), patch(
            "app.ai_reply_service.decrypt_whatsapp_secret",
            return_value="fake_token",
        ):
            client = TestClient(app)

            payload = _webhook_payload(
                "123456789",
                "5210000000001",
                "msg_dup_test",
                "Duplicate test",
            )

            body = json.dumps(payload).encode()

            response1 = client.post(
                "/api/webhooks/whatsapp",
                content=body,
                headers={
                    "Content-Type":
                        "application/json",
                    "X-Hub-Signature-256":
                        _make_signature(body),
                },
            )
            assert (
                response1.status_code == 200
            )

            response2 = client.post(
                "/api/webhooks/whatsapp",
                content=body,
                headers={
                    "Content-Type":
                        "application/json",
                    "X-Hub-Signature-256":
                        _make_signature(body),
                },
            )
            assert (
                response2.status_code == 200
            )

        conv = (
            db.query(Conversation)
            .filter(
                Conversation.store_id
                == wa_connection.store_id,
            )
            .first()
        )

        ai_msgs = (
            db.query(Message)
            .filter(
                Message.conversation_id
                == conv.id,
                Message.sender == "ai",
            )
            .all()
        )

        assert len(ai_msgs) == 1

    def test_status_event_no_reply(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
        ) as mock_gen:
            client = TestClient(app)

            body = json.dumps(
                _status_payload(
                    "wamid.status_test",
                    "delivered",
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

            assert (
                response.status_code == 200
            )
            mock_gen.assert_not_called()

    def test_ai_response_saved_with_correct_provider(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
            return_value="AI answer here",
        ), patch(
            "app.ai_reply_service.retrieve_agent_knowledge",
            return_value=[],
        ), patch(
            "app.ai_reply_service.search_products",
            return_value=[],
        ), patch(
            "app.ai_reply_service.send_whatsapp_text_message",
            return_value={
                "message_id": "wamid.provider_test",
                "response": {},
            },
        ), patch(
            "app.ai_reply_service.decrypt_whatsapp_secret",
            return_value="fake_token",
        ):
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_provider_001",
                    "What products do you have?",
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

            assert (
                response.status_code == 200
            )

        conv = (
            db.query(Conversation)
            .filter(
                Conversation.store_id
                == wa_connection.store_id,
            )
            .first()
        )

        ai_msg = (
            db.query(Message)
            .filter(
                Message.conversation_id
                == conv.id,
                Message.sender == "ai",
            )
            .first()
        )

        assert ai_msg is not None
        assert (
            ai_msg.sender == "ai"
        )
        assert (
            ai_msg.provider == "whatsapp"
        )
        assert (
            ai_msg.delivery_status == "sent"
        )
        assert (
            ai_msg.external_message_id
            == "wamid.provider_test"
        )

    def test_send_failure_controlled(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
            return_value="AI answer",
        ), patch(
            "app.ai_reply_service.retrieve_agent_knowledge",
            return_value=[],
        ), patch(
            "app.ai_reply_service.search_products",
            return_value=[],
        ), patch(
            "app.ai_reply_service.send_whatsapp_text_message",
            side_effect=RuntimeError(
                "Graph API down"
            ),
        ), patch(
            "app.ai_reply_service.decrypt_whatsapp_secret",
            return_value="fake_token",
        ):
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_fail_001",
                    "Test failure",
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

            assert (
                response.status_code == 200
            )

        conv = (
            db.query(Conversation)
            .filter(
                Conversation.store_id
                == wa_connection.store_id,
            )
            .first()
        )

        ai_msg = (
            db.query(Message)
            .filter(
                Message.conversation_id
                == conv.id,
                Message.sender == "ai",
            )
            .first()
        )

        assert ai_msg is not None
        assert (
            ai_msg.provider == "whatsapp"
        )
        assert (
            ai_msg.delivery_status == "failed"
        )
        assert (
            ai_msg.external_message_id is None
        )

    def test_ai_failure_no_webhook_break(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
            side_effect=Exception(
                "Bedrock timeout"
            ),
        ), patch(
            "app.ai_reply_service.retrieve_agent_knowledge",
            return_value=[],
        ), patch(
            "app.ai_reply_service.search_products",
            return_value=[],
        ):
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_err_001",
                    "AI error test",
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

            assert (
                response.status_code == 200
            )

        conv = (
            db.query(Conversation)
            .filter(
                Conversation.store_id
                == wa_connection.store_id,
            )
            .first()
        )

        inbound = (
            db.query(Message)
            .filter(
                Message.conversation_id
                == conv.id,
                Message.sender == "customer",
            )
            .first()
        )

        assert inbound is not None
        assert (
            inbound.text == "AI error test"
        )

    def test_handoff_keyword_skips_reply(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
        ) as mock_gen:
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_handoff_001",
                    "Quiero hablar con un asesor",
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

            assert (
                response.status_code == 200
            )
            mock_gen.assert_not_called()

        conv = (
            db.query(Conversation)
            .filter(
                Conversation.store_id
                == wa_connection.store_id,
            )
            .first()
        )

        assert conv.mode == "human"

        ai_msgs = (
            db.query(Message)
            .filter(
                Message.conversation_id
                == conv.id,
                Message.sender == "ai",
            )
            .all()
        )

        assert len(ai_msgs) == 0

    def test_english_handoff_skips_reply(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
        ) as mock_gen:
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_en_handoff",
                    "I want to speak to a human",
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

            assert (
                response.status_code == 200
            )
            mock_gen.assert_not_called()

        conv = (
            db.query(Conversation)
            .filter(
                Conversation.store_id
                == wa_connection.store_id,
            )
            .first()
        )

        assert conv.mode == "human"

    def test_mode_human_no_reply(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        conv = (
            db.query(Conversation)
            .filter(
                Conversation.store_id
                == wa_connection.store_id,
            )
            .first()
        )

        if not conv:
            from app.models import Customer

            customer = Customer(
                organization_id=
                    wa_connection.organization_id,
                name="Human Mode Customer",
                phone="5210000000002",
            )
            db.add(customer)
            db.flush()

            conv = Conversation(
                organization_id=
                    wa_connection.organization_id,
                store_id=
                    wa_connection.store_id,
                customer_id=customer.id,
                channel="WhatsApp",
                mode="human",
                agent_id=agent.id,
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)

        conv.mode = "human"
        db.commit()

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
        ) as mock_gen:
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000002",
                    "msg_human_mode",
                    "Hello again",
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

            assert (
                response.status_code == 200
            )
            mock_gen.assert_not_called()

    def test_no_agent_no_reply(
        self,
        wa_connection,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
        ) as mock_gen:
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_no_agent",
                    "No agent test",
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

            assert (
                response.status_code == 200
            )
            mock_gen.assert_not_called()

        conv = (
            db.query(Conversation)
            .filter(
                Conversation.store_id
                == wa_connection.store_id,
            )
            .first()
        )

        inbound = (
            db.query(Message)
            .filter(
                Message.conversation_id
                == conv.id,
                Message.sender == "customer",
            )
            .first()
        )

        assert inbound is not None
        assert (
            inbound.text == "No agent test"
        )

    def test_history_limited_to_conversation(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        captured_history = {}

        def capture_generate(**kwargs):
            captured_history["history"] = (
                kwargs.get(
                    "conversation_history"
                )
            )
            return "Reply with history"

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
            side_effect=capture_generate,
        ), patch(
            "app.ai_reply_service.retrieve_agent_knowledge",
            return_value=[],
        ), patch(
            "app.ai_reply_service.search_products",
            return_value=[],
        ), patch(
            "app.ai_reply_service.send_whatsapp_text_message",
            return_value={
                "message_id": "wamid.hist1",
                "response": {},
            },
        ), patch(
            "app.ai_reply_service.decrypt_whatsapp_secret",
            return_value="fake_token",
        ):
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_hist_first",
                    "First question",
                )
            ).encode()

            client.post(
                "/api/webhooks/whatsapp",
                content=body,
                headers={
                    "Content-Type":
                        "application/json",
                    "X-Hub-Signature-256":
                        _make_signature(body),
                },
            )

            body2 = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_hist_second",
                    "Follow up question",
                )
            ).encode()

            client.post(
                "/api/webhooks/whatsapp",
                content=body2,
                headers={
                    "Content-Type":
                        "application/json",
                    "X-Hub-Signature-256":
                        _make_signature(body2),
                },
            )

        assert "history" in captured_history

        history = captured_history["history"]
        assert "First question" in history
        assert (
            "Follow up question" in history
        )

    def test_webhook_responds_200_with_background(
        self,
        wa_connection,
        agent,
        db,
    ):
        from unittest.mock import patch

        os.environ[
            "WHATSAPP_APP_SECRET"
        ] = TEST_APP_SECRET

        with patch(
            "app.ai_reply_service.generate_grounded_answer",
            return_value="Background reply",
        ), patch(
            "app.ai_reply_service.retrieve_agent_knowledge",
            return_value=[],
        ), patch(
            "app.ai_reply_service.search_products",
            return_value=[],
        ), patch(
            "app.ai_reply_service.send_whatsapp_text_message",
            return_value={
                "message_id": "wamid.bg1",
                "response": {},
            },
        ), patch(
            "app.ai_reply_service.decrypt_whatsapp_secret",
            return_value="fake_token",
        ):
            client = TestClient(app)

            body = json.dumps(
                _webhook_payload(
                    "123456789",
                    "5210000000001",
                    "msg_bg_001",
                    "Background test",
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

            assert (
                response.status_code == 200
            )
            assert (
                response.json() == {"ok": True}
            )
