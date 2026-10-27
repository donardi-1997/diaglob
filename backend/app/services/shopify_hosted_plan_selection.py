"""Build a Shopify-hosted App Pricing link from a verified merchant shop.

No charges are created in DIAGLOB. Never trust a shop or plan handle supplied
by the browser: app handle comes from operator config, shop from connected OAuth.
"""
from __future__ import annotations

import os
import re
from urllib.parse import quote

from sqlalchemy.orm import Session

from ..models import CommerceConnection, Organization, Store
from .billing_channel_policy import paddle_migration_cancellation_verified
from .shopify_app_pricing import (
    ShopifyAppPricingError,
    resolve_trusted_shop_gid,
)

_APP_HANDLE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,98}[a-z0-9])?$")
_SHOP_HANDLE = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")


def get_hosted_plan_selection(
    db: Session, *, organization_id: int,
) -> dict:
    """Verify a single Shopify-managed merchant before returning the hosted URL."""
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    migration = bool(org and org.billing_provider == "paddle")
    if not org or not org.active or ((org.billing_provider or "").lower() != "shopify" and not migration):
        raise ShopifyAppPricingError("SHOPIFY_BILLING_PROVENANCE_REQUIRED")
    if migration:
        if not paddle_migration_cancellation_verified(db, org):
            raise ShopifyAppPricingError("SHOPIFY_BILLING_PROVENANCE_REQUIRED")
    elif org.billing_customer_id or org.billing_subscription_id or org.billing_price_id:
        raise ShopifyAppPricingError("SHOPIFY_LEGACY_BILLING_REVIEW_REQUIRED")
    connections = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.provider == "shopify",
        )
        .limit(2).all()
    )
    if len(connections) != 1 or connections[0].status != "connected":
        raise ShopifyAppPricingError("SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED")
    connection = connections[0]
    store = db.query(Store).filter(
        Store.id == connection.store_id,
        Store.organization_id == organization_id,
        Store.active.is_(True),
        Store.deleted.is_(False),
    ).first()
    if store is None:
        raise ShopifyAppPricingError("SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED")

    app_handle = (os.getenv("SHOPIFY_APP_STORE_HANDLE") or "").strip()
    if not _APP_HANDLE.fullmatch(app_handle):
        raise ShopifyAppPricingError("SHOPIFY_HOSTED_PRICING_NOT_CONFIGURED")

    # Authenticate shop ownership with the installed token before exposing a
    # trusted administrative redirect. Never use URL query parameter "shop".
    resolve_trusted_shop_gid(connection)
    domain = connection.external_store_url
    suffix = ".myshopify.com"
    if not domain.endswith(suffix):
        raise ShopifyAppPricingError("SHOPIFY_IDENTITY_INVALID")
    shop_handle = domain[:-len(suffix)]
    if not _SHOP_HANDLE.fullmatch(shop_handle):
        raise ShopifyAppPricingError("SHOPIFY_IDENTITY_INVALID")

    return {
        "provider": "shopify",
        "hosted_by_shopify": True,
        "url": (
            "https://admin.shopify.com/store/"
            f"{quote(shop_handle, safe='')}/charges/"
            f"{quote(app_handle, safe='')}/pricing_plans"
        ),
        "entitlements_applied": False,
    }
