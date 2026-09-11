from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.billing import add_billing_months, calculate_local_proration
from app.paddle_client import preview_subscription_update, update_subscription
from app.services.billing_service import (
    UpgradeNotAllowedError,
    execute_upgrade,
    preview_upgrade_provider,
    validate_plan_upgrade,
)


def _http_response(data=None):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"data": data or {}}
    return response


def _provider() -> MagicMock:
    provider = MagicMock()
    provider.name = "paddle"
    provider.is_configured.return_value = True
    provider.get_price_id.return_value = "pri_growth"
    provider.get_subscription_price_id.return_value = "pri_growth"
    provider.get_plan_from_price_id.return_value = "growth"
    provider.get_billing_period_from_price_id.return_value = 1
    return provider


def test_add_billing_months_clamps_end_of_month():
    assert add_billing_months(datetime(2026, 1, 31, 12), 1) == datetime(2026, 2, 28, 12)
    assert add_billing_months(datetime(2028, 1, 31, 12), 1) == datetime(2028, 2, 29, 12)


def test_local_proration_charges_only_remaining_plan_difference():
    period_start = datetime(2026, 8, 1, 0, 0, 0)
    period_end = datetime(2026, 9, 1, 0, 0, 0)
    now = datetime(2026, 8, 16, 12, 0, 0)

    result = calculate_local_proration(
        current_plan="starter",
        target_plan="growth",
        billing_period_months=1,
        current_period_start=period_start,
        current_period_end=period_end,
        now=now,
    )

    assert Decimal(result["credit"]) == Decimal("9.50")
    assert Decimal(result["charge"]) == Decimal("24.50")
    assert Decimal(result["amount_due_now"]) == Decimal("15.00")
    assert Decimal(result["net_proration_amount"]) == Decimal("15.00")


def test_local_proration_keeps_current_period_end_as_next_billing_date():
    period_start = datetime(2026, 8, 1, 0, 0, 0)
    period_end = datetime(2026, 9, 1, 0, 0, 0)

    result = calculate_local_proration(
        current_plan="starter",
        target_plan="growth",
        billing_period_months=1,
        current_period_start=period_start,
        current_period_end=period_end,
        now=datetime(2026, 8, 16, 12, 0, 0),
    )

    assert result["next_billed_at"] == period_end.isoformat()


def test_preview_client_serializes_new_billing_anchor_when_explicit(monkeypatch):
    monkeypatch.setenv("PADDLE_API_KEY", "test_key")
    response = _http_response()

    with patch("app.paddle_client.httpx.patch", return_value=response) as request:
        preview_subscription_update(
            "sub_123",
            [{"price_id": "pri_growth", "quantity": 1}],
            "prorated_immediately",
            next_billed_at="2026-10-10T03:15:42Z",
        )

    body = request.call_args.kwargs["json"]
    assert body["proration_billing_mode"] == "prorated_immediately"
    assert body["next_billed_at"] == "2026-10-10T03:15:42Z"


def test_apply_client_serializes_new_billing_anchor_when_explicit(monkeypatch):
    monkeypatch.setenv("PADDLE_API_KEY", "test_key")
    response = _http_response()

    with patch("app.paddle_client.httpx.patch", return_value=response) as request:
        update_subscription(
            "sub_123",
            [{"price_id": "pri_growth", "quantity": 1}],
            "prorated_immediately",
            custom_data={"plan": "growth"},
            next_billed_at="2026-10-10T03:15:42Z",
        )

    body = request.call_args.kwargs["json"]
    assert body["proration_billing_mode"] == "prorated_immediately"
    assert body["next_billed_at"] == "2026-10-10T03:15:42Z"


def test_preview_upgrade_does_not_override_provider_billing_anchor():
    organization = SimpleNamespace(
        id=7,
        billing_provider="paddle",
        billing_subscription_id="sub_123",
        billing_period_months=1,
    )
    provider = _provider()
    provider.preview_subscription_update.return_value = {
        "immediate_transaction": {
            "details": {
                "totals": {
                    "total": "1500",
                    "subtotal": "1500",
                    "tax": "0",
                    "currency_code": "USD",
                },
                "line_items": [],
            }
        },
        "next_billed_at": "2026-09-01T00:00:00Z",
    }

    with patch(
        "app.services.billing_service._provider_for",
        return_value=provider,
    ):
        result = preview_upgrade_provider(organization, "growth")

    assert result is not None
    kwargs = provider.preview_subscription_update.call_args.kwargs
    assert "next_billed_at" not in kwargs
    assert result["next_billed_at"] == "2026-09-01T00:00:00Z"
    assert result["billing_provider"] == "paddle"


def test_preview_upgrade_prefers_provider_update_summary():
    organization = SimpleNamespace(
        id=7,
        billing_provider="paddle",
        billing_subscription_id="sub_123",
        billing_period_months=1,
    )
    provider = _provider()
    provider.preview_subscription_update.return_value = {
        "immediate_transaction": {
            "details": {
                "totals": {
                    "total": "9999",
                    "subtotal": "9999",
                    "tax": "0",
                    "currency_code": "USD",
                },
                "line_items": [{"totals": {"total": "9999"}}],
            }
        },
        "update_summary": {
            "credit": {"amount": "-950", "currency_code": "USD"},
            "charge": {"amount": "2450", "currency_code": "USD"},
            "result": {
                "action": "charge",
                "amount": "1500",
                "currency_code": "USD",
            },
        },
        "next_billed_at": "2026-09-01T00:00:00Z",
    }

    with patch(
        "app.services.billing_service._provider_for",
        return_value=provider,
    ):
        result = preview_upgrade_provider(organization, "growth")

    assert result is not None
    assert result["amount_due"] == "1500"
    assert result["update_summary"]["credit"]["amount"] == "950"
    assert result["update_summary"]["charge"]["amount"] == "2450"
    assert result["update_summary"]["result"]["amount"] == "1500"


def test_validate_plan_upgrade_rejects_trialing_proration():
    organization = SimpleNamespace(
        id=7,
        plan="starter",
        subscription_status="trialing",
    )

    with pytest.raises(UpgradeNotAllowedError, match="suscripción debe estar activa"):
        validate_plan_upgrade(organization, "growth")


def test_execute_upgrade_does_not_override_provider_billing_anchor():
    organization = SimpleNamespace(
        id=7,
        plan="starter",
        billing_provider=None,
        billing_subscription_id="sub_123",
        billing_period_months=1,
        billing_price_id="pri_starter",
        pending_plan=None,
        pending_billing_period_months=None,
        pending_plan_effective_at=None,
        pending_plan_prepared_at=None,
    )
    provider = _provider()
    provider.update_subscription.return_value = {
        "status": "active",
        "next_billed_at": "2026-09-01T00:00:00Z",
    }
    db = MagicMock()

    with patch(
        "app.services.billing_service._provider_for",
        return_value=provider,
    ):
        result = execute_upgrade(organization, "growth", db)

    kwargs = provider.update_subscription.call_args.kwargs
    assert "next_billed_at" not in kwargs
    assert result["next_billed_at"] == "2026-09-01T00:00:00Z"
    assert result["billing_provider"] == "paddle"
    assert organization.billing_provider == "paddle"
