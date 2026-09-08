"""Ads analytics service.

Calculates dropshipping/ecommerce metrics using Meta Ads + commerce data.
Does NOT own provider HTTP.
Does NOT own billing/plan logic.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..integrations.meta_ads.client import (
    MetaAdsError,
    get_campaign_insights,
    get_insights,
    parse_insights_row,
)
from ..meta_ads_security import decrypt_secret
from ..models import (
    MetaAdsConnection,
    Order,
    Store,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


def get_store_analytics(
    db: Session,
    organization_id: int,
    store_id: int,
    date_preset: str = "last_30d",
) -> dict:
    """Get analytics for a single store."""
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if not store:
        return {"error": "Store not found"}

    # Get Meta Ads connection
    connection = (
        db.query(MetaAdsConnection)
        .filter(
            MetaAdsConnection.store_id == store_id,
            MetaAdsConnection.organization_id == organization_id,
            MetaAdsConnection.status == "connected",
        )
        .first()
    )

    # Get ad spend from Meta if connected
    ad_spend = ZERO
    impressions = 0
    clicks = 0
    meta_currency = None
    meta_error = None

    if connection:
        try:
            token = decrypt_secret(connection.access_token_encrypted)
            insights = get_insights(
                token,
                connection.external_account_id,
                date_preset=date_preset,
            )

            if insights:
                parsed = parse_insights_row(insights[0])
                ad_spend = parsed["spend"]
                impressions = parsed["impressions"]
                clicks = parsed["clicks"]
                meta_currency = connection.account_currency

        except MetaAdsError as exc:
            meta_error = str(exc)
            logger.warning("Meta Ads error for store %s: %s", store_id, exc)

    # Get commerce data
    revenue, orders_count = _get_commerce_data(
        db, organization_id, store_id, date_preset
    )

    # Calculate metrics
    currency = store.currency or meta_currency or "USD"

    blended_roas = None
    if ad_spend > ZERO and revenue > ZERO:
        blended_roas = (revenue / ad_spend).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    cpa_order = None
    if ad_spend > ZERO and orders_count > 0:
        cpa_order = (ad_spend / orders_count).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    aov = None
    if revenue > ZERO and orders_count > 0:
        aov = (revenue / orders_count).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return {
        "store_id": store_id,
        "store_name": store.name,
        "currency": currency,
        "date_preset": date_preset,
        "revenue": str(revenue),
        "orders": orders_count,
        "ad_spend": str(ad_spend),
        "impressions": impressions,
        "clicks": clicks,
        "blended_roas": str(blended_roas) if blended_roas else None,
        "cpa_order": str(cpa_order) if cpa_order else None,
        "aov": str(aov) if aov else None,
        "meta_connected": connection is not None,
        "meta_error": meta_error,
    }


def get_multi_store_analytics(
    db: Session,
    organization_id: int,
    store_ids: list[int] | None,
    date_preset: str = "last_30d",
) -> dict:
    """Get analytics across multiple stores."""
    if store_ids:
        stores = (
            db.query(Store)
            .filter(
                Store.id.in_(store_ids),
                Store.organization_id == organization_id,
                Store.deleted.is_(False),
            )
            .all()
        )
    else:
        stores = (
            db.query(Store)
            .filter(
                Store.organization_id == organization_id,
                Store.deleted.is_(False),
            )
            .all()
        )

    store_results = []
    total_revenue = ZERO
    total_spend = ZERO
    total_orders = 0
    total_impressions = 0
    total_clicks = 0
    currencies = set()

    for store in stores:
        result = get_store_analytics(
            db, organization_id, store.id, date_preset
        )
        store_results.append(result)

        currency = result.get("currency", "USD")
        currencies.add(currency)

        revenue = Decimal(result.get("revenue", "0"))
        spend = Decimal(result.get("ad_spend", "0"))
        orders = result.get("orders", 0)

        total_revenue += revenue
        total_spend += spend
        total_orders += orders
        total_impressions += result.get("impressions", 0)
        total_clicks += result.get("clicks", 0)

    # Aggregate metrics
    blended_roas = None
    if total_spend > ZERO and total_revenue > ZERO:
        blended_roas = (total_revenue / total_spend).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    cpa_order = None
    if total_spend > ZERO and total_orders > 0:
        cpa_order = (total_spend / total_orders).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    aov = None
    if total_revenue > ZERO and total_orders > 0:
        aov = (total_revenue / total_orders).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return {
        "store_count": len(stores),
        "currencies": sorted(currencies),
        "date_preset": date_preset,
        "total_revenue": str(total_revenue),
        "total_orders": total_orders,
        "total_ad_spend": str(total_spend),
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "blended_roas": str(blended_roas) if blended_roas else None,
        "cpa_order": str(cpa_order) if cpa_order else None,
        "aov": str(aov) if aov else None,
        "stores": store_results,
    }


def _get_commerce_data(
    db: Session,
    organization_id: int,
    store_id: int,
    date_preset: str,
) -> tuple[Decimal, int]:
    """Get revenue and order count for a store."""
    now = datetime.utcnow()

    if date_preset == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif date_preset == "yesterday":
        start = (now - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif date_preset == "last_7d":
        start = now - timedelta(days=7)
    elif date_preset == "last_30d":
        start = now - timedelta(days=30)
    else:
        start = now - timedelta(days=30)

    query = (
        db.query(
            func.sum(Order.total_amount).label("revenue"),
            func.count(Order.id).label("count"),
        )
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
            Order.created_at >= start,
        )
    )

    row = query.first()
    revenue = Decimal(str(row[0] or 0)) if row else ZERO
    count = row[1] if row else 0

    return revenue, count
