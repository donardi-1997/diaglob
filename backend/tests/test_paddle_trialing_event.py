"""Trial events must be recognized and must provision access through the
normal signature-verified webhook handler rather than unauthenticated state.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.paddle_webhooks import (
    SUBSCRIPTION_EVENTS,
    SUPPORTED_EVENTS,
    process_subscription_event,
)


def test_trialing_is_a_supported_subscription_event():
    assert "subscription.trialing" in SUBSCRIPTION_EVENTS
    assert "subscription.trialing" in SUPPORTED_EVENTS


def test_trialing_subscription_grants_verified_plan_without_money_charge():
    organization = SimpleNamespace(
        id=42,
        plan="none",
        pending_plan=None,
        pending_plan_effective_at=None,
        pending_billing_period_months=None,
        pending_plan_prepared_at=None,
        subscription_status=None,
        auto_renew_enabled=False,
        billing_last_event_id=None,
        billing_last_event_at=None,
    )
    db = MagicMock()
    result = process_subscription_event(
        organization=organization,
        event_id="evt_test_trialing",
        occurred_at=None,
        event_type="subscription.trialing",
        plan_key="starter",
        price_id="pri_test",
        billing_period_months=1,
        status="trialing",
        data={"status": "trialing"},
        db=db,
    )
    assert result["subscription_status"] == "trialing"
    assert result["plan"] == "starter"
    assert organization.auto_renew_enabled is True
    db.commit.assert_called_once()
