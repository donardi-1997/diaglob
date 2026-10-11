"""Partner API price guard — no billing writes, credentials or customer data."""
import httpx
import pytest

from app.services.shopify_app_pricing import (
    ShopifyAppPricingError,
    ShopifySubscriptionSnapshot,
    get_active_shopify_subscription,
    resolve_verified_shopify_plan,
)


APPROVED_CATALOG = {
    "shopify-real-handle": {
        "plan": "starter",
        "interval": "EVERY_30_DAYS",
        "amount_usd": "19.00",  # Synthetic example; not a production approval.
    }
}


def _snapshot(*, amount="19.00", handles=("shopify-real-handle",)):
    return ShopifySubscriptionSnapshot(
        active=True,
        billing_period="EVERY_30_DAYS",
        item_handles=handles,
        eligible_handles=handles,
        eligible_amounts=(amount,),
    )


def test_approved_amount_is_verified_using_exact_decimal_not_float():
    verified = resolve_verified_shopify_plan(
        _snapshot(amount="19.0"), handle_catalog=APPROVED_CATALOG,
    )
    assert (verified.plan, verified.billing_period_months) == ("starter", 1)


@pytest.mark.parametrize("price", ["19.01", "20.00", "0.01", "18.99"])
def test_unapproved_real_price_does_not_become_eligible(price):
    with pytest.raises(ShopifyAppPricingError, match="SHOPIFY_PLAN_PRICE_MISMATCH"):
        resolve_verified_shopify_plan(
            _snapshot(amount=price),
            handle_catalog=APPROVED_CATALOG,
        )


@pytest.mark.parametrize(
    "bad_amount",
    [None, 19, 19.0, True, "", "NaN", "Infinity", "1e2", "-19.00",
     "+19.00", "0", "0.00", "19.001", " 19.00", "19.00 ", "1,900.00",
     "10000000.00"],
)
def test_missing_or_malformed_partner_amount_never_verifies_plan(bad_amount):
    with pytest.raises(ShopifyAppPricingError, match="SHOPIFY_PLAN_PRICE_UNVERIFIED"):
        resolve_verified_shopify_plan(
            _snapshot(amount=bad_amount),
            handle_catalog=APPROVED_CATALOG,
        )


@pytest.mark.parametrize(
    "bad_config",
    [None, 19, 19.0, True, "", "NaN", "1e2", "-5.00",
     "0.00", "19.001", " 19.00", "10000000.00"],
)
def test_operator_catalog_must_use_exact_approved_usd_decimal(bad_config):
    invalid_catalog = {
        "shopify-real-handle": {
            **APPROVED_CATALOG["shopify-real-handle"],
            "amount_usd": bad_config,
        }
    }
    with pytest.raises(ShopifyAppPricingError, match="SHOPIFY_PLAN_CATALOG_INVALID"):
        resolve_verified_shopify_plan(
            _snapshot(), handle_catalog=invalid_catalog,
        )


def test_preexisting_catalog_without_approved_price_fails_closed():
    with pytest.raises(ShopifyAppPricingError, match="SHOPIFY_PLAN_CATALOG_INVALID"):
        resolve_verified_shopify_plan(
            _snapshot(),
            handle_catalog={
                "shopify-real-handle": {
                    "plan": "starter", "interval": "EVERY_30_DAYS",
                }
            },
        )


def test_unpaired_price_or_multiple_items_must_not_verify():
    missing_amount = ShopifySubscriptionSnapshot(
        active=True,
        billing_period="EVERY_30_DAYS",
        item_handles=("shopify-real-handle",),
        eligible_handles=("shopify-real-handle",),
        eligible_amounts=(),
    )
    with pytest.raises(ShopifyAppPricingError, match="SHOPIFY_PLAN_PRICE_UNVERIFIED"):
        resolve_verified_shopify_plan(
            missing_amount, handle_catalog=APPROVED_CATALOG,
        )

    multi_item = ShopifySubscriptionSnapshot(
        active=True,
        billing_period="EVERY_30_DAYS",
        item_handles=("shopify-real-handle", "other-item"),
        eligible_handles=("shopify-real-handle", "other-item"),
        eligible_amounts=("19.00", "3.00"),
    )
    with pytest.raises(ShopifyAppPricingError, match="SHOPIFY_PLAN_ITEMS_UNRECOGNIZED"):
        resolve_verified_shopify_plan(
            multi_item, handle_catalog=APPROVED_CATALOG,
        )


@pytest.mark.parametrize(
    "raw_amount,expected",
    [("19.00", "19.00"), (None, None), (19.0, None), ("19.001", "19.001")],
)
def test_partner_api_amount_is_kept_as_untrusted_original_string(
    monkeypatch, raw_amount, expected,
):
    monkeypatch.setenv("SHOPIFY_PARTNER_ORG_ID", "12345")
    monkeypatch.setenv("SHOPIFY_PARTNER_APP_GID", "gid://shopify/App/54321")
    monkeypatch.setenv("SHOPIFY_PARTNER_ACCESS_TOKEN", "synthetic-token")
    payload = {
        "data": {
            "activeSubscription": {
                "shop": {"id": "gid://shopify/Shop/789"},
                "billingPeriod": "EVERY_30_DAYS",
                "currentBillingCycle": {"startTime": None, "endTime": None},
                "items": [{
                    "handle": "shopify-real-handle",
                    "price": {
                        "__typename": "FlatRatePrice",
                        "currency": "USD", "active": True,
                        "amount": raw_amount,
                    },
                }],
            },
        }
    }

    def handler(request):
        assert request.headers["X-Shopify-Access-Token"] == "synthetic-token"
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        subscription = get_active_shopify_subscription(
            "gid://shopify/Shop/789", http_client=client,
        )
    assert subscription.eligible_amounts == (expected,)
    if expected == "19.00":
        assert resolve_verified_shopify_plan(
            subscription, handle_catalog=APPROVED_CATALOG,
        ).plan == "starter"
    else:
        with pytest.raises(ShopifyAppPricingError):
            resolve_verified_shopify_plan(
                subscription, handle_catalog=APPROVED_CATALOG,
            )


def test_inactive_or_wrong_currency_never_confirms_a_paid_plan():
    with pytest.raises(ShopifyAppPricingError, match="NO_ACTIVE"):
        resolve_verified_shopify_plan(
            ShopifySubscriptionSnapshot(active=False),
            handle_catalog=APPROVED_CATALOG,
        )
