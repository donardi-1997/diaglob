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
    PaddleAiReconciliation,
)
from app.services.paddle_fulfillment import (
    dispatch_verified_notification, subscription_grants_access,
    verify_notification, create_portal_session_url,
    get_paddle_billing_capabilities,
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


def test_shopify_connected_paddle_migration_keeps_paid_access_until_cancel_date(db):
    from app.models import CommerceConnection, Organization, Store

    organization = Organization(
        name="Shopify migration", slug="shopify-paddle-migration",
        plan="starter", billing_provider="paddle",
        billing_onboarding_channel="direct", billing_customer_id="ctm_migrate",
        billing_subscription_id="sub_migrate", subscription_status="active",
    )
    store = Store(
        organization=organization, name="Shop", slug="shop",
        country_code="CO", currency="COP", timezone="America/Bogota",
    )
    db.add(organization)
    db.flush()
    db.add(CommerceConnection(
        organization_id=organization.id, store_id=store.id,
        provider="shopify", external_store_url="migrate.myshopify.com",
        status="connected",
    ))
    db.commit()

    dispatch_verified_notification(_event(
        "evt_migrate_active", "subscription.updated", {
            "id": "sub_migrate", "customer_id": "ctm_migrate",
            "status": "active",
            "items": [{"price": {"id": "pri_migrate", "product_id": "pro_1"}}],
            "scheduled_change": {
                "action": "cancel", "effective_at": "2026-11-16T12:00:00Z",
            },
        }, "2026-10-16T12:00:00Z",
    ), db)
    assert organization.plan == "starter"
    assert organization.subscription_status == "active"
    assert store.active is True

    dispatch_verified_notification(_event(
        "evt_migrate_canceled", "subscription.canceled", {
            "id": "sub_migrate", "customer_id": "ctm_migrate",
            "status": "canceled",
        }, "2026-11-16T12:00:00Z",
    ), db)
    assert organization.plan == "starter"
    assert organization.subscription_status == "canceled"
    assert store.active is True


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


def test_legacy_paddle_ids_are_not_synchronized_entitlements(db):
    from app.models import Organization

    organization = Organization(
        name="Legacy direct billing", slug="legacy-direct-billing",
        plan="growth", billing_provider="paddle",
        billing_customer_id="ctm_legacy_ref",
        billing_subscription_id="sub_legacy_ref",
        subscription_status="active",
    )
    db.add(organization)
    db.commit()

    status = get_paddle_billing_capabilities(db, organization)
    assert status == {
        "customer_synchronized": False,
        "subscription_synchronized": False,
        "portal_available": False,
        "plan_changes_available": False,
    }
    with pytest.raises(LookupError, match="not synchronized"):
        create_portal_session_url(db, organization)


def test_paddle_status_requires_tenant_bound_customer_and_subscription(db):
    from app.models import Organization

    organization = Organization(
        name="Billing test", slug="billing-sync-test",
        plan="pro", billing_provider="paddle",
        billing_customer_id="ctm_paddle_sync",
        billing_subscription_id="sub_paddle_sync",
    )
    other = Organization(name="Other billing tenant", slug="billing-sync-other")
    db.add_all([organization, other])
    db.commit()

    customer = PaddleBillingCustomer(
        customer_id="ctm_paddle_sync", organization_id=other.id,
    )
    subscription = PaddleBillingSubscription(
        subscription_id="sub_paddle_sync", organization_id=other.id,
        customer_id="ctm_paddle_sync", status="active",
    )
    db.add_all([customer, subscription])
    db.commit()

    assert not get_paddle_billing_capabilities(db, organization)["portal_available"]
    customer.organization_id = organization.id
    db.commit()
    partial = get_paddle_billing_capabilities(db, organization)
    assert partial["customer_synchronized"]
    assert not partial["subscription_synchronized"]
    assert not partial["portal_available"]

    subscription.organization_id = organization.id
    db.commit()
    ready = get_paddle_billing_capabilities(db, organization)
    assert ready["customer_synchronized"]
    assert ready["subscription_synchronized"]
    assert ready["portal_available"]
    assert ready["plan_changes_available"]

    subscription.status = "canceled"
    db.commit()
    canceled = get_paddle_billing_capabilities(db, organization)
    assert canceled["portal_available"]
    assert not canceled["plan_changes_available"]


def test_other_event_types_are_ignored_without_creating_receipts(db):
    result = dispatch_verified_notification(
        _event("evt_unsubscribed", "address.updated", {"id": "add_1"}), db,
    )
    assert result["ignored"] is True
    assert db.query(PaddleWebhookEvent).count() == 0


def _legacy_ai_event(event_id="evt_legacy", customer="ctm_legacy", transaction="txn_ai_legacy"):
    return _event(event_id, "transaction.completed", {
        "id": transaction, "customer_id": customer,
        "status": "completed",
        "custom_data": {
            "purchase_type": "ai_usage_package",
            "organization_id": "999999",  # untrusted, must never be used
            "package_key": "ai_1000", "responses": 1000,
        },
        "items": [{"quantity": 1, "price": {"id": "pri_ai_1000"}}],
    }, "2026-10-15T10:00:00Z")


def _known_ai_owner(db, customer="ctm_legacy"):
    from app.models import Organization
    organization = Organization(
        name="Paddle AI tenant", slug="paddle-ai-test",
        plan="pro", billing_provider="paddle",
        billing_onboarding_channel="direct",
        billing_customer_id=customer,
        billing_last_event_at=__import__("datetime").datetime(2026, 10, 16, 12),
    )
    db.add(organization)
    db.commit()
    return organization


def test_legacy_ai_credit_is_fulfilled_despite_newer_subscription_event(db, monkeypatch):
    from unittest.mock import patch
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")
    org = _known_ai_owner(db)
    with patch(
        "app.services.paddle_fulfillment.fulfill_ai_usage_package_transaction",
        return_value={"ok": True, "credited": True},
    ) as fulfill, patch(
        "app.services.paddle_fulfillment.is_out_of_order_event",
        side_effect=AssertionError("AI credits must bypass subscription timestamps"),
    ):
        outcome = dispatch_verified_notification(_legacy_ai_event(), db)

    assert outcome["credited"] is True
    assert fulfill.call_args.kwargs["organization_id"] == org.id
    assert db.get(PaddleWebhookEvent, "evt_legacy") is not None
    assert db.query(PaddleAiReconciliation).count() == 0
    assert dispatch_verified_notification(_legacy_ai_event(), db)["duplicate"] is True


def test_unsigned_legacy_purchase_with_unbound_customer_is_retained(db, monkeypatch):
    from unittest.mock import patch
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")
    with patch("app.services.paddle_fulfillment.fulfill_ai_usage_package_transaction") as fulfill:
        result = dispatch_verified_notification(_legacy_ai_event(), db)
        assert result["pending_reconciliation"] is True
        assert db.get(PaddleAiReconciliation, "txn_ai_legacy").status == "pending"
        assert db.get(PaddleAiReconciliation, "txn_ai_legacy").claimed_organization_id == "999999"
        assert db.get(PaddleWebhookEvent, "evt_legacy") is not None
        assert dispatch_verified_notification(_legacy_ai_event(), db)["duplicate"] is True
        # A different notification for the same paid transaction does not
        # create duplicate pending rows or claim untrusted organization 999999.
        second = dispatch_verified_notification(
            _legacy_ai_event(event_id="evt_legacy_again"), db,
        )
        assert second["pending_reconciliation"] is True
        assert db.query(PaddleAiReconciliation).count() == 1
        fulfill.assert_not_called()


def test_invalid_signed_ai_metadata_never_falls_back_to_legacy_matching(db, monkeypatch):
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")
    _known_ai_owner(db)
    event = _legacy_ai_event()
    event["data"]["custom_data"]["package_signature"] = "invalid"
    result = dispatch_verified_notification(event, db)
    assert result["pending_reconciliation"] is True
    assert db.get(PaddleAiReconciliation, "txn_ai_legacy").status == "pending"


def test_legacy_ambiguous_customer_cannot_claim_either_tenant(db, monkeypatch):
    from app.models import Organization
    from unittest.mock import patch
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")
    _known_ai_owner(db)
    db.add(Organization(
        name="Other tenant", slug="paddle-ai-other",
        plan="pro", billing_provider="paddle",
        billing_customer_id="ctm_legacy",
    ))
    db.commit()
    with patch("app.services.paddle_fulfillment.fulfill_ai_usage_package_transaction") as fulfill:
        outcome = dispatch_verified_notification(_legacy_ai_event(), db)
        assert outcome["pending_reconciliation"] is True
        fulfill.assert_not_called()


def test_pending_purchase_can_be_reconciled_only_from_verified_paddle_lookup(db, monkeypatch):
    from unittest.mock import patch
    from app.services.paddle_fulfillment import reconcile_pending_ai_transaction
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")
    dispatch_verified_notification(_legacy_ai_event(), db)
    with patch(
        "app.paddle_client.get_transaction",
        return_value=_legacy_ai_event()["data"],
    ), patch("app.services.paddle_fulfillment.fulfill_ai_usage_package_transaction") as fulfill:
        # No independently bound Paddle customer yet.
        assert reconcile_pending_ai_transaction(db, "txn_ai_legacy")["pending_reconciliation"] is True
        fulfill.assert_not_called()
        org = _known_ai_owner(db)
        fulfill.return_value = {"ok": True, "credited": True}
        res = reconcile_pending_ai_transaction(db, "txn_ai_legacy")
    assert res["credited"] is True
    assert db.get(PaddleAiReconciliation, "txn_ai_legacy").status == "credited"
    assert db.get(PaddleAiReconciliation, "txn_ai_legacy").resolved_at is not None
    assert org.billing_customer_id == "ctm_legacy"


def test_paddle_reconciliation_rejects_uncompleted_transaction(db, monkeypatch):
    from unittest.mock import patch
    from app.services.paddle_fulfillment import reconcile_pending_ai_transaction
    monkeypatch.setenv("PADDLE_PRICE_AI_1000", "pri_ai_1000")
    dispatch_verified_notification(_legacy_ai_event(), db)
    payload = _legacy_ai_event()["data"]
    payload["status"] = "billed"
    with patch("app.paddle_client.get_transaction", return_value=payload):
        with pytest.raises(ValueError, match="not confirmed completed"):
            reconcile_pending_ai_transaction(db, "txn_ai_legacy")
    assert db.get(PaddleAiReconciliation, "txn_ai_legacy").status == "pending"
