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

from ..shopify_client import ShopifyGraphQLClient
from ..shopify_oauth import normalize_shop_domain
from ..shopify_security import decrypt_shopify_secret


SHOP_IDENTITY_QUERY = """
query DiaglobShopIdentity {
  shop { id myshopifyDomain }
}
"""


APP_GID_RE = re.compile(r"^gid://shopify/App/[0-9]+$")
SHOP_GID_RE = re.compile(r"^gid://shopify/Shop/[0-9]+$")
PARTNER_ORG_RE = re.compile(r"^[0-9]+$")

ACTIVE_SUBSCRIPTION_QUERY = """
query DiaglobActiveSubscription($appId: ID!, $shopId: ID!) {
  activeSubscription(appId: $appId, shopId: $shopId) {
    shop { id }
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
    eligible_handles: tuple[str, ...] = ()
    trial_ends_at: str | None = None
    current_cycle_end: str | None = None
    cancel_at_end_of_cycle: bool = False


def resolve_trusted_shop_gid(connection: Any) -> str:
    """Get the verified Shop GID from an authenticated, connected store token.

    This function does not authorize a DIAGLOB user: the caller must first
    authorize tenant/store access and load the matching CommerceConnection.
    A merchant-provided domain or plan redirect alone cannot authenticate a
    Shopify shop or its subscription.
    """
    if (
        getattr(connection, "provider", None) != "shopify"
        or getattr(connection, "status", None) != "connected"
    ):
        raise ShopifyAppPricingError("SHOPIFY_CONNECTION_NOT_VERIFIED")
    try:
        domain = normalize_shop_domain(connection.external_store_url)
        token = decrypt_shopify_secret(connection.access_token_encrypted)
        response = ShopifyGraphQLClient(
            shop_domain=domain,
            access_token=token,
        ).query(SHOP_IDENTITY_QUERY)
    except (ValueError, RuntimeError, AttributeError) as exc:
        raise ShopifyAppPricingError("SHOPIFY_IDENTITY_UNAVAILABLE") from exc
    except Exception as exc:
        raise ShopifyAppPricingError("SHOPIFY_IDENTITY_UNAVAILABLE") from exc

    shop = response.get("shop") if isinstance(response, dict) else None
    if not isinstance(shop, dict):
        raise ShopifyAppPricingError("SHOPIFY_IDENTITY_INVALID")
    shop_gid = shop.get("id")
    try:
        response_domain = normalize_shop_domain(shop.get("myshopifyDomain") or "")
    except (ValueError, AttributeError) as exc:
        raise ShopifyAppPricingError("SHOPIFY_IDENTITY_INVALID") from exc
    if not isinstance(shop_gid, str) or not SHOP_GID_RE.fullmatch(shop_gid):
        raise ShopifyAppPricingError("SHOPIFY_IDENTITY_INVALID")
    if response_domain != domain:
        raise ShopifyAppPricingError("SHOPIFY_IDENTITY_MISMATCH")
    return shop_gid


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
    linked_shop = subscription.get("shop")
    if not isinstance(linked_shop, dict) or linked_shop.get("id") != shop_gid:
        raise ShopifyAppPricingError("SHOPIFY_SUBSCRIPTION_SHOP_MISMATCH")
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
    eligible_handles = tuple(
        str(item["handle"]).strip()
        for item in items
        if isinstance(item.get("handle"), str)
        and item["handle"].strip()
        and isinstance(item.get("price"), dict)
        and item["price"].get("active") is True
        and item["price"].get("__typename") == "FlatRatePrice"
        and item["price"].get("currency") == "USD"
    )
    return ShopifySubscriptionSnapshot(
        active=True,
        billing_period=subscription.get("billingPeriod"),
        item_handles=handles,
        eligible_handles=eligible_handles,
        trial_ends_at=subscription.get("trialEndsAt"),
        current_cycle_end=cycle.get("endTime") if cycle else None,
        cancel_at_end_of_cycle=subscription.get("cancelAtEndOfCycle") is True,
    )


@dataclass(frozen=True)
class VerifiedShopifyPlan:
    """Provisional entitlement decision; does not write to Organization."""

    plan: str
    billing_period_months: int
    handle: str


def resolve_verified_shopify_plan(
    subscription: ShopifySubscriptionSnapshot,
    *,
    handle_catalog: dict[str, Any] | None = None,
) -> VerifiedShopifyPlan:
    """Resolve only a verified, explicitly configured App Pricing plan.

    Never accept a plan from a URL, trial prompt or display description.
    A Shopify API call must produce the snapshot. This method is read-only and
    does not modify Paddle records or grant database entitlements.

    When handle_catalog is omitted, use operator-managed environment JSON:
      {"actual_shopify_handle": {"plan": "starter", "interval": "EVERY_30_DAYS"}}

    A subscription with multiple items (for example, unknown usage-based items)
    is deliberately not eligible until its actual contract structure is reviewed.
    """
    if not subscription.active:
        raise ShopifyAppPricingError("SHOPIFY_NO_ACTIVE_SUBSCRIPTION")

    if handle_catalog is None:
        import json

        raw = (os.getenv("SHOPIFY_APP_PRICING_HANDLES_JSON") or "").strip()
        if not raw:
            raise ShopifyAppPricingError("SHOPIFY_PLAN_CATALOG_NOT_CONFIGURED")
        try:
            handle_catalog = json.loads(raw)
        except ValueError as exc:
            raise ShopifyAppPricingError("SHOPIFY_PLAN_CATALOG_INVALID") from exc

    if not isinstance(handle_catalog, dict) or not handle_catalog:
        raise ShopifyAppPricingError("SHOPIFY_PLAN_CATALOG_INVALID")

    if len(subscription.item_handles) != 1 or len(subscription.eligible_handles) != 1:
        raise ShopifyAppPricingError("SHOPIFY_PLAN_ITEMS_UNRECOGNIZED")
    handle = subscription.eligible_handles[0]
    if handle != subscription.item_handles[0]:
        raise ShopifyAppPricingError("SHOPIFY_PLAN_ITEMS_UNRECOGNIZED")
    entry = handle_catalog.get(handle)
    if not isinstance(entry, dict):
        raise ShopifyAppPricingError("SHOPIFY_PLAN_HANDLE_UNKNOWN")
    plan = entry.get("plan")
    interval = entry.get("interval")
    if not isinstance(plan, str) or plan not in {"starter", "growth", "pro", "scale"}:
        raise ShopifyAppPricingError("SHOPIFY_PLAN_CATALOG_INVALID")
    periods = {"EVERY_30_DAYS": 1, "ANNUAL": 12}
    if not isinstance(interval, str) or interval not in periods or subscription.billing_period != interval:
        raise ShopifyAppPricingError("SHOPIFY_PLAN_INTERVAL_MISMATCH")
    return VerifiedShopifyPlan(
        plan=plan,
        billing_period_months=periods[interval],
        handle=handle,
    )
