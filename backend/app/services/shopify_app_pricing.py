"""Read-only Shopify App Pricing subscription verification via Partner API.

Shopify App Pricing (2026-10) owns plan creation and merchant charges.
Never use the legacy Billing API to create charges for App Pricing merchants.
This module does not activate entitlements or mutate existing Paddle contracts.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import httpx


APP_GID_RE = re.compile(r"^gid://shopify/App/[0-9]+$")
SHOP_GID_RE = re.compile(r"^gid://shopify/Shop/[0-9]+$")
PARTNER_ORG_RE = re.compile(r"^[0-9]+$")

ACTIVE_SUBSCRIPTION_QUERY = """
query DiaglobActiveSubscription($appId: ID!, $shopId: ID!) {
  activeSubscription(appId: $appId, shopId: $shopId) {
    billingPeriod
    cancelAtEndOfCycle
    trialEndsAt
    currentBillingCycle { startTime endTime }
    items {
      handle
      description
      price { __typename active currency }
    }
    pendingUpdate {
      billingPeriod
      items { handle }
    }
  }
}
"""


class ShopifyAppPricingError(RuntimeError):
    """Provider state cannot be verified; fail closed, never grant plan access."""


@dataclass(frozen=True)
class ShopifySubscriptionSnapshot:
    """Read-only partner confirmation. Item handles are NOT trusted plan grants."""

    active: bool
    billing_period: str | None = None
    item_handles: tuple[str, ...] = ()
    trial_ends_at: str | None = None
    current_cycle_end: str | None = None
    cancel_at_end_of_cycle: bool = False


def _configuration() -> tuple[str, str, str]:
    organization_id = (os.getenv("SHOPIFY_PARTNER_ORG_ID") or "").strip()
    app_gid = (os.getenv("SHOPIFY_PARTNER_APP_GID") or "").strip()
    token = (os.getenv("SHOPIFY_PARTNER_ACCESS_TOKEN") or "").strip()
    if (
        not PARTNER_ORG_RE.fullmatch(organization_id)
        or not APP_GID_RE.fullmatch(app_gid)
        or not token
    ):
        raise ShopifyAppPricingError("SHOPIFY_PARTNER_API_NOT_CONFIGURED")
    return organization_id, app_gid, token


def get_active_shopify_subscription(
    shop_gid: str,
    *,
    http_client: httpx.Client | None = None,
) -> ShopifySubscriptionSnapshot:
    """Confirm the currently active app subscription for a trusted shop GID.

    Must be called only after an authenticated Shopify installation establishes
    the exact Shop GID. Never derive it from a user-supplied shop domain or
    accept a `plan_handle` redirect parameter as evidence of payment.
    """
    if not SHOP_GID_RE.fullmatch(shop_gid or ""):
        raise ShopifyAppPricingError("INVALID_SHOP_GID")
    organization_id, app_gid, token = _configuration()
    url = f"https://partners.shopify.com/{organization_id}/api/2026-10/graphql.json"
    payload = {
        "query": ACTIVE_SUBSCRIPTION_QUERY,
        "variables": {"appId": app_gid, "shopId": shop_gid},
    }
    try:
        if http_client is None:
            with httpx.Client(timeout=10) as client:
                response = client.post(
                    url,
                    json=payload,
                    headers={"X-Shopify-Access-Token": token},
                )
        else:
            response = http_client.post(
                url,
                json=payload,
                headers={"X-Shopify-Access-Token": token},
            )
        response.raise_for_status()
        body: Any = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ShopifyAppPricingError("SHOPIFY_PARTNER_API_UNAVAILABLE") from exc

    if not isinstance(body, dict) or body.get("errors"):
        raise ShopifyAppPricingError("SHOPIFY_PARTNER_API_GRAPHQL_ERROR")
    data = body.get("data")
    if not isinstance(data, dict) or "activeSubscription" not in data:
        raise ShopifyAppPricingError("SHOPIFY_PARTNER_API_INVALID_RESPONSE")
    subscription = data["activeSubscription"]
    if subscription is None:
        return ShopifySubscriptionSnapshot(active=False)
    if not isinstance(subscription, dict):
        raise ShopifyAppPricingError("SHOPIFY_PARTNER_API_INVALID_RESPONSE")
    items = subscription.get("items")
    if not isinstance(items, list):
        raise ShopifyAppPricingError("SHOPIFY_PARTNER_API_INVALID_RESPONSE")
    if any(not isinstance(item, dict) for item in items):
        raise ShopifyAppPricingError("SHOPIFY_PARTNER_API_INVALID_RESPONSE")

    cycle = subscription.get("currentBillingCycle")
    if cycle is not None and not isinstance(cycle, dict):
        raise ShopifyAppPricingError("SHOPIFY_PARTNER_API_INVALID_RESPONSE")
    handles = tuple(
        handle.strip()
        for item in items
        if isinstance(handle := item.get("handle"), str) and handle.strip()
    )
    return ShopifySubscriptionSnapshot(
        active=True,
        billing_period=subscription.get("billingPeriod"),
        item_handles=handles,
        trial_ends_at=subscription.get("trialEndsAt"),
        current_cycle_end=cycle.get("endTime") if cycle else None,
        cancel_at_end_of_cycle=subscription.get("cancelAtEndOfCycle") is True,
    )
