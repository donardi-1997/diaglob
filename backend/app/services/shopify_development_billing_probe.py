"""Owner-only, read-only observation of Shopify App Pricing test contracts.

A development-store effective price of USD 0 proves neither merchant payment
nor commercial entitlement. Never call a plan mapper or mutate an organization.
The operator must verify development-store eligibility in Partner Dashboard.
"""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Any

from ..shopify_oauth import normalize_shop_domain
from .shopify_app_pricing import (
    ShopifyAppPricingError,
    USD_AMOUNT_RE,
    get_active_shopify_subscription,
    resolve_trusted_shop_gid,
)

_VALID_PERIODS = frozenset({"EVERY_30_DAYS", "ANNUAL"})


def probe_shopify_development_subscription(
    organization: Any,
    connection: Any,
    *,
    connected_shopify_store_count: int,
) -> dict:
    """Observe an approved test store; never record or apply paid entitlements.

    No client-supplied shop, handle, or GID is accepted. Two independent
    operator settings authorize this owner-only endpoint, but do NOT enable
    the normal commercial-billing entitlement feature.
    """
    if os.getenv("SHOPIFY_BILLING_TEST_PROBE_ENABLED", "") != "true":
        raise ShopifyAppPricingError("SHOPIFY_TEST_PROBE_DISABLED")
    allowed_shop = (os.getenv("SHOPIFY_BILLING_TEST_SHOP_DOMAIN") or "").strip()
    if not allowed_shop:
        raise ShopifyAppPricingError("SHOPIFY_TEST_SHOP_NOT_CONFIGURED")
    try:
        allowed_domain = normalize_shop_domain(allowed_shop)
    except (ValueError, AttributeError) as exc:
        raise ShopifyAppPricingError("SHOPIFY_TEST_SHOP_NOT_CONFIGURED") from exc

    org_id = getattr(organization, "id", None)
    if (
        type(org_id) is not int
        or org_id < 1
        or not getattr(organization, "active", False)
        or (getattr(organization, "billing_provider", "") or "").lower() != "shopify"
        or getattr(organization, "billing_customer_id", None)
        or getattr(organization, "billing_subscription_id", None)
        or getattr(organization, "billing_price_id", None)
        or getattr(connection, "organization_id", None) != org_id
        or getattr(connection, "provider", None) != "shopify"
        or getattr(connection, "status", None) != "connected"
        or type(connected_shopify_store_count) is not int
        or connected_shopify_store_count != 1
    ):
        raise ShopifyAppPricingError("SHOPIFY_TEST_PROBE_TENANT_REVIEW_REQUIRED")
    try:
        connected_domain = normalize_shop_domain(connection.external_store_url)
    except (ValueError, AttributeError) as exc:
        raise ShopifyAppPricingError("SHOPIFY_TEST_PROBE_TENANT_REVIEW_REQUIRED") from exc
    if connected_domain != allowed_domain:
        raise ShopifyAppPricingError("SHOPIFY_TEST_SHOP_NOT_ALLOWLISTED")

    # Verify the installation first. Partner API confirms the app/shop binding.
    shop_gid = resolve_trusted_shop_gid(connection)
    contract = get_active_shopify_subscription(shop_gid)
    if not contract.active:
        status = "no_active_contract"
        period = None
    else:
        period = contract.billing_period if contract.billing_period in _VALID_PERIODS else None
        safe_shape = (
            len(contract.item_handles) == 1
            and len(contract.eligible_handles) == 1
            and contract.item_handles == contract.eligible_handles
            and len(contract.eligible_amounts) == 1
            and period is not None
        )
        if not safe_shape:
            status = "unrecognized_contract_no_grant"
        else:
            amount = contract.eligible_amounts[0]
            if type(amount) is not str or not USD_AMOUNT_RE.fullmatch(amount):
                status = "unrecognized_contract_no_grant"
            elif Decimal(amount) == 0:
                status = "zero_usd_contract_observed_no_grant"
            else:
                status = "nonzero_contract_observed_no_grant"

    # Deliberately exclude shop domains, Shop GIDs, API payloads, tokens,
    # handles and prices. Even an active, positive-priced contract cannot
    # trigger paid entitlements through the testing endpoint.
    return {
        "status": status,
        "organization_id": org_id,
        "contract_observed": bool(contract.active),
        "billing_period": period,
        "requires_review": True,
        "applied": False,
        "commercial_entitlements_granted": False,
    }
