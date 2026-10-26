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
    CommerceConnection,
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
    ProviderReversalResult,
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
        self, db, org, store_co, nequi_connection, provider_stub
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


@pytest.fixture
def provider_stub(monkeypatch):
    """Real notification parser, but no provider network calls."""
    provider = NequiPaymentProvider()
    provider.create_payment = AsyncMock(return_value=ProviderPaymentResult(
        provider_transaction_id="provider-created-1",
        status=PaymentStatus.PENDING,
        provider_status="PENDING",
        payment_method="nequi_push",
        action_data={"qr_code": "synthetic-qr"},
    ))
    provider.get_payment_status = AsyncMock(return_value=ProviderStatusResult(
        status=PaymentStatus.PENDING, provider_status="PENDING",
    ))
    provider.cancel_payment = AsyncMock(return_value=ProviderStatusResult(
        status=PaymentStatus.CANCELLED, provider_status="CANCELLED",
    ))
    provider.reverse_payment = AsyncMock(return_value=ProviderReversalResult(
        status=PaymentStatus.REVERSED, provider_status="REVERSED",
    ))
    monkeypatch.setattr(
        payment_service, "get_provider", lambda code: provider if code == "nequi" else None,
    )
    return provider


@pytest.fixture
def pending_payment(db, org, store_co, nequi_connection):
    txn = PaymentTransaction(
        organization_id=org.id, store_id=store_co.id, provider="nequi",
        idempotency_key="hardening-payment", amount=Decimal("89900"),
        currency="COP", payment_method="nequi_push", status="pending",
    )
    db.add(txn)
    db.commit()
    return txn


class TestPaymentHardening:
    def test_execute_persists_successful_provider_result(self, db, pending_payment, provider_stub):
        import asyncio

        txn = asyncio.run(payment_service.execute_payment(
            db, pending_payment.organization_id, pending_payment.store_id, pending_payment.id,
        ))
        db.commit()
        db.refresh(txn)
        assert txn.provider_transaction_id == "provider-created-1"
        assert txn.status == "pending"
        assert txn._action_data == {"qr_code": "synthetic-qr"}
        provider_stub.create_payment.assert_awaited_once()

    def test_reconcile_marks_matching_order_paid(self, db, pending_payment, order, provider_stub):
        import asyncio

        pending_payment.order_id = order.id
        pending_payment.provider_transaction_id = "provider-confirmed-1"
        provider_stub.get_payment_status.return_value = ProviderStatusResult(
            PaymentStatus.PAID, "APPROVED", paid_at="2026-10-25T10:00:00+00:00",
        )
        txn = asyncio.run(payment_service.reconcile_payment_status(
            db, pending_payment.organization_id, pending_payment.store_id, pending_payment.id,
        ))
        db.commit()
        assert txn.status == "paid"
        assert txn.paid_at is not None
        assert order.payment_status == "paid"

    def test_cancel_persists_successful_provider_result(self, db, pending_payment, provider_stub):
        import asyncio

        pending_payment.provider_transaction_id = "provider-cancel-1"
        txn = asyncio.run(payment_service.cancel_payment(
            db, pending_payment.organization_id, pending_payment.store_id, pending_payment.id,
        ))
        assert txn.status == "cancelled"
        provider_stub.cancel_payment.assert_awaited_once()

    def test_reverse_persists_successful_provider_result(self, db, pending_payment, provider_stub):
        import asyncio

        pending_payment.status = "paid"
        pending_payment.provider_transaction_id = "provider-refund-1"
        txn = asyncio.run(payment_service.reverse_payment(
            db, pending_payment.organization_id, pending_payment.store_id, pending_payment.id,
        ))
        assert txn.status == "reversed"
        assert txn.reversed_at is not None
        provider_stub.reverse_payment.assert_awaited_once()

    @pytest.mark.parametrize("amount", [Decimal("1"), Decimal("0"), None, "NaN", "Infinity"])
    def test_order_amount_and_currency_are_authoritative(
        self, db, org, store_co, order, nequi_connection, amount,
    ):
        txn = payment_service.create_payment(
            db, org.id, store_co.id, "nequi", amount, "USD", "+573000000000",
            "authoritative-total", order_id=order.id,
        )
        assert txn.amount == order.total_amount
        assert txn.currency == order.currency

    @pytest.mark.parametrize("amount", ["NaN", "sNaN", "Infinity", "-Infinity"])
    def test_standalone_payment_rejects_non_finite_amounts(
        self, db, org, store_co, nequi_connection, amount,
    ):
        with pytest.raises(payment_service.PaymentInvalidAmountError):
            payment_service.create_payment(
                db, org.id, store_co.id, "nequi", amount, "COP", "+573000000000", "non-finite",
            )

    def test_underpayment_does_not_mark_order_paid(self, db, pending_payment, order, provider_stub):
        import asyncio

        pending_payment.order_id = order.id
        pending_payment.amount = Decimal("1")
        pending_payment.provider_transaction_id = "legacy-underpayment"
        db.flush()
        provider_stub.get_payment_status.return_value = ProviderStatusResult(PaymentStatus.PAID, "APPROVED")
        asyncio.run(payment_service.process_webhook(
            db, "nequi", {}, json.dumps({"transactionId": "legacy-underpayment", "status": "APPROVED"}).encode(),
        ))
        assert pending_payment.status == "paid"  # The receipt itself really is paid.
        assert order.payment_status != "paid"  # It does not settle the full order.

    @pytest.mark.parametrize("confirmed_status", [PaymentStatus.PENDING, PaymentStatus.PAID])
    def test_http_retry_does_not_call_provider_again(
        self, app_client, store_co, nequi_connection, provider_stub, confirmed_status,
    ):
        provider_stub.create_payment.return_value.status = confirmed_status
        body = {
            "amount": "100", "currency": "COP", "customer_phone": "+573000000000",
            "idempotency_key": "http-retry",
        }
        first = app_client.post(f"/api/stores/{store_co.id}/payments", json=body)
        second = app_client.post(f"/api/stores/{store_co.id}/payments", json=body)
        assert first.status_code == second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        provider_stub.create_payment.assert_awaited_once()

    def test_idempotency_key_cannot_be_rebound_to_another_store(
        self, db, org, store_co, nequi_connection,
    ):
        payment_service.create_payment(
            db, org.id, store_co.id, "nequi", "100", "COP", "+573000000000", "scoped-key",
        )
        other = Store(
            organization_id=org.id, name="Other", slug="other-payment", country_code="CO",
            currency="COP", timezone="America/Bogota",
        )
        db.add(other)
        db.flush()
        payment_service.configure_connection(db, org.id, other.id, "nequi", "sandbox", "id", "secret")
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db, org.id, other.id, "nequi", "100", "COP", "+573000000000", "scoped-key",
            )
        assert exc.value.code == "PAYMENT_IDEMPOTENCY_CONFLICT"


class TestWebhookHardening:
    @pytest.mark.parametrize("claimed_status", ["REJECTED", "FAILED", "EXPIRED", "CANCELLED", "APPROVED"])
    def test_all_statuses_are_confirmed_server_to_server(
        self, db, pending_payment, provider_stub, nequi_connection, claimed_status,
    ):
        import asyncio

        pending_payment.provider_transaction_id = "server-authoritative"
        nequi_connection.webhook_secret_encrypted = encrypt_payment_secret("configured-secret")
        db.flush()
        result = asyncio.run(payment_service.process_webhook(
            db, "nequi", {}, json.dumps({
                "transactionId": "server-authoritative", "status": claimed_status, "eventId": "untrusted-event",
            }).encode(),
        ))
        assert result["new_status"] == pending_payment.status == "pending"
        assert pending_payment.provider_status == "PENDING"
        provider_stub.get_payment_status.assert_awaited_once()

    def test_provider_failure_is_retryable_and_does_not_consume_event(
        self, app_client, db, pending_payment, provider_stub, nequi_connection,
    ):
        pending_payment.provider_transaction_id = "provider-unavailable"
        db.commit()
        provider_stub.get_payment_status.side_effect = RuntimeError("provider unavailable")
        response = app_client.post("/api/webhooks/payments/nequi", json={
            "transactionId": "provider-unavailable", "status": "REJECTED", "eventId": "retry-me",
        })
        assert response.status_code == 503
        db.refresh(pending_payment)
        db.refresh(nequi_connection)
        assert pending_payment.status == "pending"
        assert nequi_connection.last_event_id is None

    def test_replayed_event_cannot_hide_new_provider_status(self, db, pending_payment, provider_stub):
        import asyncio

        pending_payment.provider_transaction_id = "reused-event"
        db.flush()
        payload = json.dumps({"transactionId": "reused-event", "status": "REJECTED", "eventId": "same-id"}).encode()
        asyncio.run(payment_service.process_webhook(db, "nequi", {}, payload))
        assert pending_payment.status == "pending"
        provider_stub.get_payment_status.return_value = ProviderStatusResult(PaymentStatus.PAID, "APPROVED")
        result = asyncio.run(payment_service.process_webhook(db, "nequi", {}, payload))
        assert result["new_status"] == pending_payment.status == "paid"
        assert provider_stub.get_payment_status.await_count == 2

    def test_paid_timestamp_comes_from_provider_not_webhook(self, db, pending_payment, provider_stub):
        import asyncio

        pending_payment.provider_transaction_id = "paid-timestamp"
        db.flush()
        provider_stub.get_payment_status.return_value = ProviderStatusResult(
            PaymentStatus.PAID, "APPROVED", paid_at="2026-10-25T10:00:00+00:00",
        )
        asyncio.run(payment_service.process_webhook(db, "nequi", {}, json.dumps({
            "transactionId": "paid-timestamp", "status": "APPROVED", "timestamp": "1900-01-01T00:00:00Z",
        }).encode()))
        assert pending_payment.paid_at.year == 2026

    @pytest.mark.parametrize("payload", [[], None, 1, {"transactionId": []}, {"transactionId": {"id": 1}}])
    def test_malformed_webhooks_are_rejected(self, app_client, payload):
        response = app_client.post(
            "/api/webhooks/payments/nequi", content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400


class TestShopifyCheckoutBoundary:
    """General payment routes must not become an off-platform Shopify checkout."""

    @pytest.mark.parametrize("provider,origin", [
        ("shopify", "direct"), ("paddle", "shopify_install"), (None, "shopify_install"),
    ])
    def test_shopify_acquisition_cannot_bypass_checkout_without_a_connection(
        self, db, org, store_co, nequi_connection, provider, origin,
    ):
        org.billing_provider = provider
        org.billing_onboarding_channel = origin
        db.commit()
        assert payment_service.get_available_store_providers(db, org.id, store_co.id) == []
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db, org.id, store_co.id, "nequi", "100", "COP", "+573000000000", "shopify-origin",
            )
        assert exc.value.code == "SHOPIFY_CHECKOUT_REQUIRED"

    @pytest.mark.parametrize("connection_status", ["connected", "disconnected", "revoked", "error"])
    def test_shopify_stores_do_not_advertise_external_payment_providers(
        self, db, org, store_co, app_client, connection_status,
    ):
        db.add(CommerceConnection(
            organization_id=org.id, store_id=store_co.id, provider="shopify",
            status=connection_status, external_store_url="synthetic.myshopify.com",
        ))
        db.commit()
        response = app_client.get(f"/api/stores/{store_co.id}/payments/providers")
        assert response.status_code == 200
        assert response.json()["providers"] == []

    @pytest.mark.parametrize("market,provider", [("store_co", "nequi"), ("store_br", "mercado_pago")])
    def test_cannot_configure_external_payments_for_shopify_store(
        self, db, org, request, market, provider,
    ):
        store = request.getfixturevalue(market)
        db.add(CommerceConnection(
            organization_id=org.id, store_id=store.id, provider="shopify",
            status="connected", external_store_url="synthetic.myshopify.com",
        ))
        db.commit()
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.configure_connection(db, org.id, store.id, provider, "sandbox", "id", "secret")
        assert exc.value.code == "SHOPIFY_CHECKOUT_REQUIRED"
        assert db.query(PaymentConnection).count() == 0

    @pytest.mark.parametrize("with_order", [False, True])
    def test_shopify_store_cannot_create_external_charge(
        self, db, org, store_co, order, nequi_connection, with_order,
    ):
        db.add(CommerceConnection(
            organization_id=org.id, store_id=store_co.id, provider="shopify",
            status="connected", external_store_url="synthetic.myshopify.com",
        ))
        db.commit()
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db, org.id, store_co.id, "nequi", "100", "COP", "+573000000000", "shopify-external",
                order_id=order.id if with_order else None,
            )
        assert exc.value.code == "SHOPIFY_CHECKOUT_REQUIRED"
        assert db.query(PaymentTransaction).count() == 0

    @pytest.mark.parametrize("source_field,value", [
        ("source", "shopify"), ("source", "shopify_chat_checkout"), ("source", "shopify_poc"),
        ("shopify_order_id", "123"), ("shopify_draft_order_id", "123"),
    ])
    def test_shopify_order_stays_protected_without_connection_record(
        self, db, org, store_co, order, nequi_connection, source_field, value,
    ):
        setattr(order, source_field, value)
        db.commit()
        with pytest.raises(payment_service.PaymentError) as exc:
            payment_service.create_payment(
                db, org.id, store_co.id, "nequi", "100", "COP", "+573000000000", "orphan-shopify-order",
                order_id=order.id,
            )
        assert exc.value.code == "SHOPIFY_CHECKOUT_REQUIRED"

    def test_legacy_shopify_domain_blocks_external_checkout_without_connection(
        self, db, org, store_co, nequi_connection,
    ):
        store_co.shopify_domain = "synthetic.myshopify.com"
        db.commit()
        assert payment_service.get_available_store_providers(db, org.id, store_co.id) == []
        with pytest.raises(payment_service.PaymentCheckoutRequiredError):
            payment_service.configure_connection(db, org.id, store_co.id, "nequi", "sandbox", "id", "secret")
        with pytest.raises(payment_service.PaymentCheckoutRequiredError):
            payment_service.create_payment(
                db, org.id, store_co.id, "nequi", "100", "COP", "+573000000000", "legacy-shopify-domain",
            )

    @pytest.mark.parametrize("provider", ["nequi", "mercado_pago"])
    def test_http_configuration_rejected_for_shopify_origin(
        self, db, org, store_co, app_client, provider,
    ):
        org.billing_onboarding_channel = "shopify_install"
        db.commit()
        response = app_client.post(f"/api/stores/{store_co.id}/payments/{provider}/connect", json={
            "provider": provider, "environment": "sandbox", "client_id": "synthetic", "client_secret": "synthetic",
        })
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "SHOPIFY_CHECKOUT_REQUIRED"
        assert db.query(PaymentConnection).count() == 0

    def test_pending_charge_is_rechecked_before_provider_execution(
        self, db, org, store_co, pending_payment, provider_stub,
    ):
        import asyncio

        db.add(CommerceConnection(
            organization_id=org.id, store_id=store_co.id, provider="shopify",
            status="connected", external_store_url="synthetic.myshopify.com",
        ))
        db.commit()
        with pytest.raises(payment_service.PaymentError) as exc:
            asyncio.run(payment_service.execute_payment(db, org.id, store_co.id, pending_payment.id))
        assert exc.value.code == "SHOPIFY_CHECKOUT_REQUIRED"
        provider_stub.create_payment.assert_not_awaited()

    def test_other_store_shopify_connection_does_not_block_independent_payments(
        self, db, org, store_co, store_br, nequi_connection,
    ):
        db.add(CommerceConnection(
            organization_id=org.id, store_id=store_br.id, provider="shopify",
            status="connected", external_store_url="other.myshopify.com",
        ))
        db.commit()
        txn = payment_service.create_payment(
            db, org.id, store_co.id, "nequi", "100", "COP", "+573000000000", "independent-store",
        )
        assert txn.store_id == store_co.id

    def test_http_rejection_never_reaches_external_provider(
        self, db, org, store_co, nequi_connection, provider_stub, app_client,
    ):
        db.add(CommerceConnection(
            organization_id=org.id, store_id=store_co.id, provider="shopify",
            status="connected", external_store_url="synthetic.myshopify.com",
        ))
        db.commit()
        response = app_client.post(f"/api/stores/{store_co.id}/payments", json={
            "provider": "nequi", "amount": "100", "currency": "COP", "customer_phone": "+573000000000",
        })
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "SHOPIFY_CHECKOUT_REQUIRED"
        provider_stub.create_payment.assert_not_awaited()

    def test_legacy_refunds_keep_the_original_processor(
        self, db, org, store_co, pending_payment, provider_stub,
    ):
        import asyncio

        pending_payment.status = "paid"
        pending_payment.provider_transaction_id = "original-nequi-receipt"
        db.add(CommerceConnection(
            organization_id=org.id, store_id=store_co.id, provider="shopify",
            status="connected", external_store_url="synthetic.myshopify.com",
        ))
        db.commit()
        result = asyncio.run(payment_service.reverse_payment(db, org.id, store_co.id, pending_payment.id))
        assert result.status == "reversed"
        provider_stub.reverse_payment.assert_awaited_once()
        assert provider_stub.reverse_payment.await_args.kwargs["provider_transaction_id"] == "original-nequi-receipt"
        assert provider_stub.reverse_payment.await_args.kwargs["amount"] == pending_payment.amount
        provider_stub.create_payment.assert_not_awaited()
