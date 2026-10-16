"""Regression checks for the durable Paddle notification and portal layer."""
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app import models  # noqa: F401 - register all mapped entities
from app.model_domains.paddle_billing import (
    PaddleBillingCustomer, PaddleBillingSubscription, PaddleWebhookEvent,
)
from app.services.paddle_fulfillment import (
    dispatch_verified_notification, subscription_grants_access,
    verify_notification, create_portal_session_url,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _event(event_id, event_type, data, occurred_at="2026-10-16T12:00:00Z"):
    return {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "data": data,
    }


def test_sdk_verifies_raw_bytes_before_parsing():
    payload = json.dumps(_event("evt_sdk", "customer.updated", {
        "id": "ctm_test", "email": "person@example.test",
    }), separators=(",", ":")).encode()
    secret = "notification-secret-not-an-api-key"
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode(), timestamp.encode() + b":" + payload, hashlib.sha256
    ).hexdigest()
    header = f"ts={timestamp};h1={signature}"

    assert verify_notification(payload, header, secret)["event_id"] == "evt_sdk"
    with pytest.raises(ValueError, match="Invalid Paddle signature"):
        verify_notification(payload + b" ", header, secret)
    with pytest.raises(ValueError):
        verify_notification(payload, "", secret)


def test_customer_upsert_and_duplicate_event_id(db):
    event = _event("evt_1", "customer.created", {
        "id": "ctm_one", "email": "one@example.test",
    })
    assert dispatch_verified_notification(event, db)["ok"]
    assert dispatch_verified_notification(event, db)["duplicate"] is True
    assert db.query(PaddleBillingCustomer).count() == 1
    assert db.query(PaddleWebhookEvent).count() == 1
    assert db.get(PaddleBillingCustomer, "ctm_one").email == "one@example.test"

    assert dispatch_verified_notification(_event(
        "evt_2", "customer.updated",
        {"id": "ctm_one", "email": "new@example.test"},
        "2026-10-17T12:00:00Z",
    ), db)["ok"]
    assert db.get(PaddleBillingCustomer, "ctm_one").email == "new@example.test"


def test_customer_older_delivery_never_overwrites_newer_email(db):
    dispatch_verified_notification(_event(
        "evt_new", "customer.updated",
        {"id": "ctm_new", "email": "current@example.test"},
        "2026-10-17T12:00:00Z",
    ), db)
    dispatch_verified_notification(_event(
        "evt_old", "customer.created",
        {"id": "ctm_new", "email": "stale@example.test"},
        "2026-10-15T12:00:00Z",
    ), db)
    assert db.get(PaddleBillingCustomer, "ctm_new").email == "current@example.test"


def test_scheduled_cancellation_grants_access_until_actual_cancel(db):
    dispatch_verified_notification(_event(
        "evt_active", "subscription.updated", {
            "id": "sub_1", "customer_id": "ctm_1",
            "status": "active",
            "items": [{"price": {"id": "pri_month", "product_id": "pro_1"}}],
            "scheduled_change": {
                "action": "cancel", "effective_at": "2026-11-16T12:00:00Z",
            },
        }, "2026-10-16T12:00:00Z",
    ), db)
    subscription = db.get(PaddleBillingSubscription, "sub_1")
    assert subscription.status == "active"
    assert subscription.scheduled_change_action == "cancel"
    assert subscription_grants_access(subscription)
    dispatch_verified_notification(_event(
        "evt_out_of_order", "subscription.canceled", {
            "id": "sub_1", "customer_id": "ctm_1",
            "status": "canceled",
        }, "2026-10-15T12:00:00Z",
    ), db)
    assert db.get(PaddleBillingSubscription, "sub_1").status == "active"

    dispatch_verified_notification(_event(
        "evt_actual_cancel", "subscription.canceled", {
            "id": "sub_1", "customer_id": "ctm_1",
            "status": "canceled",
        }, "2026-11-16T12:00:00Z",
    ), db)
    assert not subscription_grants_access(db.get(PaddleBillingSubscription, "sub_1"))


@pytest.mark.parametrize("status,access", [
    ("active", True), ("trialing", True), ("past_due", False),
    ("paused", False), ("canceled", False), ("unknown", False),
])
def test_access_helper_uses_actual_status(status, access):
    subscription = SimpleNamespace(
        status=status, scheduled_change_action="cancel"
    )
    assert subscription_grants_access(subscription) is access


def test_customer_email_never_authorizes_an_organization(db):
    dispatch_verified_notification(_event("evt_customer", "customer.created", {
        "id": "ctm_unknown", "email": "owner@example.test",
    }), db)
    assert db.get(PaddleBillingCustomer, "ctm_unknown").organization_id is None


def test_portal_rejects_tenant_mismatch_before_calling_paddle(db):
    db.add(PaddleBillingCustomer(
        customer_id="ctm_bound", organization_id=10,
        email="one@example.test",
    ))
    db.commit()
    other_tenant = SimpleNamespace(
        id=11, billing_provider="paddle",
        billing_onboarding_channel="direct",
        billing_customer_id="ctm_bound",
        billing_subscription_id=None,
    )
    with pytest.raises(LookupError):
        create_portal_session_url(db, other_tenant)


def test_other_event_types_are_ignored_without_creating_receipts(db):
    result = dispatch_verified_notification(
        _event("evt_unsubscribed", "address.updated", {"id": "add_1"}), db,
    )
    assert result["ignored"] is True
    assert db.query(PaddleWebhookEvent).count() == 0
