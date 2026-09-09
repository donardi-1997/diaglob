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

from ..models import Order, OrderItem, Product, Store


def _safe_percentage(numerator: Any, denominator: Any) -> float | None:
    """Safe percentage: (numerator / denominator) * 100, rounded to 1 decimal.
    
    Returns None when denominator is zero or None.
    Never returns fake 0 when the metric is undefined.
    """
    if denominator is None or denominator == 0:
        return None
    pct = Decimal(str(numerator)) / Decimal(str(denominator)) * Decimal("100")
    return float(pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    """Safe division returning None when denominator is zero or None."""
    if denominator is None or denominator == 0:
        return None
    return float(Decimal(str(numerator)) / Decimal(str(denominator)))


def _get_order_query(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: str | None,
    date_to: str | None,
):
    """Build a base Order query with org/store/date filters."""
    query = db.query(Order).filter(
        Order.organization_id == organization_id,
    )
    if store_id is not None:
        query = query.filter(Order.store_id == store_id)
    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at < date_to)
    return query


def get_dropshipping_overview(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: str | None,
    date_to: str | None,
) -> dict[str, Any]:
    """Get dropshipping overview metrics with cumulative funnel semantics."""
    base = _get_order_query(db, organization_id, store_id, date_from, date_to)
    total_orders = base.count()

    # Cumulative funnel: delivered counts in shipped, shipped+delivered count in confirmed
    confirmed_orders = base.filter(
        Order.lifecycle_status.in_(["confirmed", "shipped", "delivered"])
    ).count()

    shipped_orders = base.filter(
        Order.lifecycle_status.in_(["shipped", "delivered"])
    ).count()

    delivered_orders = base.filter(
        Order.lifecycle_status == "delivered"
    ).count()

    cancelled_orders = base.filter(
        Order.lifecycle_status == "cancelled"
    ).count()

    returned_orders = base.filter(
        Order.lifecycle_status == "returned"
    ).count()

    unknown_orders = base.filter(
        Order.lifecycle_status == "unknown"
    ).count()

    # Rates (percentage formula: (n/d)*100, null if d=0)
    confirmation_rate = _safe_percentage(confirmed_orders, total_orders)
    delivery_rate = _safe_percentage(delivered_orders, shipped_orders)
    cancellation_rate = _safe_percentage(cancelled_orders, total_orders)
    return_rate = _safe_percentage(returned_orders, shipped_orders)

    # Revenue
    gross_order_value = base.with_entities(
        func.sum(Order.total_amount)
    ).scalar() or 0

    delivered_revenue = base.filter(
        Order.lifecycle_status == "delivered"
    ).with_entities(
        func.sum(Order.total_amount)
    ).scalar() or 0

    delivered_aov = _safe_div(delivered_revenue, delivered_orders)

    return {
        "total_orders": total_orders,
        "confirmed_orders": confirmed_orders,
        "shipped_orders": shipped_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
        "returned_orders": returned_orders,
        "unknown_orders": unknown_orders,
        "confirmation_rate": confirmation_rate,
        "delivery_rate": delivery_rate,
        "cancellation_rate": cancellation_rate,
        "return_rate": return_rate,
        "gross_order_value": float(gross_order_value),
        "delivered_revenue": float(delivered_revenue),
        "delivered_aov": delivered_aov,
    }


def get_profitability(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: str | None,
    date_to: str | None,
) -> dict[str, Any]:
    """Get profitability metrics.

    COGS is scoped to delivered orders in the same period as revenue.
    """
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

    delivered_revenue = delivered_base.with_entities(
        func.sum(Order.total_amount)
    ).scalar() or 0

    delivered_orders_count = delivered_base.count()

    delivered_order_ids = delivered_base.with_entities(Order.id).all()
    delivered_order_id_set = {row[0] for row in delivered_order_ids}

    # COGS from order items belonging to delivered orders in the selected period
    if delivered_order_id_set:
        order_items = db.query(OrderItem).filter(
            OrderItem.order_id.in_(delivered_order_id_set),
        )
    else:
        order_items = db.query(OrderItem).filter(
            OrderItem.id == -1,  # impossible ID => empty
        )

    total_cogs = order_items.with_entities(
        func.sum(OrderItem.unit_cost * OrderItem.quantity)
    ).scalar() or 0

    cost_completeness = order_items.with_entities(
        func.count(OrderItem.id)
    ).scalar() or 0

    items_with_cost = db.query(OrderItem).filter(
        OrderItem.order_id.in_(delivered_order_id_set),
        OrderItem.unit_cost.isnot(None),
    )

    items_with_cost_count = items_with_cost.count()

    cost_completeness_pct = (
        _safe_percentage(items_with_cost_count, cost_completeness)
        if cost_completeness > 0
        else 0.0
    )

    # Gross profit
    gross_profit = float(
        Decimal(str(delivered_revenue)) - Decimal(str(total_cogs))
    )

    gross_margin = _safe_percentage(gross_profit, delivered_revenue)
    profit_per_order = _safe_div(gross_profit, delivered_orders_count)

    # Profitability is only reliable if all costs are complete
    profitability_complete = cost_completeness_pct == 100.0 if cost_completeness > 0 else False

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
    date_from: str | None,
    date_to: str | None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get product-level profitability.

    Uses OrderItem as the historical source since SKU belongs to OrderItem.
    """
    query = (
        db.query(
            Product.id.label("product_id"),
            Product.title.label("title"),
            Product.cost.label("product_cost"),
            func.coalesce(func.sum(OrderItem.quantity), 0).label("units_ordered"),
            func.coalesce(func.sum(OrderItem.unit_cost * OrderItem.quantity), 0).label("total_cogs"),
            func.coalesce(func.sum(OrderItem.unit_price * OrderItem.quantity), 0).label("total_revenue"),
        )
        .outerjoin(OrderItem, Product.id == OrderItem.product_id)
        .outerjoin(Order, OrderItem.order_id == Order.id)
        .filter(Product.organization_id == organization_id)
    )

    if store_id is not None:
        query = query.filter(Product.store_id == store_id)

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

    return [
        {
            "product_id": r.product_id,
            "title": r.title,
            "cost": float(r.product_cost) if r.product_cost else None,
            "units_ordered": int(r.units_ordered),
            "total_revenue": float(r.total_revenue),
            "total_cogs": float(r.total_cogs) if r.total_cogs else 0,
            "gross_profit": float(r.total_revenue) - (float(r.total_cogs) if r.total_cogs else 0),
        }
        for r in results
    ]


def get_order_funnel(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: str | None,
    date_to: str | None,
) -> dict[str, Any]:
    """Get order funnel with cumulative lifecycle semantics.

    Cumulative: delivered counts in shipped, shipped+delivered count in confirmed.
    """
    base = _get_order_query(db, organization_id, store_id, date_from, date_to)
    total = base.count()

    confirmed = base.filter(
        Order.lifecycle_status.in_(["confirmed", "shipped", "delivered"])
    ).count()

    shipped = base.filter(
        Order.lifecycle_status.in_(["shipped", "delivered"])
    ).count()

    delivered = base.filter(
        Order.lifecycle_status == "delivered"
    ).count()

    cancelled = base.filter(
        Order.lifecycle_status == "cancelled"
    ).count()

    returned = base.filter(
        Order.lifecycle_status == "returned"
    ).count()

    unknown = base.filter(
        Order.lifecycle_status == "unknown"
    ).count()

    return {
        "total": total,
        "confirmed": confirmed,
        "shipped": shipped,
        "delivered": delivered,
        "cancelled": cancelled,
        "returned": returned,
        "unknown": unknown,
    }
