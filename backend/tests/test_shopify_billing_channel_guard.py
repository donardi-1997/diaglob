"""Regression tests: Shopify App Store organizations never use Paddle billing."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.billing import (
    BillingCheckoutRequest,
    _reject_shopify_managed_billing,
    create_billing_checkout,
    paddle_billing_webhook,
)


def test_shopify_channel_rejected_before_checkout_transport():
    organization = SimpleNamespace(
        billing_provider="shopify", billing_subscription_id=None,
        subscription_status="trialing",
    )
    membership = SimpleNamespace(role="owner", organization=organization)
    with pytest.raises(HTTPException) as exc:
        create_billing_checkout(
            BillingCheckoutRequest(plan="starter", billing_period_months=1),
            membership=membership,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SHOPIFY_MANAGED_BILLING"


def test_legacy_paddle_channel_is_not_blocked():
    _reject_shopify_managed_billing(SimpleNamespace(billing_provider=None))
    _reject_shopify_managed_billing(SimpleNamespace(billing_provider="paddle"))


def test_signed_paddle_event_cannot_overwrite_shopify_entitlements():
    payload = {
        "event_id": "evt_shopify_guard",
        "event_type": "subscription.created",
        "data": {"id": "sub_123", "customer_id": "ctm_123"},
    }
    body = json.dumps(payload).encode()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request = Request(
        {
            "type": "http", "method": "POST", "path": "/api/billing/webhook",
            "headers": [(b"paddle-signature", b"synthetic-signature")],
        },
        receive=receive,
    )
    provider = SimpleNamespace(
        webhook_signature_header="Paddle-Signature",
        verify_webhook=lambda raw, signature: None,
    )
    organization = SimpleNamespace(billing_provider="shopify")
    with patch("app.api.billing.get_billing_provider", return_value=provider), patch(
        "app.api.billing.resolve_organization", return_value=organization
    ), patch("app.api.billing.process_subscription_event") as mutate:
        response = asyncio.run(paddle_billing_webhook(request=request, db=None))
    assert response["ignored"] is True
    assert response["reason"] == "shopify_managed_billing"
    mutate.assert_not_called()


def test_internal_downgrade_worker_skips_shopify_organizations():
    from app.services.billing_service import process_pending_downgrades

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id=42, billing_provider="shopify")
    ]
    result = process_pending_downgrades(db)
    assert result == [{"organization_id": 42, "status": "skipped_shopify_managed"}]
    db.commit.assert_not_called()
