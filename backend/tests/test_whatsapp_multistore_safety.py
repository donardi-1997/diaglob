"""WhatsApp multi-tenant access and provider-safety regression tests.

All data is synthetic. No live Meta token, messages or merchant action.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.whatsapp import router, whatsapp_verify_webhook
from app.api.store_access import require_authorized_path_store
from app.db import Base
from app.models import (
    Conversation, Customer, Message, Organization, Store, WhatsAppConnection,
)
from app.services.whatsapp_diagnostics import diagnose_whatsapp
from app.services.whatsapp_service import (
    WhatsAppNotFoundError, WhatsAppSendError, send_message,
)
from app.services.whatsapp_webhooks import process_webhook_payload


def _merchant_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _setup_merchant(db, org_id, store_id, phone_id):
    org = Organization(
        id=org_id, name=f"Merchant {org_id}", slug=f"merchant-{org_id}",
        plan="pro", subscription_status="active", active=True,
    )
    store = Store(
        id=store_id, organization_id=org_id, name=f"Store {store_id}",
        slug=f"store-{store_id}", country_code="CO", currency="COP",
        timezone="America/Bogota", active=True, deleted=False,
    )
    customer = Customer(
        organization_id=org_id, name=f"Customer {store_id}",
        phone=f"573100000{store_id:04d}",
    )
    db.add_all([org, store, customer])
    db.flush()
    conversation = Conversation(
        organization_id=org_id, store_id=store_id, customer_id=customer.id,
        channel="WhatsApp", mode="human",
    )
    conn = WhatsAppConnection(
        organization_id=org_id, store_id=store_id, phone_number_id=phone_id,
        business_account_id=str(4400000 + store_id),
        access_token_encrypted="never_a_real_token", verify_token="only-synthetic",
        status="connected",
    )
    db.add_all([conversation, conn])
    db.flush()
    return conversation, conn


def test_all_whatsapp_store_routes_have_membership_guard():
    checked = []
    for route in router.routes:
        if "{store_id}" not in route.path:
            continue
        checked.append(route.path)
        assert any(
            dep.dependency is require_authorized_path_store
            for dep in route.dependencies
        ), f"WhatsApp endpoint missing assigned-store protection: {route.path}"
    assert len(checked) == 6
    assert "/api/stores/{store_id}/whatsapp/diagnostics" in checked
    assert "/api/stores/{store_id}/whatsapp/templates/sync" in checked


def test_manual_outbound_to_unassigned_store_denied_before_provider():
    db = MagicMock()
    conv = SimpleNamespace(id=23, organization_id=11, store_id=55, channel="WhatsApp")
    db.query.return_value.filter.return_value.first.return_value = conv
    with patch("app.services.whatsapp_service.send_whatsapp_text_message") as send:
        with pytest.raises(WhatsAppNotFoundError):
            send_message(db, 11, 23, "hello", allowed_store_ids=[44])
        send.assert_not_called()


def test_manual_outbound_outside_24h_blocked_before_provider():
    db = MagicMock()
    conv = SimpleNamespace(id=23, organization_id=11, store_id=55, channel="WhatsApp", customer_id=77)
    connection = SimpleNamespace(
        organization_id=11, store_id=55, status="connected",
        access_token_encrypted="fake", phone_number_id="2222222222",
    )
    customer = SimpleNamespace(id=77, organization_id=11, phone="57310000000")
    db.query.return_value.filter.return_value.first.side_effect = [conv, connection, customer]
    with patch("app.services.whatsapp_service.evaluate_shopify_local_privacy",
               return_value=None), patch("app.services.whatsapp_service.get_whatsapp_service_window_status",
               return_value={"inside_window": False}), patch(
               "app.services.whatsapp_service.send_whatsapp_text_message"
               ) as send, patch("app.services.whatsapp_service.decrypt_whatsapp_secret") as decrypt:
        with pytest.raises(WhatsAppSendError, match="WHATSAPP_SERVICE_WINDOW_CLOSED"):
            send_message(db, 11, 23, "Hello", allowed_store_ids=[55])
        decrypt.assert_not_called()
        send.assert_not_called()


def test_signed_status_webhook_cannot_change_other_tenant_message():
    engine = _merchant_db()
    try:
        with Session(engine) as db:
            conv_a, _ = _setup_merchant(db, 201, 301, "3333333333")
            conv_b, _ = _setup_merchant(db, 202, 302, "4444444444")
            msg_a = Message(conversation_id=conv_a.id, sender="human", text="Alpha",
                            provider="whatsapp", external_message_id="wamid.shared",
                            delivery_status="sent")
            msg_b = Message(conversation_id=conv_b.id, sender="human", text="Beta",
                            provider="whatsapp", external_message_id="wamid.shared",
                            delivery_status="sent")
            db.add_all([msg_a, msg_b])
            db.commit()
            payload = {"entry": [{"changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": "3333333333"},
                    "statuses": [{"id": "wamid.shared", "status": "read"}],
                },
            }]}]}
            process_webhook_payload(db, payload)
            db.refresh(msg_a)
            db.refresh(msg_b)
            assert msg_a.delivery_status == "read"
            assert msg_b.delivery_status == "sent"
    finally:
        engine.dispose()


def test_app_level_webhook_verification_token_is_never_queried_in_db(monkeypatch):
    monkeypatch.setenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "shared-diaglob-test-token")
    request = SimpleNamespace(query_params={
        "hub.mode": "subscribe",
        "hub.verify_token": "shared-diaglob-test-token",
        "hub.challenge": "challenge-123",
    })
    db = MagicMock()
    assert whatsapp_verify_webhook(request=request, db=db).body == b"challenge-123"
    db.query.assert_not_called()
    request.query_params["hub.verify_token"] = "wrong-token"
    with pytest.raises(HTTPException) as exc:
        whatsapp_verify_webhook(request=request, db=db)
    assert exc.value.status_code == 403


def test_diagnostics_never_claim_live_without_provider_confirmation():
    engine = _merchant_db()
    try:
        with Session(engine) as db:
            _, conn = _setup_merchant(db, 401, 501, "5555555555")
            db.commit()
            with patch("app.services.whatsapp_diagnostics.decrypt_whatsapp_secret",
                       return_value="mock-token"), patch(
                "app.services.whatsapp_diagnostics._graph_get"
            ) as graph:
                graph.side_effect = [
                    {"data": [{"id": "5555555555", "verified_name": "Test"}]},
                    {"data": [{"id": "7777777777"}]},
                ]
                with patch.dict("os.environ", {"WHATSAPP_META_APP_ID": "7777777777"}):
                    result = diagnose_whatsapp(db, 401, 501)
                assert result["configured"] is True
                assert result["provider_verified"] is True
                assert result["waba_subscription_verified"] is True
                assert "mock-token" not in str(result)
                assert graph.call_count == 2
                graph.reset_mock()
                graph.side_effect = [
                    {"data": [{"id": "5555555555"}]},
                    {"data": []},
                ]
                with patch.dict("os.environ", {"WHATSAPP_META_APP_ID": "7777777777"}):
                    missing = diagnose_whatsapp(db, 401, 501)
                assert missing["waba_subscription_verified"] is False
                assert "WHATSAPP_APP_NOT_SUBSCRIBED" in missing["errors"]
            assert diagnose_whatsapp(db, 999, 501)["configured"] is False
    finally:
        engine.dispose()
