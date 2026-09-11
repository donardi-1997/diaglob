"""Tests for Nuvemshop integration — service, router, and webhook."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import (
    CommerceConnection,
    NuvemshopOAuthState,
    Order,
    Organization,
    OrganizationMembership,
    Store,
    User,
)

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_nuvemshop.db"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine,
)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def cleanup_db():
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def org(db):
    o = Organization(
        name="Test Org",
        slug="test-org",
        plan="starter",
        subscription_status="active",
    )
    db.add(o)
    db.flush()
    return o


@pytest.fixture()
def user(db, org):
    u = User(
        email="test@test.com",
        external_auth_id="cognito-sub-123",
        name="Test User",
    )
    db.add(u)
    db.flush()
    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=u.id,
        role="owner",
        active=True,
    )
    db.add(membership)
    db.flush()
    return u


@pytest.fixture()
def store(db, org):
    s = Store(
        organization_id=org.id,
        name="Test Store",
        slug="test-store",
        country_code="BR",
        currency="BRL",
        timezone="America/Sao_Paulo",
        default_language="pt-BR",
        active=True,
    )
    db.add(s)
    db.flush()
    return s


@pytest.fixture()
def membership(db, org, user):
    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.user_id == user.id,
            OrganizationMembership.organization_id == org.id,
        )
        .first()
    )


@pytest.fixture()
def client(db, membership, user):
    def override_get_db():
        yield db

    def override_get_current_user():
        return user

    def override_get_current_membership():
        return membership

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_current_membership] = override_get_current_membership

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ============================================================
# OAUTH STATE TESTS
# ============================================================


class TestNuvemshopOAuthState:
    def test_persist_and_consume_state(self, db, org, store, user):
        now = datetime.utcnow()
        state = NuvemshopOAuthState(
            state="test-state-token",
            organization_id=org.id,
            store_id=store.id,
            user_id=user.id,
            expires_at=now + timedelta(minutes=10),
            used=False,
            created_at=now,
        )
        db.add(state)
        db.commit()

        found = (
            db.query(NuvemshopOAuthState)
            .filter(NuvemshopOAuthState.state == "test-state-token")
            .first()
        )
        assert found is not None
        assert found.used is False
        assert found.organization_id == org.id

        found.used = True
        db.commit()

        found2 = (
            db.query(NuvemshopOAuthState)
            .filter(NuvemshopOAuthState.state == "test-state-token")
            .first()
        )
        assert found2.used is True

    def test_expired_state_rejected(self, db, org, store, user):
        now = datetime.utcnow()
        state = NuvemshopOAuthState(
            state="expired-state",
            organization_id=org.id,
            store_id=store.id,
            user_id=user.id,
            expires_at=now - timedelta(minutes=1),
            used=False,
            created_at=now,
        )
        db.add(state)
        db.commit()

        from app.services.nuvemshop_service import NuvemshopOAuthError

        with pytest.raises(NuvemshopOAuthError, match="expired"):
            from app.services.nuvemshop_service import process_oauth_callback
            process_oauth_callback(db, "code123", "expired-state", org.id, store.id)


# ============================================================
# SERVICE TESTS
# ============================================================


class TestNuvemshopService:
    def test_get_oauth_url_persists_state(self, db, org, store, user):
        from app.services.nuvemshop_service import get_oauth_url

        with patch("app.services.nuvemshop_service.NUVEMSHOP_CLIENT_ID", "test-client-id"), \
             patch("app.services.nuvemshop_service.NUVEMSHOP_REDIRECT_URI", "https://example.com/callback"):
            result = get_oauth_url(db, org.id, store.id, user.id)

        assert "authorization_url" in result
        assert "state" in result
        assert "test-client-id" in result["authorization_url"]

        saved = (
            db.query(NuvemshopOAuthState)
            .filter(NuvemshopOAuthState.state == result["state"])
            .first()
        )
        assert saved is not None
        assert saved.organization_id == org.id
        assert saved.store_id == store.id
        assert saved.used is False

    def test_connect_account_creates_connection(self, db, org, store):
        from app.services.nuvemshop_service import connect_account

        result = connect_account(
            db, org.id, store.id,
            "encrypted-token-abc",
            "12345",
            "Mi Tienda",
            "BRL",
            "America/Sao_Paulo",
            "BR",
        )

        assert result["ok"] is True
        assert result["connected"] is True

        conn = (
            db.query(CommerceConnection)
            .filter(
                CommerceConnection.store_id == store.id,
                CommerceConnection.provider == "nuvemshop",
            )
            .first()
        )
        assert conn is not None
        assert conn.status == "connected"
        assert conn.external_store_url == "12345"

    def test_disconnect_removes_connection(self, db, org, store):
        from app.services.nuvemshop_service import connect_account, disconnect

        connect_account(
            db, org.id, store.id,
            "encrypted-token", "12345", "Tienda", "BRL", "America/Sao_Paulo", "BR",
        )

        result = disconnect(db, org.id, store.id)
        assert result["ok"] is True
        assert result["connected"] is False

        conn = (
            db.query(CommerceConnection)
            .filter(
                CommerceConnection.store_id == store.id,
                CommerceConnection.provider == "nuvemshop",
            )
            .first()
        )
        assert conn is None

    def test_get_connection_status_disconnected(self, db, org, store):
        from app.services.nuvemshop_service import get_connection_status

        result = get_connection_status(db, org.id, store.id)
        assert result["connected"] is False
        assert result["status"] == "disconnected"


# ============================================================
# WEBHOOK TESTS
# ============================================================


class TestNuvemshopWebhook:
    def _make_signature(self, body: bytes, secret: str) -> str:
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    @patch("app.api.nuvemshop._verify_nuvemshop_signature", return_value=False)
    def test_invalid_signature_rejected(self, mock_verify, client):
        response = client.post(
            "/api/webhooks/nuvemshop",
            json={"event": "order/created", "store_id": 123, "id": 456},
        )
        assert response.status_code == 401

    @patch("app.api.nuvemshop._verify_nuvemshop_signature", return_value=True)
    def test_unknown_store_acknowledged(self, mock_verify, client):
        response = client.post(
            "/api/webhooks/nuvemshop",
            json={"event": "order/created", "store_id": 999999, "id": 456},
        )
        assert response.status_code == 200
        assert response.json()["ok"] is True

    @patch("app.api.nuvemshop._verify_nuvemshop_signature", return_value=True)
    @patch("app.api.nuvemshop.process_webhook_event")
    def test_valid_webhook_dispatched(self, mock_process, mock_verify, client, db, org, store):
        conn = CommerceConnection(
            organization_id=org.id,
            store_id=store.id,
            provider="nuvemshop",
            external_store_url="12345",
            access_token_encrypted="encrypted",
            status="connected",
            connected_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(conn)
        db.commit()

        mock_process.return_value = {"ok": True, "action": "created"}

        response = client.post(
            "/api/webhooks/nuvemshop",
            json={"event": "order/created", "store_id": 12345, "id": 789},
        )
        assert response.status_code == 200
        mock_process.assert_called_once()

    @patch("app.api.nuvemshop._verify_nuvemshop_signature", return_value=True)
    def test_uninstall_marks_disconnected(self, mock_verify, client, db, org, store):
        conn = CommerceConnection(
            organization_id=org.id,
            store_id=store.id,
            provider="nuvemshop",
            external_store_url="12345",
            access_token_encrypted="encrypted",
            status="connected",
            connected_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(conn)
        db.commit()

        response = client.post(
            "/api/webhooks/nuvemshop/uninstall",
            json={"store_id": 12345},
        )
        assert response.status_code == 200

        db.refresh(conn)
        assert conn.status == "disconnected"


# ============================================================
# ROUTER TESTS
# ============================================================


class TestNuvemshopRouter:
    def test_connect_starts_oauth(self, client, store):
        with patch("app.services.nuvemshop_service.NUVEMSHOP_CLIENT_ID", "test-id"), \
             patch("app.services.nuvemshop_service.NUVEMSHOP_REDIRECT_URI", "https://example.com/cb"):
            response = client.post(
                f"/api/stores/{store.id}/nuvemshop/connect",
            )
        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "state" in data

    def test_status_returns_disconnected(self, client, store):
        response = client.get(
            f"/api/stores/{store.id}/nuvemshop/status",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    def test_disconnect_when_not_connected(self, client, store):
        response = client.delete(
            f"/api/stores/{store.id}/nuvemshop/disconnect",
        )
        assert response.status_code == 404

    def test_nuvemshop_routes_exist(self, client):
        response = client.get("/docs")
        assert response.status_code == 200
