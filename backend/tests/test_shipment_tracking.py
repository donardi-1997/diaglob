"""Shipment tracking service tests."""

from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.shipments import Shipment
from app.model_domains.supplier_integrations import SupplierConnection
from app.model_domains.supplier_orders import SupplierOrder
from app.models import Organization, Store
from app.services import shipment_tracking
from app.supplier_security import encrypt_supplier_secret


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


@pytest.fixture()
def data(db):
    org = Organization(
        name="Tracking Org",
        slug="tracking-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Tracking Store",
        slug="tracking-store",
        country_code="US",
        currency="USD",
        timezone="America/New_York",
        default_language="en",
        active=True,
        deleted=False,
    )
    db.add(store)
    db.flush()
    connection = SupplierConnection(
        organization_id=org.id,
        store_id=store.id,
        provider="cj",
        external_account_id="77",
        api_key_encrypted=encrypt_supplier_secret("api-key"),
        access_token_encrypted=encrypt_supplier_secret("access"),
        refresh_token_encrypted=encrypt_supplier_secret("refresh"),
        access_token_expires_at=datetime.utcnow() + timedelta(days=30),
        refresh_token_expires_at=datetime.utcnow() + timedelta(days=60),
        status="connected",
        connected_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(connection)
    db.flush()
    supplier_order = SupplierOrder(
        organization_id=org.id,
        store_id=store.id,
        supplier_connection_id=connection.id,
        provider="cj",
        provider_order_number="DG-TRACK",
        external_order_id="CJ-TRACK",
        supplier_status="SHIPPED",
        creation_status="created",
        idempotency_key="track-order",
        currency="USD",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(supplier_order)
    db.commit()
    return org, store, supplier_order


def test_tracking_code_normalization():
    assert shipment_tracking.normalize_cj_tracking_code(10) == "OUT_FOR_DELIVERY"
    assert shipment_tracking.normalize_cj_tracking_code("12") == "DELIVERED"
    assert shipment_tracking.normalize_cj_tracking_code(7) == "CUSTOMS"
    assert shipment_tracking.normalize_cj_tracking_code("bad") == "PENDING"


def test_sync_without_tracking_number_is_explicit(db, data, monkeypatch):
    org, store, supplier_order = data
    monkeypatch.setattr(
        shipment_tracking,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "access",
    )
    monkeypatch.setattr(
        shipment_tracking.cj_client,
        "get_order",
        lambda *_args, **_kwargs: {
            "orderId": "CJ-TRACK",
            "orderStatus": "UNSHIPPED",
        },
    )

    result = shipment_tracking.sync_cj_shipment(
        db,
        org.id,
        store.id,
        supplier_order.id,
    )

    assert result == {
        "available": False,
        "supplier_order_id": supplier_order.id,
        "reason": "TRACKING_NUMBER_NOT_AVAILABLE",
    }
    assert db.query(Shipment).count() == 0


def test_sync_tracking_uses_current_cj_endpoint_result(db, data, monkeypatch):
    org, store, supplier_order = data
    monkeypatch.setattr(
        shipment_tracking,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "access",
    )
    monkeypatch.setattr(
        shipment_tracking.cj_client,
        "get_order",
        lambda *_args, **_kwargs: {
            "orderId": "CJ-TRACK",
            "trackNumber": "TRACK-123",
            "logisticName": "USPS+",
            "trackingProvider": "USPS",
            "trackingUrl": "https://example.test/track",
        },
    )
    monkeypatch.setattr(
        shipment_tracking.cj_client,
        "get_tracking_info",
        lambda *_args, **_kwargs: [
            {
                "trackingNumber": "TRACK-123",
                "trackingFrom": "CN",
                "trackingTo": "US",
                "trackingStatus": "Delivered",
                "deliveryDay": 8,
                "deliveryTime": "2026-09-24 10:30:00",
                "lastMileCarrier": "USPS",
                "lastTrackNumber": "9400",
            }
        ],
    )

    result = shipment_tracking.sync_cj_shipment(
        db,
        org.id,
        store.id,
        supplier_order.id,
    )

    assert result["available"] is True
    shipment = db.query(Shipment).one()
    assert shipment.tracking_number == "TRACK-123"
    assert shipment.normalized_status == "DELIVERED"
    assert shipment.destination_country_code == "US"
    assert shipment.last_mile_carrier == "USPS"
    assert shipment.last_mile_tracking_number == "9400"
    assert shipment.delivery_time == datetime(2026, 9, 24, 10, 30, 0)


def test_webhook_configuration_uses_public_api_url(db, data, monkeypatch):
    org, store, _supplier_order = data
    monkeypatch.setattr(
        shipment_tracking,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "access",
    )
    calls = []
    monkeypatch.setattr(
        shipment_tracking.cj_client,
        "set_webhook_configuration",
        lambda token, url: calls.append((token, url)) or True,
    )

    result = shipment_tracking.configure_cj_logistics_webhook(
        db,
        org.id,
        store.id,
    )

    assert result["topic"] == "LOGISTIC"
    assert calls[0][0] == "access"
    assert calls[0][1].endswith("/api/webhooks/cj")
