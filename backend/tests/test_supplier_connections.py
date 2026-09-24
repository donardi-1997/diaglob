"""Supplier connection service tests."""

from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.supplier_integrations import SupplierConnection
from app.models import Organization, Store
from app.services import supplier_connections as service
from app.supplier_security import decrypt_supplier_secret


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def schema(monkeypatch):
    monkeypatch.setenv(
        "SUPPLIER_TOKEN_ENCRYPTION_KEY",
        Fernet.generate_key().decode("utf-8"),
    )
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


def make_store(db):
    org = Organization(
        name="CJ Org",
        slug="cj-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="US Store",
        slug="us-store",
        country_code="US",
        currency="USD",
        timezone="America/New_York",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.commit()
    db.refresh(org)
    db.refresh(store)
    return org, store


def token_payload(access="access-1", refresh="refresh-1"):
    return {
        "openId": 77,
        "accessToken": access,
        "refreshToken": refresh,
        "accessTokenExpiryDate": "2027-03-20T12:00:00+00:00",
        "refreshTokenExpiryDate": "2027-03-20T12:00:00+00:00",
    }


def test_connect_cj_validates_and_encrypts_credentials(db, monkeypatch):
    org, store = make_store(db)
    monkeypatch.setattr(
        service.cj_client,
        "get_access_token",
        lambda _key: token_payload(),
    )
    monkeypatch.setattr(
        service.cj_client,
        "get_settings",
        lambda _token: {
            "openId": 77,
            "openName": "Merchant CJ",
            "openEmail": "merchant@example.com",
            "setting": {"qpsLimit": 2},
            "isSandbox": False,
        },
    )

    result = service.connect_cj(db, org.id, store.id, "api-key-secret")

    assert result["connected"] is True
    row = db.query(SupplierConnection).one()
    assert row.provider == "cj"
    assert row.external_account_id == "77"
    assert row.api_key_encrypted != "api-key-secret"
    assert decrypt_supplier_secret(row.api_key_encrypted) == "api-key-secret"
    assert decrypt_supplier_secret(row.access_token_encrypted) == "access-1"
    assert decrypt_supplier_secret(row.refresh_token_encrypted) == "refresh-1"


def test_connect_cj_reconnects_without_duplicate_row(db, monkeypatch):
    org, store = make_store(db)
    monkeypatch.setattr(
        service.cj_client,
        "get_access_token",
        lambda key: token_payload(access=f"access-{key}"),
    )
    monkeypatch.setattr(
        service.cj_client,
        "get_settings",
        lambda _token: {"openId": 77, "openName": "Merchant CJ"},
    )

    service.connect_cj(db, org.id, store.id, "one")
    service.connect_cj(db, org.id, store.id, "two")

    assert db.query(SupplierConnection).count() == 1
    row = db.query(SupplierConnection).one()
    assert decrypt_supplier_secret(row.api_key_encrypted) == "two"


def test_expired_access_token_refreshes_and_persists(db, monkeypatch):
    org, store = make_store(db)
    now = datetime(2026, 9, 24, 12, 0, 0)
    row = SupplierConnection(
        organization_id=org.id,
        store_id=store.id,
        provider="cj",
        external_account_id="77",
        api_key_encrypted=service._encrypt("api-key"),
        access_token_encrypted=service._encrypt("old-access"),
        refresh_token_encrypted=service._encrypt("refresh"),
        access_token_expires_at=now,
        refresh_token_expires_at=now + timedelta(days=30),
        status="connected",
        connected_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()

    monkeypatch.setattr(
        service.cj_client,
        "refresh_access_token",
        lambda _token: token_payload(access="new-access", refresh="new-refresh"),
    )

    token = service.get_valid_cj_access_token(
        db,
        org.id,
        store.id,
        now=now,
    )

    assert token == "new-access"
    db.refresh(row)
    assert decrypt_supplier_secret(row.access_token_encrypted) == "new-access"


def test_disconnect_removes_supplier_credentials(db, monkeypatch):
    org, store = make_store(db)
    monkeypatch.setattr(
        service.cj_client,
        "get_access_token",
        lambda _key: token_payload(),
    )
    monkeypatch.setattr(
        service.cj_client,
        "get_settings",
        lambda _token: {"openId": 77, "openName": "Merchant CJ"},
    )
    service.connect_cj(db, org.id, store.id, "api-key")

    result = service.disconnect_cj(db, org.id, store.id)

    assert result["connected"] is False
    assert db.query(SupplierConnection).count() == 0
