"""Public direct-checkout cadence is monthly or annual only.

The backend price matrix does not contain quarterly or semiannual periods.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import billing as billing_api
from app.services import billing_service


@pytest.mark.parametrize("months", [0, 2, 3, 6])
def test_public_checkout_rejects_unsupported_period_before_price_lookup(
    monkeypatch, months,
):
    org = SimpleNamespace(
        billing_subscription_id=None,
        subscription_status="none",
        billing_provider="paddle",
        billing_onboarding_channel="direct",
    )
    membership = SimpleNamespace(role="owner", organization=org)
    monkeypatch.setattr(
        billing_api, "_reject_shopify_managed_billing", lambda _org: None
    )

    def unexpected(*args, **kwargs):
        pytest.fail("unsupported periods must not contact a billing provider")

    monkeypatch.setattr(billing_api, "get_billing_price_id", unexpected)
    monkeypatch.setattr(billing_api, "create_checkout", unexpected)

    with pytest.raises(HTTPException) as exc:
        billing_api.create_billing_checkout(
            billing_api.BillingCheckoutRequest(
                plan="starter", billing_period_months=months,
            ),
            membership=membership,
        )
    assert exc.value.status_code == 400


@pytest.mark.parametrize("months", [1, 12])
def test_public_checkout_allows_configured_monthly_annual(monkeypatch, months):
    org = SimpleNamespace(
        billing_subscription_id=None,
        subscription_status="none",
        billing_provider="paddle",
        billing_onboarding_channel="direct",
    )
    membership = SimpleNamespace(role="owner", organization=org)
    monkeypatch.setattr(
        billing_api, "_reject_shopify_managed_billing", lambda _org: None
    )
    looked_up = []
    monkeypatch.setattr(
        billing_api, "get_billing_price_id",
        lambda plan, period, provider: looked_up.append((plan, period, provider)),
    )
    monkeypatch.setattr(
        billing_api, "create_checkout",
        lambda _org, plan, period: {"plan": plan, "period": period},
    )

    result = billing_api.create_billing_checkout(
        billing_api.BillingCheckoutRequest(
            plan="growth", billing_period_months=months,
        ),
        membership=membership,
    )
    assert result == {"plan": "growth", "period": months}
    assert looked_up == [("growth", months, "paddle")]


@pytest.mark.parametrize("months", [3, 6])
def test_service_cannot_create_discontinued_cadence_checkout(months):
    with pytest.raises(billing_service.InvalidBillingPlanError):
        billing_service.create_checkout(
            SimpleNamespace(), "starter", months,
        )
