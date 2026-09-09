"""Dropshipping analytics service.

Provides profit-oriented analytics for dropshipping operations.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import case, func, and_, or_, cast, String
from sqlalchemy.orm import Session

from ..models import Order, OrderItem, Product, ProductVariant, Store


def _safe_div(numerator: Any, denominator: Any) -> float | None:
    """Safe division returning None when denominator is zero or None."""
    if denominator is None or denominator == 0:
        return None
    return float(Decimal(str(numerator)) / Decimal(str(denominator)))


def _safe_percentage(numerator: Any, denominator: Any) -> float | None:
    """Safe percentage calculation."""
    result = _safe_div(numerator, denominator)
    if result is None:
        return None
    return float(
        Decimal(str(result)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
    )


def _sum_case(
    db: Session,
    model,
    organization_id: int,
    store_id: int | None,
    date_from: str | None,
    date_to: str | None,
    column: str,
    condition: str,
) -> int:
    """Sum a column with a CASE condition."""
    query = db.query(
        func.sum(
            case(
                (getattr(model, "lifecycle_status") == condition, getattr(model, column)),
                else_=0,
            )
        )
    )
    query = query.filter(model.organization_id == organization_id)
    if store_id is not None:
        query = query.filter(model.store_id == store_id)
    if date_from:
        query = query.filter(model.created_at >= date_from)
    if date_to:
        query = query.filter(model.created_at < date_to)
    return query.scalar() or 0


def get_dropshipping_overview(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: str | None,
    date_to: str | None,
) -> dict[str, Any]:
    """Get dropshipping overview metrics."""
    # Order counts by lifecycle
    orders = db.query(Order).filter(
        Order.organization_id == organization_id,
    )
    if store_id is not None:
        orders = orders.filter(Order.store_id == store_id)
    if date_from:
        orders = orders.filter(Order.created_at >= date_from)
    if date_to:
        orders = orders.filter(Order.created_at < date_to)

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

    # Rates
    confirmation_rate = _safe_percentage(confirmed_orders, total_orders)
    delivery_rate = _safe_percentage(delivered_orders, shipped_orders)
    cancellation_rate = _safe_percentage(cancelled_orders, total_orders)
    return_rate = _safe_percentage(returned_orders, shipped_orders)

    # Revenue
    gross_order_value = orders.filter(
        Order.lifecycle_status.in_(["pending", "confirmed", "shipped", "delivered"])
    ).with_entities(
        func.sum(Order.total_amount)
    ).scalar() or 0

    delivered_revenue = orders.filter(
        Order.lifecycle_status == "delivered"
    ).with_entities(
        func.sum(Order.total_amount)
    ).scalar() or 0

    # AOV
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
    """Get profitability metrics."""
    # Get delivered revenue
    orders = db.query(Order).filter(
        Order.organization_id == organization_id,
        Order.lifecycle_status == "delivered",
    )
    if store_id is not None:
        orders = orders.filter(Order.store_id == store_id)
    if date_from:
        orders = orders.filter(Order.created_at >= date_from)
    if date_to:
        orders = orders.filter(Order.created_at < date_to)

    delivered_revenue = orders.with_entities(
        func.sum(Order.total_amount)
    ).scalar() or 0

    delivered_orders_count = orders.count()

    # COGS from order items
    order_items = db.query(OrderItem).filter(
        OrderItem.organization_id == organization_id,
    )
    if store_id is not None:
        order_items = order_items.filter(OrderItem.store_id == store_id)

    total_cogs = order_items.with_entities(
        func.sum(OrderItem.unit_cost * OrderItem.quantity)
    ).scalar() or 0

    cost_completeness = order_items.with_entities(
        func.count(OrderItem.id)
    ).scalar() or 0

    items_with_cost = db.query(OrderItem).filter(
        OrderItem.organization_id == organization_id,
        OrderItem.unit_cost.isnot(None),
    )
    if store_id is not None:
        items_with_cost = items_with_cost.filter(
            OrderItem.store_id == store_id
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
    date_from: str | None,
    date_to: str | None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get product-level profitability."""
    query = db.query(
        Product.id,
        Product.title,
        Product.sku,
        Product.cost,
        func.coalesce(func.sum(OrderItem.quantity), 0).label("units_ordered"),
        func.coalesce(func.sum(OrderItem.unit_cost * OrderItem.quantity), 0).label("total_cogs"),
    ).outerjoin(
        OrderItem, Product.id == OrderItem.product_id
    ).outerjoin(
        Order, OrderItem.order_id == Order.id
    ).filter(
        Product.organization_id == organization_id,
    )

    if store_id is not None:
        query = query.filter(Product.store_id == store_id)

    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at < date_to)

    results = (
        query.group_by(Product.id, Product.title, Product.sku, Product.cost)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "product_id": r.id,
            "title": r.title,
            "sku": r.sku,
            "cost": float(r.cost) if r.cost else None,
            "units_ordered": int(r.units_ordered),
            "total_cogs": float(r.total_cogs) if r.total_cogs else 0,
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
    """Get order funnel metrics."""
    query = db.query(Order).filter(
        Order.organization_id == organization_id,
    )
    if store_id is not None:
        query = query.filter(Order.store_id == store_id)
    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at < date_to)

    total = query.count()

    confirmed = query.filter(
        Order.lifecycle_status == "confirmed"
    ).count()

    shipped = query.filter(
        Order.lifecycle_status == "shipped"
    ).count()

    delivered = query.filter(
        Order.lifecycle_status == "delivered"
    ).count()

    cancelled = query.filter(
        Order.lifecycle_status == "cancelled"
    ).count()

    returned = query.filter(
        Order.lifecycle_status == "returned"
    ).count()

    return {
        "total": total,
        "confirmed": confirmed,
        "shipped": shipped,
        "delivered": delivered,
        "cancelled": cancelled,
        "returned": returned,
    }
