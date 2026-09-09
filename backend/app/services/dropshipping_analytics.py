"""Dropshipping analytics service.

Provides profit-oriented analytics for dropshipping operations.

Lifecycle semantics:
- lifecycle_status is a mutually exclusive current-state field
- For cumulative funnel, delivered counts in shipped and confirmed stages
- Cancelled/returned are side outcomes, not part of the forward funnel
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Order, OrderItem, Product


def _safe_percentage(numerator: Any, denominator: Any) -> float | None:
    """Safe percentage: (numerator / denominator) * 100, rounded to 1 decimal."""
    if denominator is None or denominator == 0:
        return None
    pct = Decimal(str(numerator)) / Decimal(str(denominator)) * Decimal("100")
    return float(pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    """Safe division returning None when denominator is zero or None."""
    if denominator is None or denominator == 0:
        return None
    return float(Decimal(str(numerator)) / Decimal(str(denominator)))


def _percentage_change(current: Any, previous: Any) -> float | None:
    """Return period-over-period percentage change, or None when undefined."""
    if previous is None or previous == 0 or current is None:
        return None
    change = (Decimal(str(current)) - Decimal(str(previous))) / Decimal(str(previous)) * Decimal("100")
    return float(change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _percentage_point_change(current: Any, previous: Any) -> float | None:
    """Return percentage-point delta for rate metrics."""
    if current is None or previous is None:
        return None
    delta = Decimal(str(current)) - Decimal(str(previous))
    return float(delta.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _get_order_query(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: Any,
    date_to: Any,
):
    query = db.query(Order).filter(Order.organization_id == organization_id)
    if store_id is not None:
        query = query.filter(Order.store_id == store_id)
    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at < date_to)
    return query


def _overview_metrics(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: Any,
    date_to: Any,
) -> dict[str, Any]:
    """Compute overview metrics for one exact cohort."""
    base = _get_order_query(db, organization_id, store_id, date_from, date_to)
    total_orders = base.count()
    confirmed_orders = base.filter(
        Order.lifecycle_status.in_(["confirmed", "shipped", "delivered"])
    ).count()
    shipped_orders = base.filter(
        Order.lifecycle_status.in_(["shipped", "delivered"])
    ).count()
    delivered_orders = base.filter(Order.lifecycle_status == "delivered").count()
    cancelled_orders = base.filter(Order.lifecycle_status == "cancelled").count()
    returned_orders = base.filter(Order.lifecycle_status == "returned").count()
    unknown_orders = base.filter(Order.lifecycle_status == "unknown").count()

    gross_order_value = base.with_entities(func.sum(Order.total_amount)).scalar() or 0
    delivered_revenue = base.filter(
        Order.lifecycle_status == "delivered"
    ).with_entities(func.sum(Order.total_amount)).scalar() or 0

    return {
        "total_orders": total_orders,
        "confirmed_orders": confirmed_orders,
        "shipped_orders": shipped_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
        "returned_orders": returned_orders,
        "unknown_orders": unknown_orders,
        "confirmation_rate": _safe_percentage(confirmed_orders, total_orders),
        "delivery_rate": _safe_percentage(delivered_orders, shipped_orders),
        "cancellation_rate": _safe_percentage(cancelled_orders, total_orders),
        "return_rate": _safe_percentage(returned_orders, shipped_orders),
        "gross_order_value": float(gross_order_value),
        "delivered_revenue": float(delivered_revenue),
        "delivered_aov": _safe_div(delivered_revenue, delivered_orders),
    }


def get_dropshipping_overview(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: Any,
    date_to: Any,
) -> dict[str, Any]:
    """Get dropshipping overview and optional previous-period comparison."""
    current = _overview_metrics(db, organization_id, store_id, date_from, date_to)
    current["comparison"] = None

    if date_from is None or date_to is None:
        return current

    duration = date_to - date_from
    if duration.total_seconds() <= 0:
        return current

    previous_from = date_from - duration
    previous_to = date_from
    previous = _overview_metrics(
        db,
        organization_id,
        store_id,
        previous_from,
        previous_to,
    )

    current_profitability = get_profitability(
        db, organization_id, store_id, date_from, date_to
    )
    previous_profitability = get_profitability(
        db, organization_id, store_id, previous_from, previous_to
    )

    current["comparison"] = {
        "previous_date_from": previous_from.isoformat(),
        "previous_date_to": previous_to.isoformat(),
        "total_orders_pct": _percentage_change(current["total_orders"], previous["total_orders"]),
        "delivered_orders_pct": _percentage_change(current["delivered_orders"], previous["delivered_orders"]),
        "delivered_revenue_pct": _percentage_change(current["delivered_revenue"], previous["delivered_revenue"]),
        "delivered_aov_pct": _percentage_change(current["delivered_aov"], previous["delivered_aov"]),
        "delivery_rate_pp": _percentage_point_change(current["delivery_rate"], previous["delivery_rate"]),
        "cancellation_rate_pp": _percentage_point_change(current["cancellation_rate"], previous["cancellation_rate"]),
        "gross_profit_pct": _percentage_change(current_profitability["gross_profit"], previous_profitability["gross_profit"]),
        "gross_margin_pp": _percentage_point_change(current_profitability["gross_margin"], previous_profitability["gross_margin"]),
    }
    return current


def get_profitability(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: Any,
    date_to: Any,
) -> dict[str, Any]:
    """Get profitability metrics scoped to delivered orders."""
    delivered_base = db.query(Order).filter(
        Order.organization_id == organization_id,
        Order.lifecycle_status == "delivered",
    )
    if store_id is not None:
        delivered_base = delivered_base.filter(Order.store_id == store_id)
    if date_from:
        delivered_base = delivered_base.filter(Order.created_at >= date_from)
    if date_to:
        delivered_base = delivered_base.filter(Order.created_at < date_to)

    delivered_revenue = delivered_base.with_entities(func.sum(Order.total_amount)).scalar() or 0
    delivered_orders_count = delivered_base.count()
    delivered_order_ids = {row[0] for row in delivered_base.with_entities(Order.id).all()}

    if delivered_order_ids:
        order_items = db.query(OrderItem).filter(OrderItem.order_id.in_(delivered_order_ids))
    else:
        order_items = db.query(OrderItem).filter(OrderItem.id == -1)

    total_cogs = order_items.with_entities(
        func.sum(OrderItem.unit_cost * OrderItem.quantity)
    ).scalar() or 0
    cost_item_count = order_items.with_entities(func.count(OrderItem.id)).scalar() or 0
    items_with_cost_count = order_items.filter(OrderItem.unit_cost.isnot(None)).count()

    cost_completeness_pct = (
        _safe_percentage(items_with_cost_count, cost_item_count)
        if cost_item_count > 0
        else 0.0
    )

    gross_profit = float(Decimal(str(delivered_revenue)) - Decimal(str(total_cogs)))
    gross_margin = _safe_percentage(gross_profit, delivered_revenue)
    profit_per_order = _safe_div(gross_profit, delivered_orders_count)
    profitability_complete = cost_item_count > 0 and cost_completeness_pct == 100.0

    return {
        "delivered_revenue": float(delivered_revenue),
        "total_cogs": float(total_cogs),
        "gross_profit": gross_profit,
        "gross_margin": gross_margin,
        "profit_per_delivered_order": profit_per_order,
        "delivered_orders_count": delivered_orders_count,
        "cost_completeness_pct": cost_completeness_pct,
        "profitability_complete": profitability_complete,
    }


def get_product_profitability(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: Any,
    date_to: Any,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get product-level profitability from delivered orders only."""
    query = (
        db.query(
            Product.id.label("product_id"),
            Product.title.label("title"),
            Product.cost.label("product_cost"),
            func.min(OrderItem.sku).label("sku"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units_delivered"),
            func.coalesce(func.sum(OrderItem.unit_price * OrderItem.quantity), 0).label("delivered_revenue"),
            func.coalesce(func.sum(OrderItem.unit_cost * OrderItem.quantity), 0).label("total_cogs"),
            func.count(OrderItem.id).label("cost_item_count"),
            func.count(OrderItem.unit_cost).label("items_with_cost_count"),
        )
        .join(OrderItem, Product.id == OrderItem.product_id)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Product.organization_id == organization_id,
            Order.organization_id == organization_id,
            Order.lifecycle_status == "delivered",
        )
    )

    if store_id is not None:
        query = query.filter(
            Product.store_id == store_id,
            Order.store_id == store_id,
            OrderItem.store_id == store_id,
        )
    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at < date_to)

    results = (
        query.group_by(Product.id, Product.title, Product.cost)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )

    products: list[dict[str, Any]] = []
    for row in results:
        revenue = float(row.delivered_revenue)
        cogs = float(row.total_cogs or 0)
        gross_profit = revenue - cogs
        completeness = (
            _safe_percentage(row.items_with_cost_count, row.cost_item_count)
            if row.cost_item_count
            else 0.0
        )
        products.append(
            {
                "product_id": row.product_id,
                "title": row.title,
                "sku": row.sku,
                "cost": float(row.product_cost) if row.product_cost is not None else None,
                "units_delivered": int(row.units_delivered),
                "delivered_revenue": revenue,
                "total_cogs": cogs,
                "gross_profit": gross_profit,
                "gross_margin": _safe_percentage(gross_profit, revenue),
                "cost_completeness_pct": completeness,
                "profitability_complete": bool(row.cost_item_count) and completeness == 100.0,
            }
        )

    return products


def get_order_funnel(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: Any,
    date_to: Any,
) -> dict[str, Any]:
    """Get order funnel with cumulative lifecycle semantics."""
    base = _get_order_query(db, organization_id, store_id, date_from, date_to)
    total = base.count()
    confirmed = base.filter(
        Order.lifecycle_status.in_(["confirmed", "shipped", "delivered"])
    ).count()
    shipped = base.filter(
        Order.lifecycle_status.in_(["shipped", "delivered"])
    ).count()
    delivered = base.filter(Order.lifecycle_status == "delivered").count()
    cancelled = base.filter(Order.lifecycle_status == "cancelled").count()
    returned = base.filter(Order.lifecycle_status == "returned").count()
    unknown = base.filter(Order.lifecycle_status == "unknown").count()

    return {
        "total": total,
        "confirmed": confirmed,
        "shipped": shipped,
        "delivered": delivered,
        "cancelled": cancelled,
        "returned": returned,
        "unknown": unknown,
    }
