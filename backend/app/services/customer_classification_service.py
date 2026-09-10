"""Deterministic customer value classification and analytics.

Commercial classifications are intentionally separate from the legacy
Customer Intelligence operational segments. They use delivered commerce
outcomes only for purchase frequency and monetary value.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Conversation, Customer, CustomerStoreProfile, Order, Store

CLASS_CHAMPION = "champion"
CLASS_LOYAL = "loyal"
CLASS_REPEAT = "repeat_customer"
CLASS_HIGH_VALUE = "high_value"
CLASS_RECENT_BUYER = "recent_buyer"
CLASS_VALUE_AT_RISK = "value_at_risk"
CLASS_DORMANT = "dormant"
CLASS_PROSPECT = "prospect"
CLASS_LEAD = "lead"

CLASSIFICATIONS = (
    CLASS_CHAMPION,
    CLASS_LOYAL,
    CLASS_REPEAT,
    CLASS_HIGH_VALUE,
    CLASS_RECENT_BUYER,
    CLASS_VALUE_AT_RISK,
    CLASS_DORMANT,
    CLASS_PROSPECT,
    CLASS_LEAD,
)

VALUE_HIGH = "high"
VALUE_MEDIUM = "medium"
VALUE_LOW = "low"
VALUE_NONE = "none"
VALUE_TIERS = (VALUE_HIGH, VALUE_MEDIUM, VALUE_LOW, VALUE_NONE)


def _days_since(value: datetime | None, now: datetime) -> int | None:
    if value is None:
        return None
    return max(0, (now - value).days)


def _safe_pct(numerator: float | int, denominator: float | int) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator) * 100, 1)


def _cohort_value_tiers(values: dict[int, float]) -> dict[int, str]:
    """Assign relative monetary tiers inside one store/currency cohort."""
    positive = sorted(value for value in values.values() if value > 0)
    if not positive:
        return {customer_id: VALUE_NONE for customer_id in values}

    high_index = math.ceil(0.75 * (len(positive) - 1))
    medium_index = math.ceil(0.40 * (len(positive) - 1))
    high_threshold = positive[high_index]
    medium_threshold = positive[medium_index]

    tiers: dict[int, str] = {}
    for customer_id, value in values.items():
        if value <= 0:
            tiers[customer_id] = VALUE_NONE
        elif value >= high_threshold:
            tiers[customer_id] = VALUE_HIGH
        elif value >= medium_threshold:
            tiers[customer_id] = VALUE_MEDIUM
        else:
            tiers[customer_id] = VALUE_LOW
    return tiers


def _rfm_scores(
    recency_days: int | None,
    frequency: int,
    value_tier: str,
) -> tuple[int, int, int]:
    if recency_days is None:
        recency_score = 0
    elif recency_days <= 30:
        recency_score = 5
    elif recency_days <= 60:
        recency_score = 4
    elif recency_days <= 90:
        recency_score = 3
    elif recency_days <= 180:
        recency_score = 2
    else:
        recency_score = 1

    if frequency >= 5:
        frequency_score = 5
    elif frequency >= 3:
        frequency_score = 4
    elif frequency >= 2:
        frequency_score = 3
    elif frequency >= 1:
        frequency_score = 2
    else:
        frequency_score = 0

    monetary_score = {
        VALUE_HIGH: 5,
        VALUE_MEDIUM: 3,
        VALUE_LOW: 2,
        VALUE_NONE: 0,
    }[value_tier]
    return recency_score, frequency_score, monetary_score


def _classify(
    *,
    recency_days: int | None,
    frequency: int,
    value_tier: str,
    interaction_recency_days: int | None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if frequency == 0:
        if interaction_recency_days is not None and interaction_recency_days <= 14:
            return CLASS_PROSPECT, ["recent_interaction_no_purchase"]
        return CLASS_LEAD, ["no_delivered_purchase"]

    if recency_days is not None and recency_days > 180:
        return CLASS_DORMANT, ["purchase_older_than_180d"]

    if recency_days is not None and recency_days > 90:
        return CLASS_VALUE_AT_RISK, ["purchase_older_than_90d"]

    if frequency >= 5 and value_tier == VALUE_HIGH and recency_days is not None and recency_days <= 30:
        reasons.extend(["five_plus_delivered_orders", "high_value_tier", "purchase_within_30d"])
        return CLASS_CHAMPION, reasons

    if frequency >= 3 and recency_days is not None and recency_days <= 60:
        return CLASS_LOYAL, ["three_plus_delivered_orders", "purchase_within_60d"]

    if frequency >= 2 and recency_days is not None and recency_days <= 60:
        return CLASS_REPEAT, ["repeat_delivered_buyer", "purchase_within_60d"]

    if value_tier == VALUE_HIGH and recency_days is not None and recency_days <= 90:
        return CLASS_HIGH_VALUE, ["high_value_tier", "purchase_within_90d"]

    return CLASS_RECENT_BUYER, ["delivered_buyer"]


def get_customer_classification_map(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    now: datetime | None = None,
) -> dict[int, dict[str, Any]]:
    """Return current commercial classification keyed by customer id."""
    now = now or datetime.utcnow()

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
        return {}

    customers = (
        db.query(Customer)
        .join(
            CustomerStoreProfile,
            CustomerStoreProfile.customer_id == Customer.id,
        )
        .filter(
            Customer.organization_id == organization_id,
            CustomerStoreProfile.organization_id == organization_id,
            CustomerStoreProfile.store_id == store_id,
        )
        .all()
    )
    customer_ids = [customer.id for customer in customers]
    if not customer_ids:
        return {}

    delivered_rows = (
        db.query(
            Order.customer_id,
            func.count(Order.id).label("frequency"),
            func.coalesce(func.sum(Order.total_amount), 0).label("monetary_value"),
            func.max(Order.created_at).label("last_delivered_at"),
        )
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
            Order.customer_id.in_(customer_ids),
            Order.lifecycle_status == "delivered",
        )
        .group_by(Order.customer_id)
        .all()
    )
    delivered = {
        row.customer_id: {
            "frequency": int(row.frequency or 0),
            "monetary_value": float(row.monetary_value or 0),
            "last_delivered_at": row.last_delivered_at,
        }
        for row in delivered_rows
    }

    interaction_rows = (
        db.query(
            Conversation.customer_id,
            func.max(Conversation.updated_at).label("last_interaction_at"),
        )
        .filter(
            Conversation.organization_id == organization_id,
            Conversation.store_id == store_id,
            Conversation.customer_id.in_(customer_ids),
        )
        .group_by(Conversation.customer_id)
        .all()
    )
    interactions = {row.customer_id: row.last_interaction_at for row in interaction_rows}

    values = {
        customer.id: delivered.get(customer.id, {}).get("monetary_value", 0.0)
        for customer in customers
    }
    tiers = _cohort_value_tiers(values)

    result: dict[int, dict[str, Any]] = {}
    for customer in customers:
        commerce = delivered.get(customer.id, {})
        frequency = int(commerce.get("frequency", 0))
        monetary_value = float(commerce.get("monetary_value", 0.0))
        last_delivered_at = commerce.get("last_delivered_at")
        last_interaction_at = interactions.get(customer.id)
        recency_days = _days_since(last_delivered_at, now)
        interaction_recency_days = _days_since(last_interaction_at, now)
        value_tier = tiers[customer.id]
        classification, reasons = _classify(
            recency_days=recency_days,
            frequency=frequency,
            value_tier=value_tier,
            interaction_recency_days=interaction_recency_days,
        )
        r_score, f_score, m_score = _rfm_scores(recency_days, frequency, value_tier)

        result[customer.id] = {
            "customer_id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "country_code": customer.country_code,
            "currency": store.currency,
            "commercial_classification": classification,
            "value_tier": value_tier,
            "rfm_recency_days": recency_days,
            "rfm_frequency": frequency,
            "rfm_monetary_value": monetary_value,
            "rfm_recency_score": r_score,
            "rfm_frequency_score": f_score,
            "rfm_monetary_score": m_score,
            "rfm_score": r_score + f_score + m_score,
            "last_delivered_at": last_delivered_at.isoformat() if last_delivered_at else None,
            "last_interaction_at": last_interaction_at.isoformat() if last_interaction_at else None,
            "classification_reasons": reasons,
        }
    return result


def enrich_customer_metrics(
    db: Session,
    organization_id: int,
    store_id: int,
    metrics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach current commercial classification fields to customer metrics."""
    mapping = get_customer_classification_map(db, organization_id, store_id)
    enriched: list[dict[str, Any]] = []
    for item in metrics:
        classification = mapping.get(item.get("id"))
        enriched.append({**item, **(classification or {})})
    return enriched


def get_customer_classifications(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    classification: str | None = None,
    value_tier: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: str = "value_desc",
) -> dict[str, Any]:
    mapping = get_customer_classification_map(db, organization_id, store_id)
    items = list(mapping.values())

    if classification:
        items = [item for item in items if item["commercial_classification"] == classification]
    if value_tier:
        items = [item for item in items if item["value_tier"] == value_tier]
    if search:
        needle = search.strip().lower()
        items = [
            item
            for item in items
            if needle in (item.get("name") or "").lower()
            or needle in (item.get("phone") or "").lower()
            or needle in (item.get("email") or "").lower()
        ]

    if sort == "recency_asc":
        items.sort(key=lambda item: item["rfm_recency_days"] if item["rfm_recency_days"] is not None else 10**9)
    elif sort == "frequency_desc":
        items.sort(key=lambda item: (item["rfm_frequency"], item["rfm_monetary_value"]), reverse=True)
    elif sort == "rfm_desc":
        items.sort(key=lambda item: (item["rfm_score"], item["rfm_monetary_value"]), reverse=True)
    else:
        items.sort(key=lambda item: (item["rfm_monetary_value"], item["rfm_frequency"]), reverse=True)

    total = len(items)
    page_size = min(max(1, page_size), 100)
    total_pages = max(1, math.ceil(total / page_size))
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size

    all_items = list(mapping.values())
    buyers = [item for item in all_items if item["rfm_frequency"] > 0]
    classification_counts = {key: 0 for key in CLASSIFICATIONS}
    value_tier_counts = {key: 0 for key in VALUE_TIERS}
    for item in all_items:
        classification_counts[item["commercial_classification"]] += 1
        value_tier_counts[item["value_tier"]] += 1

    return {
        "items": items[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "summary": {
            "total_customers": len(all_items),
            "buyers": len(buyers),
            "repeat_buyers": sum(1 for item in buyers if item["rfm_frequency"] >= 2),
            "repeat_buyer_rate": _safe_pct(sum(1 for item in buyers if item["rfm_frequency"] >= 2), len(buyers)),
            "lifetime_delivered_revenue": round(sum(item["rfm_monetary_value"] for item in buyers), 2),
            "classification_counts": classification_counts,
            "value_tier_counts": value_tier_counts,
        },
    }


def get_customer_classification_analytics(
    db: Session,
    organization_id: int,
    store_id: int,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    """Current classifications with delivered performance for selected period."""
    mapping = get_customer_classification_map(db, organization_id, store_id)
    store = (
        db.query(Store)
        .filter(Store.id == store_id, Store.organization_id == organization_id)
        .first()
    )

    period_query = db.query(
        Order.customer_id,
        func.count(Order.id).label("orders"),
        func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
    ).filter(
        Order.organization_id == organization_id,
        Order.store_id == store_id,
        Order.customer_id.isnot(None),
        Order.lifecycle_status == "delivered",
    )
    if date_from:
        period_query = period_query.filter(Order.created_at >= date_from)
    if date_to:
        period_query = period_query.filter(Order.created_at < date_to)
    period_rows = period_query.group_by(Order.customer_id).all()
    period_by_customer = {
        row.customer_id: {"orders": int(row.orders or 0), "revenue": float(row.revenue or 0)}
        for row in period_rows
    }

    total_period_revenue = sum(value["revenue"] for value in period_by_customer.values())
    total_period_orders = sum(value["orders"] for value in period_by_customer.values())
    buyers = [item for item in mapping.values() if item["rfm_frequency"] > 0]
    repeat_buyers = [item for item in buyers if item["rfm_frequency"] >= 2]

    distribution = []
    for key in CLASSIFICATIONS:
        members = [item for item in mapping.values() if item["commercial_classification"] == key]
        customer_ids = {item["customer_id"] for item in members}
        period_orders = sum(period_by_customer.get(customer_id, {}).get("orders", 0) for customer_id in customer_ids)
        period_revenue = sum(period_by_customer.get(customer_id, {}).get("revenue", 0.0) for customer_id in customer_ids)
        distribution.append(
            {
                "classification": key,
                "customers": len(members),
                "customer_share_pct": _safe_pct(len(members), len(mapping)) or 0.0,
                "period_delivered_orders": period_orders,
                "period_delivered_revenue": round(period_revenue, 2),
                "revenue_share_pct": _safe_pct(period_revenue, total_period_revenue) or 0.0,
                "avg_order_value": round(period_revenue / period_orders, 2) if period_orders else None,
            }
        )

    top_customers = []
    for item in mapping.values():
        period = period_by_customer.get(item["customer_id"], {"orders": 0, "revenue": 0.0})
        top_customers.append(
            {
                **item,
                "period_delivered_orders": period["orders"],
                "period_delivered_revenue": round(period["revenue"], 2),
            }
        )
    top_customers.sort(
        key=lambda item: (item["period_delivered_revenue"], item["rfm_monetary_value"]),
        reverse=True,
    )

    value_tier_distribution = []
    for tier in VALUE_TIERS:
        members = [item for item in mapping.values() if item["value_tier"] == tier]
        value_tier_distribution.append(
            {
                "value_tier": tier,
                "customers": len(members),
                "customer_share_pct": _safe_pct(len(members), len(mapping)) or 0.0,
            }
        )

    return {
        "currency": store.currency if store else "",
        "total_customers": len(mapping),
        "customers_with_delivered_orders": len(buyers),
        "repeat_customer_rate": _safe_pct(len(repeat_buyers), len(buyers)),
        "period_delivered_orders": total_period_orders,
        "period_delivered_revenue": round(total_period_revenue, 2),
        "classification_distribution": distribution,
        "value_tier_distribution": value_tier_distribution,
        "top_customers": top_customers[:10],
        "classification_basis": "current_lifetime_delivered_rfm",
        "period_basis": "selected_period_delivered_orders",
    }
