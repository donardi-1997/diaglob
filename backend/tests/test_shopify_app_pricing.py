"""Shopify App Pricing verification must never authorize charges by itself."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.services.shopify_app_pricing import (
    SHOPIFY_APP_PRICING_INTERVAL_TO_MONTHS,
    SHOPIFY_APP_STORE_PLANS,
    SHOPIFY_APP_STORE_TRIAL_DAYS,
    ShopifyAppPricingError,
    get_active_shopify_subscription,
    get_shopify_trial_evidence,
    is_trusted_partner_development_shop,
    resolve_verified_shopify_plan,
    ShopifySubscriptionSnapshot,
    resolve_trusted_shop_gid,
)


def test_shopify_app_pricing_exposes_only_monthly_and_annual_intervals():
    """Shopify App Pricing has no semestral billing interval."""
    assert SHOPIFY_APP_PRICING_INTERVAL_TO_MONTHS == {
        "EVERY_30_DAYS": 1,
        "ANNUAL": 12,
    }
    assert "EVERY_180_DAYS" not in SHOPIFY_APP_PRICING_INTERVAL_TO_MONTHS


def _env(monkeypatch):
    monkeypatch.setenv("SHOPIFY_PARTNER_ORG_ID", "5148778")
    monkeypatch.setenv("SHOPIFY_PARTNER_APP_GID", "gid://shopify/App/416524435457")
    monkeypatch.setenv("SHOPIFY_PARTNER_ACCESS_TOKEN", "test-credential")


def _client(payload, *, status=200, requests=None):
    def handler(request):
        if requests is not None:
            requests.append(request)
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_active_subscription_is_verified_by_partner_api(monkeypatch):
    _env(monkeypatch)
    requests = []
    payload = {
        "data": {
            "activeSubscription": {
                "shop": {"id": "gid://shopify/Shop/12345"},
                "billingPeriod": "EVERY_30_DAYS",
                "cancelAtEndOfCycle": False,
                "trialEndsAt": None,
                "currentBillingCycle": {
                    "startTime": "2026-10-01T00:00:00Z",
                    "endTime": "2026-11-01T00:00:00Z",
                },
                "items": [{"handle": "starter-plan", "description": "Starter", "price": {"__typename": "FlatRatePrice", "active": True, "currency": "USD", "amount": "19.00"}}],
            }
        }
    }
    with _client(payload, requests=requests) as client:
        snapshot = get_active_shopify_subscription(
            "gid://shopify/Shop/12345", http_client=client
        )
    assert snapshot.active is True
    assert snapshot.billing_period == "EVERY_30_DAYS"
    assert snapshot.item_handles == ("starter-plan",)
    assert snapshot.eligible_amounts == ("19.00",)
    assert snapshot.current_cycle_end == "2026-11-01T00:00:00Z"
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert str(request.url) == (
        "https://partners.shopify.com/5148778/api/2026-10/graphql.json"
    )
    assert request.headers["X-Shopify-Access-Token"] == "test-credential"
    assert "on FlatRatePrice { amount }" in json.loads(request.content)["query"]
    params = json.loads(request.content)["variables"]
    assert params == {
        "appId": "gid://shopify/App/416524435457",
        "shopId": "gid://shopify/Shop/12345",
    }


def _partner_billing_lifecycle_payload(**overrides):
    subscription = {
        "shop": {"id": "gid://shopify/Shop/12345"},
        "billingPeriod": "EVERY_30_DAYS",
        "cancelAtEndOfCycle": False,
        "items": [{
            "handle": "starter-plan",
            "price": {
                "__typename": "FlatRatePrice",
                "active": True, "currency": "USD", "amount": "19.00",
            },
        }],
    }
    subscription.update(overrides)
    return {"data": {"activeSubscription": subscription}}


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"cancelAtEndOfCycle": "false"}, "SHOPIFY_PARTNER_API_INVALID_RESPONSE"),
        ({"cancelAtEndOfCycle": 1}, "SHOPIFY_PARTNER_API_INVALID_RESPONSE"),
        ({"pendingUpdate": {"billingPeriod": "HOURLY", "items": [
            {"handle": "pro-plan"},
        ]}}, "SHOPIFY_PARTNER_API_INVALID_RESPONSE"),
        ({"pendingUpdate": {"billingPeriod": [], "items": [
            {"handle": "pro-plan"},
        ]}}, "SHOPIFY_PARTNER_API_INVALID_RESPONSE"),
        ({"pendingUpdate": {"billingPeriod": "ANNUAL", "items": [
            {"handle": ""},
        ]}}, "SHOPIFY_PARTNER_API_INVALID_RESPONSE"),
    ],
)
def test_partner_lifecycle_rejects_invalid_cancel_or_pending_update(
    monkeypatch, updates, expected,
):
    _env(monkeypatch)
    with _client(_partner_billing_lifecycle_payload(**updates)) as client:
        with pytest.raises(ShopifyAppPricingError, match=expected):
            get_active_shopify_subscription(
                "gid://shopify/Shop/12345", http_client=client,
            )


def test_partner_pending_upgrade_does_not_reassign_active_plan(monkeypatch):
    _env(monkeypatch)
    payload = _partner_billing_lifecycle_payload(
        pendingUpdate={
            "billingPeriod": "ANNUAL",
            "items": [{"handle": "pro-plan"}],
        },
    )
    with _client(payload) as client:
        snapshot = get_active_shopify_subscription(
            "gid://shopify/Shop/12345", http_client=client,
        )
    assert snapshot.active is True
    assert snapshot.has_pending_update is True
    assert snapshot.item_handles == ("starter-plan",)
    result = resolve_verified_shopify_plan(
        snapshot, handle_catalog={
            "starter-plan": {
                "plan": "starter",
                "prices": {"EVERY_30_DAYS": "19.00", "ANNUAL": "190.00"},
            },
            "pro-plan": {
                "plan": "pro",
                "prices": {"EVERY_30_DAYS": "99.00", "ANNUAL": "990.00"},
            },
        },
    )
    assert result.plan == "starter"
    assert result.billing_period_months == 1


def test_partner_scheduled_cancellation_is_explicit(monkeypatch):
    _env(monkeypatch)
    with _client(_partner_billing_lifecycle_payload(
        cancelAtEndOfCycle=True,
    )) as client:
        snapshot = get_active_shopify_subscription(
            "gid://shopify/Shop/12345", http_client=client,
        )
    assert snapshot.active is True
    assert snapshot.cancel_at_end_of_cycle is True


def test_missing_subscription_fails_closed_as_inactive(monkeypatch):
    _env(monkeypatch)
    with _client({"data": {"activeSubscription": None}}) as client:
        snapshot = get_active_shopify_subscription(
            "gid://shopify/Shop/9", http_client=client
        )
    assert snapshot.active is False
    assert snapshot.item_handles == ()


@pytest.mark.parametrize(
    "response,status",
    [
        ({"errors": [{"message": "not authorized"}]}, 200),
        ({"data": {}}, 200),
        ({"data": {"activeSubscription": {"items": "invalid"}}}, 200),
        ({"data": {"activeSubscription": None}}, 401),
        ({"data": {"activeSubscription": None}}, 429),
    ],
)
def test_errors_cannot_grant_entitlements(monkeypatch, response, status):
    _env(monkeypatch)
    with _client(response, status=status) as client:
        with pytest.raises(ShopifyAppPricingError):
            get_active_shopify_subscription(
                "gid://shopify/Shop/9", http_client=client
            )


def test_partner_api_requires_explicit_configuration(monkeypatch):
    monkeypatch.delenv("SHOPIFY_PARTNER_ORG_ID", raising=False)
    monkeypatch.delenv("SHOPIFY_PARTNER_APP_GID", raising=False)
    monkeypatch.delenv("SHOPIFY_PARTNER_ACCESS_TOKEN", raising=False)
    with pytest.raises(ShopifyAppPricingError, match="NOT_CONFIGURED"):
        get_active_shopify_subscription("gid://shopify/Shop/123")


@pytest.mark.parametrize(
    "shop_gid",
    ["", "fake.myshopify.com", "gid://shopify/Shop/1?x=1", "gid://shopify/App/1"],
)
def test_user_supplied_shop_domain_cannot_be_used_as_shop_gid(shop_gid, monkeypatch):
    _env(monkeypatch)
    with pytest.raises(ShopifyAppPricingError, match="INVALID_SHOP_GID"):
        get_active_shopify_subscription(shop_gid)


def test_paddle_registry_remains_default():
    from app.billing_providers.registry import registered_billing_providers
    from app.billing_providers.registry import get_billing_provider

    assert "paddle" in registered_billing_providers()
    assert get_billing_provider().name == "paddle"

def test_trusted_shop_gid_resolved_with_authenticated_store_token():
    connection = SimpleNamespace(
        provider="shopify",
        status="connected",
        external_store_url="some-store.myshopify.com",
        access_token_encrypted="encrypted-token",
    )
    with patch(
        "app.services.shopify_app_pricing.decrypt_shopify_secret",
        return_value="access-token",
    ), patch(
        "app.services.shopify_app_pricing.ShopifyGraphQLClient"
    ) as client:
        client.return_value.query.return_value = {
            "shop": {
                "id": "gid://shopify/Shop/123",
                "myshopifyDomain": "some-store.myshopify.com",
            }
        }
        gid = resolve_trusted_shop_gid(connection)
    assert gid == "gid://shopify/Shop/123"
    client.assert_called_once_with(
        shop_domain="some-store.myshopify.com",
        access_token="access-token",
    )


@pytest.mark.parametrize(
    "returned_shop",
    [
        {"id": "gid://shopify/Shop/123", "myshopifyDomain": "other.myshopify.com"},
        {"id": "not-a-gid", "myshopifyDomain": "some-store.myshopify.com"},
        {},
    ],
)
def test_shop_gid_rejects_mismatched_or_invalid_admin_identity(returned_shop):
    connection = SimpleNamespace(
        provider="shopify",
        status="connected",
        external_store_url="some-store.myshopify.com",
        access_token_encrypted="token",
    )
    with patch(
        "app.services.shopify_app_pricing.decrypt_shopify_secret",
        return_value="access-token",
    ), patch(
        "app.services.shopify_app_pricing.ShopifyGraphQLClient"
    ) as client:
        client.return_value.query.return_value = {"shop": returned_shop}
        with pytest.raises(ShopifyAppPricingError):
            resolve_trusted_shop_gid(connection)


def test_disconnected_shopify_connection_cannot_verify_subscription():
    connection = SimpleNamespace(
        provider="shopify",
        status="disconnected",
        external_store_url="some-store.myshopify.com",
        access_token_encrypted="token",
    )
    with pytest.raises(ShopifyAppPricingError, match="NOT_VERIFIED"):
        resolve_trusted_shop_gid(connection)


def test_verified_plan_rejects_untrusted_or_ambiguous_handles():
    valid = ShopifySubscriptionSnapshot(
        active=True,
        billing_period="EVERY_30_DAYS",
        item_handles=("real-starter-monthly",),
        eligible_handles=("real-starter-monthly",),
        eligible_amounts=("19.00",),
    )
    catalog = {
        "real-starter-monthly": {"plan": "starter", "interval": "EVERY_30_DAYS", "amount_usd": "19.00"}
    }
    result = resolve_verified_shopify_plan(valid, handle_catalog=catalog)
    assert result.plan == "starter"
    assert result.billing_period_months == 1

    with pytest.raises(ShopifyAppPricingError, match="UNKNOWN"):
        resolve_verified_shopify_plan(
            valid, handle_catalog={"other": {"plan": "starter", "interval": "EVERY_30_DAYS"}}
        )
    with pytest.raises(ShopifyAppPricingError, match="MISMATCH"):
        resolve_verified_shopify_plan(
            valid, handle_catalog={"real-starter-monthly": {"plan": "starter", "interval": "ANNUAL"}}
        )

    for handles, eligible in [
        (("real-starter-monthly", "extra-charge"), ("real-starter-monthly",)),
        (("real-starter-monthly",), ()),
        ((), ()),
    ]:
        with pytest.raises(ShopifyAppPricingError, match="UNRECOGNIZED"):
            resolve_verified_shopify_plan(
                ShopifySubscriptionSnapshot(
                    active=True,
                    billing_period="EVERY_30_DAYS",
                    item_handles=handles,
                    eligible_handles=eligible,
                ),
                handle_catalog=catalog,
            )


def test_inactive_plan_never_maps_to_entitlements():
    with pytest.raises(ShopifyAppPricingError, match="NO_ACTIVE"):
        resolve_verified_shopify_plan(
            ShopifySubscriptionSnapshot(active=False),
            handle_catalog={"starter": {"plan": "starter", "interval": "EVERY_30_DAYS"}},
        )


def test_environment_handle_catalog_fail_closed(monkeypatch):
    monkeypatch.delenv("SHOPIFY_APP_PRICING_HANDLES_JSON", raising=False)
    active = ShopifySubscriptionSnapshot(
        active=True,
        billing_period="ANNUAL",
        item_handles=("annual-starter",),
        eligible_handles=("annual-starter",),
        eligible_amounts=("190.00",),
    )
    with pytest.raises(ShopifyAppPricingError, match="NOT_CONFIGURED"):
        resolve_verified_shopify_plan(active)

    monkeypatch.setenv(
        "SHOPIFY_APP_PRICING_HANDLES_JSON",
        '{"annual-starter":{"plan":"starter","interval":"ANNUAL","amount_usd":"190.00"}}',
    )
    plan = resolve_verified_shopify_plan(active)
    assert (plan.plan, plan.billing_period_months) == ("starter", 12)


def test_subscription_response_shop_id_must_match_requested_shop(monkeypatch):
    _env(monkeypatch)
    payload = {
        "data": {
            "activeSubscription": {
                "shop": {"id": "gid://shopify/Shop/other"},
                "billingPeriod": "EVERY_30_DAYS",
                "currentBillingCycle": None,
                "items": [{"handle": "starter", "price": {"__typename": "FlatRatePrice", "active": True, "currency": "USD"}}],
            },
        }
    }
    with _client(payload) as client:
        with pytest.raises(ShopifyAppPricingError, match="SHOP_MISMATCH"):
            get_active_shopify_subscription(
                "gid://shopify/Shop/123", http_client=client
            )


@pytest.mark.parametrize("actual,approved", [
    ("0.00", "49.00"),
    ("0", "49.00"),
    ("0.00", "0.00"),
])
def test_dev_store_zero_charge_never_grants_commercial_entitlements(
    actual, approved,
):
    """A real no-charge development contract is not a paid merchant receipt."""
    snapshot = ShopifySubscriptionSnapshot(
        active=True,
        billing_period="EVERY_30_DAYS",
        item_handles=("growth-monthly",),
        eligible_handles=("growth-monthly",),
        eligible_amounts=(actual,),
    )
    catalog = {
        "growth-monthly": {
            "plan": "growth", "interval": "EVERY_30_DAYS",
            "amount_usd": approved,
        },
    }
    with pytest.raises(ShopifyAppPricingError) as exc:
        resolve_verified_shopify_plan(snapshot, handle_catalog=catalog)
    assert str(exc.value) in {
        "SHOPIFY_PLAN_PRICE_UNVERIFIED",
        "SHOPIFY_PLAN_PRICE_MISMATCH",
        "SHOPIFY_PLAN_CATALOG_INVALID",
    }


def test_one_shopify_plan_handle_can_verify_both_billing_periods():
    """One public plan can offer a monthly and yearly price under one handle."""
    catalog = {
        "growth-shared": {
            "plan": "growth",
            "prices": {"EVERY_30_DAYS": "49.00", "ANNUAL": "490.00"},
        }
    }
    for interval, amount, months in [
        ("EVERY_30_DAYS", "49.00", 1),
        ("ANNUAL", "490.00", 12),
    ]:
        subscription = ShopifySubscriptionSnapshot(
            active=True,
            billing_period=interval,
            item_handles=("growth-shared",),
            eligible_handles=("growth-shared",),
            eligible_amounts=(amount,),
        )
        matched = resolve_verified_shopify_plan(subscription, handle_catalog=catalog)
        assert (matched.plan, matched.billing_period_months) == ("growth", months)


@pytest.mark.parametrize("invalid_prices", [
    {},
    {"EVERY_30_DAYS": "0"},
    {"ANNUAL": 490.0},
    {"ANNUAL": "NaN"},
    {"EVERY_30_DAYS": "49.00", "WEEKLY": "10.00"},
])
def test_shared_handle_catalog_rejects_unapproved_prices(invalid_prices):
    snapshot = ShopifySubscriptionSnapshot(
        active=True, billing_period="EVERY_30_DAYS",
        item_handles=("growth-shared",), eligible_handles=("growth-shared",),
        eligible_amounts=("49.00",),
    )
    with pytest.raises(ShopifyAppPricingError, match="CATALOG_INVALID"):
        resolve_verified_shopify_plan(
            snapshot, handle_catalog={"growth-shared": {
                "plan": "growth", "prices": invalid_prices,
            }},
        )


def test_shared_handle_does_not_fallback_or_allow_price_mismatch():
    catalog = {"growth-shared": {
        "plan": "growth", "prices": {"EVERY_30_DAYS": "49.00"},
    }}
    annual = ShopifySubscriptionSnapshot(
        active=True, billing_period="ANNUAL",
        item_handles=("growth-shared",), eligible_handles=("growth-shared",),
        eligible_amounts=("490.00",),
    )
    with pytest.raises(ShopifyAppPricingError, match="INTERVAL_MISMATCH"):
        resolve_verified_shopify_plan(annual, handle_catalog=catalog)

    monthly_zero = ShopifySubscriptionSnapshot(
        active=True, billing_period="EVERY_30_DAYS",
        item_handles=("growth-shared",), eligible_handles=("growth-shared",),
        eligible_amounts=("0.00",),
    )
    with pytest.raises(ShopifyAppPricingError, match="PRICE_UNVERIFIED"):
        resolve_verified_shopify_plan(monthly_zero, handle_catalog=catalog)

    monthly_wrong = ShopifySubscriptionSnapshot(
        active=True, billing_period="EVERY_30_DAYS",
        item_handles=("growth-shared",), eligible_handles=("growth-shared",),
        eligible_amounts=("39.00",),
    )
    with pytest.raises(ShopifyAppPricingError, match="PRICE_MISMATCH"):
        resolve_verified_shopify_plan(monthly_wrong, handle_catalog=catalog)


def test_shared_handle_config_cannot_mix_legacy_and_new_price_keys():
    subscription = ShopifySubscriptionSnapshot(
        active=True, billing_period="EVERY_30_DAYS",
        item_handles=("growth-shared",), eligible_handles=("growth-shared",),
        eligible_amounts=("49.00",),
    )
    with pytest.raises(ShopifyAppPricingError, match="CATALOG_INVALID"):
        resolve_verified_shopify_plan(
            subscription,
            handle_catalog={"growth-shared": {
                "plan": "growth",
                "interval": "EVERY_30_DAYS",
                "amount_usd": "49.00",
                "prices": {"EVERY_30_DAYS": "49.00"},
            }},
        )


def test_shopify_app_store_review_contract_has_three_public_plans_and_three_day_trial():
    assert SHOPIFY_APP_STORE_PLANS == ("starter", "growth", "pro")
    assert SHOPIFY_APP_STORE_TRIAL_DAYS == 3
    assert set(SHOPIFY_APP_PRICING_INTERVAL_TO_MONTHS.values()) == {1, 12}


@pytest.mark.parametrize(
    "plan,handle,monthly,annual,interval,amount,months",
    [
        ("starter", "starter-review", "19.00", "190.00", "EVERY_30_DAYS", "19.00", 1),
        ("starter", "starter-review", "19.00", "190.00", "ANNUAL", "190.00", 12),
        ("growth", "growth-review", "49.00", "490.00", "EVERY_30_DAYS", "49.00", 1),
        ("growth", "growth-review", "49.00", "490.00", "ANNUAL", "490.00", 12),
        ("pro", "pro-review", "99.00", "990.00", "EVERY_30_DAYS", "99.00", 1),
        ("pro", "pro-review", "99.00", "990.00", "ANNUAL", "990.00", 12),
    ],
)
def test_each_shopify_public_plan_resolves_for_monthly_and_annual_review(
    plan, handle, monthly, annual, interval, amount, months,
):
    subscription = ShopifySubscriptionSnapshot(
        active=True,
        billing_period=interval,
        item_handles=(handle,),
        eligible_handles=(handle,),
        eligible_amounts=(amount,),
        trial_ends_at="2026-10-14T18:00:00Z",
    )
    catalog = {
        handle: {
            "plan": plan,
            "prices": {
                "EVERY_30_DAYS": monthly,
                "ANNUAL": annual,
            },
        },
    }

    resolved = resolve_verified_shopify_plan(
        subscription,
        handle_catalog=catalog,
    )

    assert resolved.plan == plan
    assert resolved.billing_period_months == months
    assert subscription.trial_ends_at == "2026-10-14T18:00:00Z"


def test_scale_is_not_a_shopify_app_store_public_plan():
    subscription = ShopifySubscriptionSnapshot(
        active=True,
        billing_period="EVERY_30_DAYS",
        item_handles=("scale-review",),
        eligible_handles=("scale-review",),
        eligible_amounts=("199.00",),
    )
    with pytest.raises(ShopifyAppPricingError, match="SHOPIFY_PLAN_CATALOG_INVALID"):
        resolve_verified_shopify_plan(
            subscription,
            handle_catalog={
                "scale-review": {
                    "plan": "scale",
                    "interval": "EVERY_30_DAYS",
                    "amount_usd": "199.00",
                },
            },
        )


def test_shopify_billing_capabilities_publish_review_contract(monkeypatch):
    from app.api.billing import shopify_billing_capabilities

    monkeypatch.setenv("SHOPIFY_APP_STORE_HANDLE", "diaglob-app")
    monkeypatch.delenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", raising=False)
    result = shopify_billing_capabilities(
        membership=SimpleNamespace(role="owner", organization_id=77),
    )

    assert result["shopify_hosted_pricing_configured"] is True
    assert result["verified_entitlement_apply_enabled"] is False
    assert result["paddle_checkout_available"] is False
    assert result["public_plans"] == ["starter", "growth", "pro"]
    assert result["trial_days"] == 3
    assert result["billing_period_months"] == [1, 12]


def test_zero_effective_price_maps_only_when_trusted_dev_store_was_confirmed():
    snapshot = ShopifySubscriptionSnapshot(
        active=True,
        billing_period="EVERY_30_DAYS",
        item_handles=("growth-monthly",),
        eligible_handles=("growth-monthly",),
        eligible_amounts=("0.00",),
    )
    catalog = {
        "growth-monthly": {
            "plan": "growth",
            "interval": "EVERY_30_DAYS",
            "amount_usd": "49.00",
        },
    }

    with pytest.raises(ShopifyAppPricingError, match="PRICE_UNVERIFIED"):
        resolve_verified_shopify_plan(snapshot, handle_catalog=catalog)

    resolved = resolve_verified_shopify_plan(
        snapshot,
        handle_catalog=catalog,
        allow_no_charge_testing=True,
    )
    assert resolved.plan == "growth"
    assert resolved.billing_period_months == 1


@pytest.mark.parametrize("partner_development", [True, False])
def test_development_shop_status_comes_from_authenticated_admin_identity(
    partner_development,
):
    connection = SimpleNamespace(
        provider="shopify",
        status="connected",
        external_store_url="some-store.myshopify.com",
        access_token_encrypted="encrypted-token",
    )
    with patch(
        "app.services.shopify_app_pricing.decrypt_shopify_secret",
        return_value="access-token",
    ), patch(
        "app.services.shopify_app_pricing.ShopifyGraphQLClient"
    ) as client:
        client.return_value.query.return_value = {
            "shop": {
                "id": "gid://shopify/Shop/123",
                "myshopifyDomain": "some-store.myshopify.com",
                "plan": {"partnerDevelopment": partner_development},
            }
        }
        result = is_trusted_partner_development_shop(
            connection,
            expected_shop_gid="gid://shopify/Shop/123",
        )

    assert result is partner_development
    client.assert_called_once_with(
        shop_domain="some-store.myshopify.com",
        access_token="access-token",
    )


def test_development_shop_status_rejects_gid_or_domain_mismatch():
    connection = SimpleNamespace(
        provider="shopify",
        status="connected",
        external_store_url="some-store.myshopify.com",
        access_token_encrypted="encrypted-token",
    )
    for returned_shop in (
        {
            "id": "gid://shopify/Shop/999",
            "myshopifyDomain": "some-store.myshopify.com",
            "plan": {"partnerDevelopment": True},
        },
        {
            "id": "gid://shopify/Shop/123",
            "myshopifyDomain": "other.myshopify.com",
            "plan": {"partnerDevelopment": True},
        },
        {
            "id": "gid://shopify/Shop/123",
            "myshopifyDomain": "some-store.myshopify.com",
            "plan": {"partnerDevelopment": "true"},
        },
    ):
        with patch(
            "app.services.shopify_app_pricing.decrypt_shopify_secret",
            return_value="access-token",
        ), patch(
            "app.services.shopify_app_pricing.ShopifyGraphQLClient"
        ) as client:
            client.return_value.query.return_value = {"shop": returned_shop}
            with pytest.raises(ShopifyAppPricingError, match="IDENTITY_INVALID"):
                is_trusted_partner_development_shop(
                    connection,
                    expected_shop_gid="gid://shopify/Shop/123",
                )


def test_trial_evidence_reads_three_day_setting_for_current_partner_plan(monkeypatch):
    _env(monkeypatch)
    payload = {
        "data": {
            "events": {
                "edges": [
                    {
                        "node": {
                            "eventType": "SUBSCRIPTION_UPDATED",
                            "occurredAt": "2026-10-11T18:30:00Z",
                            "shop": {"id": "gid://shopify/Shop/123"},
                            "plan": {
                                "handle": "growth-review",
                                "billingPeriod": "EVERY_30_DAYS",
                                "trialDays": 3,
                                "trialDaysRemaining": 2,
                            },
                        }
                    }
                ]
            }
        }
    }
    with _client(payload) as client:
        evidence = get_shopify_trial_evidence(
            "gid://shopify/Shop/123",
            current_handle="growth-review",
            current_billing_period="EVERY_30_DAYS",
            http_client=client,
        )

    assert evidence.trial_days == 3
    assert evidence.trial_days_remaining == 2
    assert evidence.billing_period == "EVERY_30_DAYS"
    assert evidence.event_type == "SUBSCRIPTION_UPDATED"


def test_trial_evidence_ignores_other_plan_events_and_fails_if_current_missing(monkeypatch):
    _env(monkeypatch)
    payload = {
        "data": {
            "events": {
                "edges": [
                    {
                        "node": {
                            "eventType": "SUBSCRIPTION_CREATED",
                            "occurredAt": "2026-10-10T18:30:00Z",
                            "shop": {"id": "gid://shopify/Shop/123"},
                            "plan": {
                                "handle": "starter-review",
                                "billingPeriod": "EVERY_30_DAYS",
                                "trialDays": 3,
                                "trialDaysRemaining": 3,
                            },
                        }
                    }
                ]
            }
        }
    }
    with _client(payload) as client:
        with pytest.raises(ShopifyAppPricingError, match="TRIAL_EVIDENCE_NOT_FOUND"):
            get_shopify_trial_evidence(
                "gid://shopify/Shop/123",
                current_handle="growth-review",
                current_billing_period="EVERY_30_DAYS",
                http_client=client,
            )


@pytest.mark.parametrize(
    "trial_days,remaining",
    [(True, 1), (3, True), (-1, 0), (3, -1), (3, 4)],
)
def test_trial_evidence_rejects_invalid_partner_values(
    monkeypatch, trial_days, remaining,
):
    _env(monkeypatch)
    payload = {
        "data": {
            "events": {
                "edges": [
                    {
                        "node": {
                            "eventType": "SUBSCRIPTION_CREATED",
                            "occurredAt": "2026-10-11T18:30:00Z",
                            "shop": {"id": "gid://shopify/Shop/123"},
                            "plan": {
                                "handle": "growth-review",
                                "billingPeriod": "EVERY_30_DAYS",
                                "trialDays": trial_days,
                                "trialDaysRemaining": remaining,
                            },
                        }
                    }
                ]
            }
        }
    }
    with _client(payload) as client:
        with pytest.raises(ShopifyAppPricingError, match="TRIAL_EVIDENCE_INVALID"):
            get_shopify_trial_evidence(
                "gid://shopify/Shop/123",
                current_handle="growth-review",
                current_billing_period="EVERY_30_DAYS",
                http_client=client,
            )
