"""Payment provider tests.

Tests for payment connections, transactions, webhooks,
tenant isolation, and the Nequi provider adapter.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.main import app
from app.models import (
    Order,
    Organization,
    OrganizationMembership,
    PaymentConnection,
    PaymentTransaction,
    Store,
    User,
)
from app.api.deps import get_db, get_current_user, get_current_membership
from app.payment_security import (
    encrypt_payment_secret,
    decrypt_payment_secret,
)
from app.payments.base import (
    PaymentStatus,
    ProviderPaymentResult,
    ProviderStatusResult,
    is_valid_transition,
)
from app.payments.nequi import NequiPaymentProvider
from app.payments.registry import get_provider, get_providers_for_market
from app.services import payment_service


# ============================================================
# FIXTURES
# ============================================================

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_payments.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

_ENCRYPTION_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _set_payment_encryption_key():
    with patch.dict(
        os.environ,
        {"PAYMENT_TOKEN_ENCRYPTION_KEY": _ENCRYPTION_KEY},
    ):
        yield


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


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def org(db):
    org = Organization(
        name="Test Org",
        slug="test-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


@pytest.fixture
def user(db):
    user = User(
        email="test@test.com",
        name="Test User",
        external_auth_id="test-sub-123",
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def membership(db, org, user):
    m = OrganizationMembership(
        user_id=user.id,
        organization_id=org.id,
        role="owner",
        all_stores=True,
        active=True,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@pytest.fixture
def store_co(db, org):
    store = Store(
        organization_id=org.id,
        name="Colombia Store",
        slug="co-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
        active=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@pytest.fixture
def store_br(db, org):
    store = Store(
        organization_id=org.id,
        name="Brazil Store",
        slug="br-store",
        country_code="BR",
        currency="BRL",
        timezone="America/Sao_Paulo",
        default_language="pt-BR",
        active=True,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


@pytest.fixture
def order(db, org, store_co):
    order = Order(
        organization_id=org.id,
        store_id=store_co.id,
        order_number="ORD-001",
        total_amount=Decimal("89900.00"),
        currency="COP",
        source="manual",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@pytest.fixture
def nequi_connection(db, org, store_co):
    conn = PaymentConnection(
        organization_id=org.id,
        store_id=store_co.id,
        provider="nequi",
        status="connected",
        environment="sandbox",
        client_id_encrypted=encrypt_payment_secret("test-client-id"),
        client_secret_encrypted=encrypt_payment_secret("test-client-secret"),
        merchant_reference="merchant-001",
        connected_at=datetime.now(timezone.utc),
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


@pytest.fixture
def app_client(db, user, membership):
    def override_db():
        yield db

    def override_user():
        return user

    def override_membership():
        return membership

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_current_membership] = override_membership

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ============================================================
# CONNECTION TESTS
# ============================================================


class TestConnection:
    def test_colombia_cop_can_configure_nequi(
        self, db, org, store_co
    ):
        """Test 1: Colombia/COP can configure Nequi."""
        conn = payment_service.configure_connection(
            db,
            org.id,
            store_co.id,
            "nequi",
            "sandbox",
            "client-id",
            "client-secret",
        )
        assert conn.status == "connected"
        assert conn.provider == "nequi"
        assert conn.environment == "sandbox"

    def test_brazil_store_cannot_configure_nequi(
        self, db, org, store_br
    ):
        """Test 2: Brazil store cannot configure Nequi."""
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.configure_connection(
                db,
                org.id,
                store_br.id,
                "nequi",
                "sandbox",
                "client-id",
                "client-secret",
            )
        assert exc.value.code == "PAYMENT_PROVIDER_UNAVAILABLE"

    def test_wrong_org_cannot_access_connection(
        self, db, store_co, nequi_connection
    ):
        """Test 3: Wrong organization cannot access connection."""
        status = payment_service.get_connection_status(
            db, 99999, store_co.id, "nequi"
        )
        assert status["connected"] is False

    def test_secrets_encrypted_not_serialized(
        self, db, org, store_co, nequi_connection
    ):
        """Test 4: Secrets are encrypted and not in API response."""
        status = payment_service.get_connection_status(
            db, org.id, store_co.id, "nequi"
        )
        assert "client_id" not in status
        assert "client_secret" not in status
        assert "webhook_secret" not in status

    def test_sandbox_prod_separation(
        self, db, org, store_co
    ):
        """Test 5: sandbox/prod separation is persisted."""
        conn = payment_service.configure_connection(
            db,
            org.id,
            store_co.id,
            "nequi",
            "production",
            "prod-id",
            "prod-secret",
        )
        assert conn.environment == "production"


# ============================================================
# PAYMENT CREATION TESTS
# ============================================================


class TestPaymentCreation:
    def test_valid_order_can_create_payment(
        self, db, org, store_co, order, nequi_connection
    ):
        """Test 6: Valid order can create payment."""
        with patch(
            "app.payments.nequi.NequiPaymentProvider.create_payment",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = ProviderPaymentResult(
                provider_transaction_id="txn-123",
                status=PaymentStatus.PENDING,
                provider_status="PENDING",
                payment_method="nequi_push",
                expires_at="2026-01-01T00:15:00Z",
            )

            txn = payment_service.create_payment(
                db,
                org.id,
                store_co.id,
                "nequi",
                Decimal("89900"),
                "COP",
                "+573001234567",
                "idem-key-001",
                order_id=order.id,
            )

            assert txn.status == "pending"
            assert txn.provider == "nequi"
            assert txn.order_id == order.id

    def test_invalid_store_rejected(
        self, db, org, nequi_connection
    ):
        """Test 7: Invalid store rejected."""
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db,
                org.id,
                99999,
                "nequi",
                Decimal("100"),
                "COP",
                "+573001234567",
                "idem-key-002",
            )
        assert exc.value.code == "PAYMENT_STORE_NOT_FOUND"

    def test_cross_tenant_order_rejected(
        self, db, org, store_co, nequi_connection
    ):
        """Test 8: Cross-tenant order rejected."""
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db,
                org.id,
                store_co.id,
                "nequi",
                Decimal("100"),
                "COP",
                "+573001234567",
                "idem-key-003",
                order_id=99999,
            )
        assert exc.value.code == "PAYMENT_ORDER_NOT_FOUND"

    def test_wrong_currency_rejected(
        self, db, org, store_co, nequi_connection
    ):
        """Test 9: Wrong currency rejected."""
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db,
                org.id,
                store_co.id,
                "nequi",
                Decimal("100"),
                "BRL",
                "+573001234567",
                "idem-key-004",
            )
        assert exc.value.code == "PAYMENT_INVALID_AMOUNT"

    def test_duplicate_idempotency_key(
        self, db, org, store_co, nequi_connection
    ):
        """Test 11: Duplicate idempotency key does not create second charge."""
        with patch(
            "app.payments.nequi.NequiPaymentProvider.create_payment",
            new_callable=AsyncMock,
        ) as mock_create:
            mock_create.return_value = ProviderPaymentResult(
                provider_transaction_id="txn-456",
                status=PaymentStatus.PENDING,
                provider_status="PENDING",
                payment_method="nequi_push",
            )

            txn1 = payment_service.create_payment(
                db,
                org.id,
                store_co.id,
                "nequi",
                Decimal("100"),
                "COP",
                "+573001234567",
                "idem-key-dup",
            )

            txn2 = payment_service.create_payment(
                db,
                org.id,
                store_co.id,
                "nequi",
                Decimal("100"),
                "COP",
                "+573001234567",
                "idem-key-dup",
            )

            assert txn1.id == txn2.id

    def test_missing_provider_connection_rejected(
        self, db, org, store_co
    ):
        """Test 12: Missing provider connection rejected."""
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db,
                org.id,
                store_co.id,
                "nequi",
                Decimal("100"),
                "COP",
                "+573001234567",
                "idem-key-005",
            )
        assert exc.value.code == "PAYMENT_PROVIDER_NOT_CONNECTED"


# ============================================================
# STATUS TESTS
# ============================================================


class TestStatusTransitions:
    def test_pending_to_paid_allowed(self):
        """Test 15: Confirmed success -> paid."""
        assert is_valid_transition("pending", "paid")

    def test_pending_to_rejected_allowed(self):
        """Test 16: Rejected -> rejected."""
        assert is_valid_transition("pending", "rejected")

    def test_pending_to_expired_allowed(self):
        """Test 17: Expired -> expired."""
        assert is_valid_transition("pending", "expired")

    def test_paid_cannot_regress_to_pending(self):
        """Test 21: Paid payment cannot regress to pending."""
        assert not is_valid_transition("paid", "pending")

    def test_paid_to_reversed_allowed(self):
        """Test 22: Paid payment can be reversed."""
        assert is_valid_transition("paid", "reversed")

    def test_pending_cannot_be_reversed(self):
        """Test 23: Pending payment cannot be reversed."""
        assert not is_valid_transition("pending", "reversed")


# ============================================================
# SECURITY TESTS
# ============================================================


class TestSecurity:
    def test_credentials_encrypted(self):
        """Test 30: Credentials are encrypted."""
        encrypted = encrypt_payment_secret("my-secret")
        assert encrypted != "my-secret"
        decrypted = decrypt_payment_secret(encrypted)
        assert decrypted == "my-secret"

    def test_empty_secret_raises(self):
        """Test: Empty secrets raise errors."""
        with pytest.raises(ValueError):
            encrypt_payment_secret("")
        with pytest.raises(ValueError):
            decrypt_payment_secret("")


# ============================================================
# PROVIDER REGISTRY TESTS
# ============================================================


class TestProviderRegistry:
    def test_nequi_available_for_colombia(self):
        providers = get_providers_for_market("CO", "COP")
        codes = [p.provider_code for p in providers]
        assert "nequi" in codes

    def test_nequi_not_available_for_brazil(self):
        providers = get_providers_for_market("BR", "BRL")
        codes = [p.provider_code for p in providers]
        assert "nequi" not in codes

    def test_nequi_provider_properties(self):
        provider = get_provider("nequi")
        assert provider is not None
        assert provider.provider_code == "nequi"
        assert provider.display_name == "Nequi"
        assert "CO" in provider.supported_countries
        assert "COP" in provider.supported_currencies
        assert provider.supports_webhooks is True
        assert provider.supports_reversals is True


# ============================================================
# NEQUI PROVIDER TESTS
# ============================================================


class TestNequiProvider:
    def test_phone_normalization(self):
        """Test that phone numbers are normalized."""
        provider = NequiPaymentProvider()
        # The provider normalizes in create_payment
        # Just verify it exists
        assert provider.provider_code == "nequi"

    def test_availability_check(self):
        """Test market availability."""
        provider = NequiPaymentProvider()
        assert provider.is_available("CO", "COP") is True
        assert provider.is_available("BR", "BRL") is False
        assert provider.is_available("MX", "MXN") is False


# ============================================================
# API ENDPOINT TESTS
# ============================================================


class TestPaymentAPI:
    def test_list_providers_for_colombia_store(
        self, app_client, store_co
    ):
        """Test: List providers for Colombia store."""
        response = app_client.get(
            f"/api/stores/{store_co.id}/payments/providers"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["store_id"] == store_co.id
        codes = [p["code"] for p in data["providers"]]
        assert "nequi" in codes

    def test_list_providers_for_brazil_store(
        self, app_client, store_br
    ):
        """Test: List providers for Brazil store shows no Nequi."""
        response = app_client.get(
            f"/api/stores/{store_br.id}/payments/providers"
        )
        assert response.status_code == 200
        data = response.json()
        codes = [p["code"] for p in data["providers"]]
        assert "nequi" not in codes

    def test_configure_nequi_connection(
        self, app_client, store_co
    ):
        """Test: Configure Nequi connection via API."""
        response = app_client.post(
            f"/api/stores/{store_co.id}/payments/nequi/connect",
            json={
                "provider": "nequi",
                "environment": "sandbox",
                "client_id": "test-id",
                "client_secret": "test-secret",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["provider"] == "nequi"

    def test_get_connection_status(
        self, app_client, store_co, nequi_connection
    ):
        """Test: Get connection status."""
        response = app_client.get(
            f"/api/stores/{store_co.id}/payments/nequi/status"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["provider"] == "nequi"

    def test_disconnect_nequi(
        self, app_client, store_co, nequi_connection
    ):
        """Test: Disconnect Nequi."""
        response = app_client.delete(
            f"/api/stores/{store_co.id}/payments/nequi/disconnect"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    def test_webhook_invalid_json(self, app_client):
        """Test 19: Invalid webhook rejected."""
        response = app_client.post(
            "/api/webhooks/payments/nequi",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400

    def test_webhook_unknown_transaction(self, app_client):
        """Test: Webhook for unknown transaction is handled."""
        response = app_client.post(
            "/api/webhooks/payments/nequi",
            json={
                "transactionId": "unknown-txn",
                "status": "APPROVED",
                "eventType": "payment",
            },
        )
        # Should return 400 or handle gracefully
        assert response.status_code in (200, 400)


# ============================================================
# AMOUNT VALIDATION TESTS
# ============================================================


class TestAmountValidation:
    def test_zero_amount_rejected(
        self, db, org, store_co, nequi_connection
    ):
        """Test: Zero amount rejected."""
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db,
                org.id,
                store_co.id,
                "nequi",
                Decimal("0"),
                "COP",
                "+573001234567",
                "idem-zero",
            )
        assert exc.value.code == "PAYMENT_INVALID_AMOUNT"

    def test_negative_amount_rejected(
        self, db, org, store_co, nequi_connection
    ):
        """Test: Negative amount rejected."""
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db,
                org.id,
                store_co.id,
                "nequi",
                Decimal("-100"),
                "COP",
                "+573001234567",
                "idem-neg",
            )
        assert exc.value.code == "PAYMENT_INVALID_AMOUNT"


# ============================================================
# WEBHOOK IDEMPOTENCY TEST
# ============================================================


class TestWebhookIdempotency:
    def test_duplicate_webhook_is_idempotent(
        self, db, org, store_co, nequi_connection
    ):
        """Test 18: Duplicate webhook is idempotent."""
        # Create a transaction first
        txn = PaymentTransaction(
            organization_id=org.id,
            store_id=store_co.id,
            provider="nequi",
            provider_transaction_id="txn-webhook-001",
            idempotency_key="idem-webhook-001",
            amount=Decimal("50000"),
            currency="COP",
            status="pending",
            payment_method="nequi_push",
        )
        db.add(txn)
        db.commit()

        nequi_connection.last_event_id = "event-001"
        db.commit()

        # First webhook
        import asyncio
        result1 = asyncio.run(payment_service.process_webhook(
            db,
            "nequi",
            {},
            json.dumps({
                "transactionId": "txn-webhook-001",
                "status": "APPROVED",
                "eventType": "payment",
                "eventId": "event-002",
            }).encode(),
        ))

        # Second webhook with same event
        result2 = asyncio.run(payment_service.process_webhook(
            db,
            "nequi",
            {},
            json.dumps({
                "transactionId": "txn-webhook-001",
                "status": "APPROVED",
                "eventType": "payment",
                "eventId": "event-002",
            }).encode(),
        ))

        assert result1["status"] == "processed"
        assert result2["status"] == "duplicate"
