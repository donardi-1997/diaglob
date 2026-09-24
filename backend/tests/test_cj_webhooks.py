"""CJ logistics webhook ingestion tests."""

import base64
import hashlib
import hmac
import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.shipments import CJWebhookReceipt, Shipment, TrackingEvent
from app.model_domains.supplier_integrations import SupplierConnection
from app.model_domains.supplier_orders import SupplierOrder
from app.models import Organization, Store
from app.services import cj_webhooks


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def schema():
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
        name="Webhook Org",
        slug="webhook-org",
        plan="growth",
        subscription_status="active",
        active=True,
    )
    db.add(org)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Webhook Store",
        slug="webhook-store",
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
        external_account_id="open-secret",
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
        provider_order_number="DG-1-1",
        external_order_id="CJ-1",
        supplier_status="SHIPPED",
        creation_status="created",
        idempotency_key="order-1",
        currency="USD",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(supplier_order)
    db.commit()
    return org, store, connection, supplier_order


def signed_payload(payload):
    raw = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(
            payload["openId"].encode("utf-8"),
            raw,
            hashlib.sha256,
        ).digest()
    ).decode("ascii")
    return raw, signature


def test_valid_logistic_webhook_creates_shipment_and_events(db, data):
    _org, _store, _connection, supplier_order = data
    payload = {
        "messageId": "msg-1",
        "openId": "open-secret",
        "type": "LOGISTIC",
        "messageType": "UPDATE",
        "params": {
            "orderId": "CJ-1",
            "storeOrderNumbers": ["DG-1-1"],
            "trackingNumber": "TRACK-1",
            "trackingStatus": 12,
            "logisticName": "USPS+",
            "trackingProvider": "USPS",
            "trackingUrl": "https://example.test/track",
            "logisticsTrackEvents": json.dumps(
                [
                    {
                        "status": 10,
                        "statusDesc": "Out for delivery",
                        "location": "New York, NY",
                        "eventTime": "2026-09-24 09:00:00",
                    },
                    {
                        "status": 12,
                        "statusDesc": "Delivered",
                        "location": "New York, NY",
                        "eventTime": "2026-09-24 11:00:00",
                    },
                ]
            ),
        },
    }
    raw, signature = signed_payload(payload)

    result = cj_webhooks.process_cj_webhook(
        db,
        raw_body=raw,
        signature=signature,
    )

    assert result["status"] == "DELIVERED"
    shipment = db.query(Shipment).one()
    assert shipment.supplier_order_id == supplier_order.id
    assert shipment.tracking_number == "TRACK-1"
    assert shipment.normalized_status == "DELIVERED"
    assert shipment.delivered_at == datetime(2026, 9, 24, 11, 0, 0)
    assert db.query(TrackingEvent).count() == 2
    assert db.query(CJWebhookReceipt).one().processing_status == "processed"


def test_duplicate_message_is_idempotent(db, data):
    payload = {
        "messageId": "msg-duplicate",
        "openId": "open-secret",
        "type": "LOGISTIC",
        "params": {
            "orderId": "CJ-1",
            "trackingNumber": "TRACK-DUP",
            "trackingStatus": 2,
            "logisticsTrackEvents": "[]",
        },
    }
    raw, signature = signed_payload(payload)

    first = cj_webhooks.process_cj_webhook(
        db,
        raw_body=raw,
        signature=signature,
    )
    second = cj_webhooks.process_cj_webhook(
        db,
        raw_body=raw,
        signature=signature,
    )

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert db.query(CJWebhookReceipt).count() == 1
    assert db.query(Shipment).count() == 1


def test_invalid_signature_is_rejected_without_persistence(db, data):
    payload = {
        "messageId": "msg-bad-signature",
        "openId": "open-secret",
        "type": "LOGISTIC",
        "params": {},
    }
    raw = json.dumps(payload).encode("utf-8")

    with pytest.raises(cj_webhooks.CJWebhookAuthError):
        cj_webhooks.process_cj_webhook(
            db,
            raw_body=raw,
            signature="invalid",
        )

    assert db.query(CJWebhookReceipt).count() == 0


def test_unknown_account_is_rejected(db, data):
    payload = {
        "messageId": "msg-unknown",
        "openId": "not-ours",
        "type": "LOGISTIC",
        "params": {},
    }
    raw, signature = signed_payload(payload)

    with pytest.raises(cj_webhooks.CJWebhookAuthError):
        cj_webhooks.process_cj_webhook(
            db,
            raw_body=raw,
            signature=signature,
        )


def test_event_replay_across_different_messages_deduplicates_timeline(db, data):
    event = {
        "status": 2,
        "statusDesc": "In transit",
        "location": "Los Angeles, CA",
        "eventTime": "2026-09-24 08:00:00",
    }
    for message_id in ("msg-a", "msg-b"):
        payload = {
            "messageId": message_id,
            "openId": "open-secret",
            "type": "LOGISTIC",
            "params": {
                "orderId": "CJ-1",
                "trackingNumber": "TRACK-REPLAY",
                "trackingStatus": 2,
                "logisticsTrackEvents": json.dumps([event]),
            },
        }
        raw, signature = signed_payload(payload)
        cj_webhooks.process_cj_webhook(
            db,
            raw_body=raw,
            signature=signature,
        )

    assert db.query(CJWebhookReceipt).count() == 2
    assert db.query(TrackingEvent).count() == 1
