"""Regression tests: Shopify App Store organizations never use Paddle billing."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.paddle_fulfillment import dispatch_verified_notification
from app.api.billing import (
    BillingCheckoutRequest,
    _reject_shopify_managed_billing,
    create_billing_checkout,
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


@pytest.mark.parametrize("provider", [None, "paddle", "PADDLE"])
def test_shopify_install_origin_never_falls_back_to_external_checkout(provider):
    organization = SimpleNamespace(
        billing_provider=provider,
        billing_onboarding_channel="shopify_install",
        subscription_status="trialing",
    )
    membership = SimpleNamespace(role="owner", organization=organization)
    with pytest.raises(HTTPException) as exc:
        create_billing_checkout(
            BillingCheckoutRequest(plan="starter", billing_period_months=1),
            membership=membership,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "SHOPIFY_INSTALL_BILLING_PENDING"


def test_direct_signup_with_shopify_store_connection_keeps_paddle_channel():
    _reject_shopify_managed_billing(SimpleNamespace(
        billing_provider="paddle",
        billing_onboarding_channel="direct",
    ))


def _dispatch_for_shopify_org(organization, event):
    """Verified events may be mirrored but must never mutate Shopify entitlements."""
    db = MagicMock()
    db.get.return_value = None
    db.query.return_value.filter.return_value.first.return_value = organization
    with patch(
        "app.services.paddle_fulfillment._sync_subscription_event",
        return_value=(SimpleNamespace(subscription_id=event["data"]["id"]), True),
    ), patch(
        "app.services.paddle_fulfillment.process_subscription_event"
    ) as mutate, patch(
        "app.services.paddle_fulfillment.update_billing_fields"
    ) as update:
        result = dispatch_verified_notification(event, db)
    mutate.assert_not_called()
    update.assert_not_called()
    db.commit.assert_called_once()
    return result


def test_signed_paddle_event_cannot_overwrite_shopify_entitlements():
    event = {
        "event_id": "evt_shopify_guard",
        "event_type": "subscription.created",
        "data": {"id": "sub_123", "customer_id": "ctm_123"},
    }
    result = _dispatch_for_shopify_org(
        SimpleNamespace(billing_provider="shopify", billing_onboarding_channel=None),
        event,
    )
    assert result["ignored"] is True
    assert result["reason"] == "unbound_or_stale_subscription"


@pytest.mark.parametrize("provider_name", [None, "paddle"])
def test_signed_paddle_event_ignored_for_shopify_origin_even_if_provider_stale(
    provider_name,
):
    event = {
        "event_id": "evt_stale_shopify_origin",
        "event_type": "subscription.created",
        "data": {"id": "sub_other", "customer_id": "ctm_other"},
    }
    result = _dispatch_for_shopify_org(
        SimpleNamespace(
            billing_provider=provider_name,
            billing_onboarding_channel="shopify_install",
        ),
        event,
    )
    assert result["ignored"] is True
    assert result["reason"] == "unbound_or_stale_subscription"


def test_internal_downgrade_worker_skips_shopify_organizations():
    from app.services.billing_service import process_pending_downgrades

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(id=42, billing_provider="shopify")
    ]
    result = process_pending_downgrades(db)
    assert result == [{"organization_id": 42, "status": "skipped_shopify_managed"}]
    db.commit.assert_not_called()
