from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import billing as billing_api
from app.services import paddle_checkout


def test_country_header_is_normalized_and_unknown_sentinel_is_ignored():
    assert paddle_checkout.paddle_country_code(
        {"x-vercel-ip-country": "co"}, trusted_header="x-vercel-ip-country",
    ) == "CO"
    assert paddle_checkout.paddle_country_code(
        {"cloudfront-viewer-country": "GB"},
        trusted_header="cloudfront-viewer-country",
    ) == "GB"
    assert paddle_checkout.paddle_country_code(
        {"cf-ipcountry": "XX"}, trusted_header="cf-ipcountry",
    ) is None
    assert paddle_checkout.paddle_country_code(
        {"x-vercel-ip-country": "OTHERS"},
        trusted_header="x-vercel-ip-country",
    ) is None
    assert paddle_checkout.paddle_country_code(
        {"x-vercel-ip-country": "CO"},
    ) is None
    assert paddle_checkout.paddle_country_code({}) is None


def test_checkout_metadata_is_signed_and_bound_to_plan_price_and_organization():
    metadata = paddle_checkout.create_signed_checkout_custom_data(
        organization_id=42,
        plan="scale",
        billing_period_months=12,
        price_id="pri_01m50h6r57qvj1pr80czvjnev4",
        secret="webhook-secret-for-test",
    )
    assert metadata["organization_id"] == "42"
    assert metadata["plan"] == "scale"
    assert metadata["billing_period_months"] == 12
    assert metadata["price_id"] == "pri_01m50h6r57qvj1pr80czvjnev4"
    assert paddle_checkout.verify_signed_checkout_custom_data(
        metadata,
        actual_price_id="pri_01m50h6r57qvj1pr80czvjnev4",
        expected_price_id="pri_01m50h6r57qvj1pr80czvjnev4",
        secret="webhook-secret-for-test",
    )

    tampered = {**metadata, "organization_id": "43"}
    assert not paddle_checkout.verify_signed_checkout_custom_data(
        tampered,
        actual_price_id="pri_01m50h6r57qvj1pr80czvjnev4",
        expected_price_id="pri_01m50h6r57qvj1pr80czvjnev4",
        secret="webhook-secret-for-test",
    )
    assert not paddle_checkout.verify_signed_checkout_custom_data(
        metadata,
        actual_price_id="pri_another_price",
        expected_price_id="pri_01m50h6r57qvj1pr80czvjnev4",
        secret="webhook-secret-for-test",
    )
    assert not paddle_checkout.verify_signed_checkout_custom_data(
        metadata,
        actual_price_id="pri_01m50h6r57qvj1pr80czvjnev4",
        expected_price_id="pri_01m50h6r57qvj1pr80czvjnev4",
        secret="wrong-secret",
    )


@pytest.mark.parametrize("plan,period", [("unknown", 1), ("starter", 3)])
def test_checkout_metadata_rejects_invalid_plans_and_periods(plan, period):
    with pytest.raises(ValueError):
        paddle_checkout.create_signed_checkout_custom_data(
            organization_id=42,
            plan=plan,
            billing_period_months=period,
            price_id="pri_01m50gxt8wr6cqgndwk271zbs2",
            secret="webhook-secret-for-test",
        )


def test_paddle_catalog_returns_all_existing_price_ids_and_server_country(monkeypatch):
    expected = {
        "starter": {"month": "starter-month", "year": "starter-year"},
        "growth": {"month": "growth-month", "year": "growth-year"},
        "pro": {"month": "pro-month", "year": "pro-year"},
        "scale": {"month": "scale-month", "year": "scale-year"},
    }
    monkeypatch.setattr(
        billing_api,
        "get_billing_price_id",
        lambda plan, period, provider: expected[plan]["month" if period == 1 else "year"],
    )
    membership = SimpleNamespace(
        role="owner",
        organization=SimpleNamespace(
            billing_provider="paddle", billing_onboarding_channel="direct",
        ),
    )
    request = SimpleNamespace(headers={"x-vercel-ip-country": "co"})
    monkeypatch.setenv("PADDLE_TRUSTED_COUNTRY_HEADER", "x-vercel-ip-country")

    result = billing_api.get_paddle_checkout_catalog(request, membership)

    assert result["price_ids"] == expected
    assert result["country_code"] == "CO"
    assert result["trial_days"] == 3


def test_shopify_managed_organization_cannot_fetch_paddle_checkout_catalog(monkeypatch):
    membership = SimpleNamespace(
        role="owner",
        organization=SimpleNamespace(
            billing_provider="shopify", billing_onboarding_channel="shopify_install",
        ),
    )
    monkeypatch.setattr(
        billing_api,
        "get_billing_price_id",
        lambda *args: pytest.fail("Shopify organizations must never resolve Paddle prices"),
    )

    with pytest.raises(HTTPException) as exc:
        billing_api.get_paddle_checkout_catalog(
            SimpleNamespace(headers={}), membership,
        )

    assert exc.value.status_code == 409


def test_paddle_checkout_intent_is_server_signed_and_rejects_active_subscriptions(
    monkeypatch,
):
    price_id = "pri_01m50h6r57qvj1pr80czvjnev4"
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", "webhook-secret-for-test")
    monkeypatch.setattr(
        billing_api, "get_billing_price_id",
        lambda plan, period, provider: price_id,
    )
    org = SimpleNamespace(
        id=42,
        billing_provider="paddle",
        billing_onboarding_channel="direct",
        billing_subscription_id=None,
        subscription_status="none",
    )
    membership = SimpleNamespace(role="owner", organization=org)

    result = billing_api.create_paddle_checkout_intent(
        billing_api.PaddleCheckoutIntentRequest(
            plan="scale", billing_period_months=12,
        ),
        membership,
    )

    assert result["price_id"] == price_id
    assert paddle_checkout.verify_signed_checkout_custom_data(
        result["custom_data"],
        actual_price_id=price_id,
        expected_price_id=price_id,
        secret="webhook-secret-for-test",
    )

    org.billing_subscription_id = "sub_existing"
    org.subscription_status = "active"
    with pytest.raises(HTTPException) as exc:
        billing_api.create_paddle_checkout_intent(
            billing_api.PaddleCheckoutIntentRequest(
                plan="scale", billing_period_months=12,
            ),
            membership,
        )
    assert exc.value.status_code == 409
