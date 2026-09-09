"""Dropshipping analytics service.

Provides profit-oriented analytics for dropshipping operations.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Order, OrderItem, Product

DateBound = datetime | None


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    """Safe division returning None when denominator is zero or None."""
    if denominator is None or denominator == 0:
        return None
    return float(Decimal(str(numerator)) / Decimal(str(denominator)))


def _safe_percentage(numerator: Any, denominator: Any) -> float | None:
    """Safe percentage calculation expressed as a percentage value."""
    result = _safe_div(numerator, denominator)
    if result is None:
        return None
    return float(
        (Decimal(str(result)) * Decimal("100")).quantize(
            Decimal("0.1"),
            rounding=ROUND_HALF_UP,
        )
    )


def _apply_order_scope(
    query,
    organization_id: int,
    store_id: int | None,
    date_from: DateBound,
    date_to: DateBound,
):
    query = query.filter(Order.organization_id == organization_id)
    if store_id is not None:
        query = query.filter(Order.store_id == store_id)
    if date_from is not None:
        query = query.filter(Order.created_at >= date_from)
    if date_to is not None:
        query = query.filter(Order.created_at < date_to)
    return query


def _delivered_orders_query(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: DateBound,
    date_to: DateBound,
):
    query = db.query(Order).filter(Order.lifecycle_status == "delivered")
    return _apply_order_scope(
        query,
        organization_id,
        store_id,
        date_from,
        date_to,
    )


def _delivered_items_query(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: DateBound,
    date_to: DateBound,
):
    query = (
        db.query(OrderItem)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            OrderItem.organization_id == organization_id,
            Order.organization_id == organization_id,
            Order.lifecycle_status == "delivered",
        )
    )
    if store_id is not None:
        query = query.filter(
            OrderItem.store_id == store_id,
            Order.store_id == store_id,
        )
    if date_from is not None:
        query = query.filter(Order.created_at >= date_from)
    if date_to is not None:
        query = query.filter(Order.created_at < date_to)
    return query


def get_dropshipping_overview(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: DateBound,
    date_to: DateBound,
) -> dict[str, Any]:
    """Get dropshipping overview metrics for one scoped order cohort."""
    orders = _apply_order_scope(
        db.query(Order),
        organization_id,
        store_id,
        date_from,
        date_to,
    )

    total_orders = orders.count()
    confirmed_orders = orders.filter(
        Order.lifecycle_status == "confirmed"
    ).count()
    shipped_orders = orders.filter(
        Order.lifecycle_status == "shipped"
    ).count()
    delivered_orders = orders.filter(
        Order.lifecycle_status == "delivered"
    ).count()
    cancelled_orders = orders.filter(
        Order.lifecycle_status == "cancelled"
    ).count()
    returned_orders = orders.filter(
        Order.lifecycle_status == "returned"
    ).count()
    unknown_orders = orders.filter(
        Order.lifecycle_status == "unknown"
    ).count()

    confirmation_rate = _safe_percentage(confirmed_orders, total_orders)
    delivery_rate = _safe_percentage(delivered_orders, shipped_orders)
    cancellation_rate = _safe_percentage(cancelled_orders, total_orders)
    return_rate = _safe_percentage(returned_orders, shipped_orders)

    gross_order_value = (
        orders.filter(
            Order.lifecycle_status.in_(
                ["pending", "confirmed", "shipped", "delivered"]
            )
        )
        .with_entities(func.sum(Order.total_amount))
        .scalar()
        or 0
    )

    delivered_revenue = (
        orders.filter(Order.lifecycle_status == "delivered")
        .with_entities(func.sum(Order.total_amount))
        .scalar()
        or 0
    )

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
    date_from: DateBound,
    date_to: DateBound,
) -> dict[str, Any]:
    """Get profitability using only delivered orders in the selected range."""
    orders = _delivered_orders_query(
        db,
        organization_id,
        store_id,
        date_from,
        date_to,
    )
    delivered_revenue = (
        orders.with_entities(func.sum(Order.total_amount)).scalar() or 0
    )
    delivered_orders_count = orders.count()

    order_items = _delivered_items_query(
        db,
        organization_id,
        store_id,
        date_from,
        date_to,
    )
    total_cogs = (
        order_items.with_entities(
            func.sum(OrderItem.unit_cost * OrderItem.quantity)
        ).scalar()
        or 0
    )

    total_items = order_items.count()
    items_with_cost_count = order_items.filter(
        OrderItem.unit_cost.isnot(None)
    ).count()
    cost_completeness_pct = (
        _safe_percentage(items_with_cost_count, total_items)
        if total_items > 0
        else 0.0
    )

    gross_profit = float(
        Decimal(str(delivered_revenue)) - Decimal(str(total_cogs))
    )
    gross_margin = _safe_percentage(gross_profit, delivered_revenue)
    profit_per_order = _safe_div(gross_profit, delivered_orders_count)

    return {
        "delivered_revenue": float(delivered_revenue),
        "total_cogs": float(total_cogs),
        "gross_profit": gross_profit,
        "gross_margin": gross_margin,
        "profit_per_delivered_order": profit_per_order,
        "delivered_orders_count": delivered_orders_count,
        "cost_completeness_pct": cost_completeness_pct,
    }


def get_product_profitability(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: DateBound,
    date_to: DateBound,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get delivered product profitability for the selected range."""
    revenue_expr = func.coalesce(
        func.sum(OrderItem.unit_price * OrderItem.quantity),
        0,
    )
    cogs_expr = func.coalesce(
        func.sum(OrderItem.unit_cost * OrderItem.quantity),
        0,
    )

    query = (
        db.query(
            Product.id,
            Product.title,
            Product.sku,
            Product.cost,
            func.coalesce(func.sum(OrderItem.quantity), 0).label(
                "units_delivered"
            ),
            revenue_expr.label("delivered_revenue"),
            cogs_expr.label("total_cogs"),
        )
        .join(OrderItem, Product.id == OrderItem.product_id)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Product.organization_id == organization_id,
            OrderItem.organization_id == organization_id,
            Order.organization_id == organization_id,
            Order.lifecycle_status == "delivered",
        )
    )

    if store_id is not None:
        query = query.filter(
            Product.store_id == store_id,
            OrderItem.store_id == store_id,
            Order.store_id == store_id,
        )
    if date_from is not None:
        query = query.filter(Order.created_at >= date_from)
    if date_to is not None:
        query = query.filter(Order.created_at < date_to)

    results = (
        query.group_by(Product.id, Product.title, Product.sku, Product.cost)
        .order_by(revenue_expr.desc())
        .limit(limit)
        .all()
    )

    products: list[dict[str, Any]] = []
    for row in results:
        revenue = float(row.delivered_revenue or 0)
        cogs = float(row.total_cogs or 0)
        gross_profit = revenue - cogs
        products.append(
            {
                "product_id": row.id,
                "title": row.title,
                "sku": row.sku,
                "cost": float(row.cost) if row.cost is not None else None,
                "units_delivered": int(row.units_delivered or 0),
                "delivered_revenue": revenue,
                "total_cogs": cogs,
                "gross_profit": gross_profit,
                "gross_margin": _safe_percentage(gross_profit, revenue),
            }
        )

    return products


def get_order_funnel(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: DateBound,
    date_to: DateBound,
) -> dict[str, Any]:
    """Get order funnel metrics."""
    query = _apply_order_scope(
        db.query(Order),
        organization_id,
        store_id,
        date_from,
        date_to,
    )

    return {
        "total": query.count(),
        "confirmed": query.filter(
            Order.lifecycle_status == "confirmed"
        ).count(),
        "shipped": query.filter(
            Order.lifecycle_status == "shipped"
        ).count(),
        "delivered": query.filter(
            Order.lifecycle_status == "delivered"
        ).count(),
        "cancelled": query.filter(
            Order.lifecycle_status == "cancelled"
        ).count(),
        "returned": query.filter(
            Order.lifecycle_status == "returned"
        ).count(),
    }
