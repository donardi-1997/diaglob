from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.billing import add_billing_months
from app.paddle_client import preview_subscription_update, update_subscription
from app.services.billing_service import (
    UpgradeNotAllowedError,
    _build_upgrade_next_billed_at,
    execute_upgrade,
    preview_upgrade_paddle,
    validate_plan_upgrade,
)


def _http_response(data=None):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"data": data or {}}
    return response


def test_add_billing_months_clamps_end_of_month():
    assert add_billing_months(datetime(2026, 1, 31, 12), 1) == datetime(2026, 2, 28, 12)
    assert add_billing_months(datetime(2028, 1, 31, 12), 1) == datetime(2028, 2, 29, 12)


def test_upgrade_anchor_starts_new_calendar_cycle():
    value = _build_upgrade_next_billed_at(
        3,
        datetime(2026, 9, 10, 3, 15, 42, 123456),
    )
    assert value == "2026-12-10T03:15:42Z"


def test_preview_client_serializes_new_billing_anchor(monkeypatch):
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


def test_apply_client_serializes_new_billing_anchor(monkeypatch):
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


def test_preview_upgrade_passes_restarted_cycle_to_paddle(monkeypatch):
    monkeypatch.setenv("PADDLE_API_KEY", "test_key")
    organization = SimpleNamespace(
        id=7,
        billing_subscription_id="sub_123",
        billing_period_months=1,
    )
    paddle_preview = {
        "immediate_transaction": {
            "details": {
                "totals": {
                    "total": "3000",
                    "subtotal": "3000",
                    "tax": "0",
                    "currency_code": "USD",
                },
                "line_items": [],
            }
        },
        "next_billed_at": "2026-10-10T03:15:42Z",
    }

    with patch(
        "app.services.billing_service.get_paddle_price_id",
        return_value="pri_growth",
    ), patch(
        "app.services.billing_service._build_upgrade_next_billed_at",
        return_value="2026-10-10T03:15:42Z",
    ), patch(
        "app.services.billing_service.preview_subscription_update",
        return_value=paddle_preview,
    ) as preview:
        result = preview_upgrade_paddle(organization, "growth")

    assert result is not None
    assert preview.call_args.kwargs["next_billed_at"] == "2026-10-10T03:15:42Z"


def test_preview_upgrade_prefers_paddle_update_summary(monkeypatch):
    monkeypatch.setenv("PADDLE_API_KEY", "test_key")
    organization = SimpleNamespace(
        id=7,
        billing_subscription_id="sub_123",
        billing_period_months=1,
    )
    paddle_preview = {
        "immediate_transaction": {
            "details": {
                "totals": {
                    "total": "9999",
                    "subtotal": "9999",
                    "tax": "0",
                    "currency_code": "USD",
                },
                "line_items": [
                    {"totals": {"total": "9999"}},
                ],
            }
        },
        "update_summary": {
            "credit": {
                "amount": "-1200",
                "currency_code": "USD",
            },
            "charge": {
                "amount": "4900",
                "currency_code": "USD",
            },
            "result": {
                "action": "charge",
                "amount": "3700",
                "currency_code": "USD",
            },
        },
        "next_billed_at": "2026-10-10T03:15:42Z",
    }

    with patch(
        "app.services.billing_service.get_paddle_price_id",
        return_value="pri_growth",
    ), patch(
        "app.services.billing_service._build_upgrade_next_billed_at",
        return_value="2026-10-10T03:15:42Z",
    ), patch(
        "app.services.billing_service.preview_subscription_update",
        return_value=paddle_preview,
    ):
        result = preview_upgrade_paddle(organization, "growth")

    assert result is not None
    assert result["amount_due"] == "3700"
    assert result["update_summary"]["credit"]["amount"] == "1200"
    assert result["update_summary"]["charge"]["amount"] == "4900"
    assert result["update_summary"]["result"]["amount"] == "3700"


def test_validate_plan_upgrade_rejects_trialing_proration():
    organization = SimpleNamespace(
        id=7,
        plan="starter",
        subscription_status="trialing",
    )

    with pytest.raises(UpgradeNotAllowedError, match="suscripción debe estar activa"):
        validate_plan_upgrade(organization, "growth")


def test_execute_upgrade_uses_same_restarted_cycle_contract():
    organization = SimpleNamespace(
        id=7,
        plan="starter",
        billing_subscription_id="sub_123",
        billing_period_months=1,
        billing_price_id="pri_starter",
        pending_plan=None,
        pending_billing_period_months=None,
        pending_plan_effective_at=None,
        pending_plan_prepared_at=None,
    )
    db = MagicMock()

    with patch(
        "app.services.billing_service.get_paddle_price_id",
        return_value="pri_growth",
    ), patch(
        "app.services.billing_service._build_upgrade_next_billed_at",
        return_value="2026-10-10T03:15:42Z",
    ), patch(
        "app.services.billing_service.update_subscription",
        return_value={
            "status": "active",
            "next_billed_at": "2026-10-10T03:15:42Z",
        },
    ) as update, patch(
        "app.services.billing_service.get_subscription_price_id",
        return_value="pri_growth",
    ), patch(
        "app.services.billing_service.get_plan_from_price_id",
        return_value="growth",
    ), patch(
        "app.services.billing_service.get_billing_period_from_price_id",
        return_value=1,
    ):
        result = execute_upgrade(organization, "growth", db)

    assert update.call_args.kwargs["next_billed_at"] == "2026-10-10T03:15:42Z"
    assert result["next_billed_at"] == "2026-10-10T03:15:42Z"
