"""Dropshipping analytics service.

Provides profit-oriented analytics for dropshipping operations.

Lifecycle semantics:
- lifecycle_status is a mutually exclusive current-state field
- For cumulative funnel, delivered counts in shipped and confirmed stages
- Cancelled/returned are side outcomes, not part of the forward funnel
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from ..models import Order, OrderItem, Product, ProductVariant


FORWARD_CONFIRMED = ["confirmed", "shipped", "delivered"]
FORWARD_SHIPPED = ["shipped", "delivered"]


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
    change = (
        (Decimal(str(current)) - Decimal(str(previous)))
        / Decimal(str(previous))
        * Decimal("100")
    )
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
    confirmed_orders = base.filter(Order.lifecycle_status.in_(FORWARD_CONFIRMED)).count()
    shipped_orders = base.filter(Order.lifecycle_status.in_(FORWARD_SHIPPED)).count()
    delivered_orders = base.filter(Order.lifecycle_status == "delivered").count()
    cancelled_orders = base.filter(Order.lifecycle_status == "cancelled").count()
    returned_orders = base.filter(Order.lifecycle_status == "returned").count()
    unknown_orders = base.filter(Order.lifecycle_status == "unknown").count()

    gross_order_value = base.with_entities(func.sum(Order.total_amount)).scalar() or 0
    delivered_revenue = (
        base.filter(Order.lifecycle_status == "delivered")
        .with_entities(func.sum(Order.total_amount))
        .scalar()
        or 0
    )

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
        "total_orders_pct": _percentage_change(
            current["total_orders"], previous["total_orders"]
        ),
        "delivered_orders_pct": _percentage_change(
            current["delivered_orders"], previous["delivered_orders"]
        ),
        "delivered_revenue_pct": _percentage_change(
            current["delivered_revenue"], previous["delivered_revenue"]
        ),
        "delivered_aov_pct": _percentage_change(
            current["delivered_aov"], previous["delivered_aov"]
        ),
        "delivery_rate_pp": _percentage_point_change(
            current["delivery_rate"], previous["delivery_rate"]
        ),
        "cancellation_rate_pp": _percentage_point_change(
            current["cancellation_rate"], previous["cancellation_rate"]
        ),
        "gross_profit_pct": _percentage_change(
            current_profitability["gross_profit"],
            previous_profitability["gross_profit"],
        ),
        "gross_margin_pp": _percentage_point_change(
            current_profitability["gross_margin"],
            previous_profitability["gross_margin"],
        ),
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

    delivered_revenue = (
        delivered_base.with_entities(func.sum(Order.total_amount)).scalar() or 0
    )
    delivered_orders_count = delivered_base.count()
    delivered_order_ids = {
        row[0] for row in delivered_base.with_entities(Order.id).all()
    }

    if delivered_order_ids:
        order_items = db.query(OrderItem).filter(
            OrderItem.order_id.in_(delivered_order_ids),
            OrderItem.organization_id == organization_id,
        )
        if store_id is not None:
            order_items = order_items.filter(OrderItem.store_id == store_id)
    else:
        order_items = db.query(OrderItem).filter(OrderItem.id == -1)

    total_cogs = (
        order_items.with_entities(
            func.sum(OrderItem.unit_cost * OrderItem.quantity)
        ).scalar()
        or 0
    )
    cost_item_count = (
        order_items.with_entities(func.count(OrderItem.id)).scalar() or 0
    )
    items_with_cost_count = order_items.filter(
        OrderItem.unit_cost.isnot(None)
    ).count()

    cost_completeness_pct = (
        _safe_percentage(items_with_cost_count, cost_item_count)
        if cost_item_count > 0
        else 0.0
    )

    gross_profit = float(
        Decimal(str(delivered_revenue)) - Decimal(str(total_cogs))
    )
    gross_margin = _safe_percentage(gross_profit, delivered_revenue)
    profit_per_order = _safe_div(gross_profit, delivered_orders_count)
    profitability_complete = (
        cost_item_count > 0 and cost_completeness_pct == 100.0
    )

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


def _product_performance_rows(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: Any,
    date_to: Any,
    product_id: int | None = None,
):
    delivered = Order.lifecycle_status == "delivered"
    query = (
        db.query(
            Product.id.label("product_id"),
            Product.title.label("title"),
            Product.cost.label("product_cost"),
            func.min(OrderItem.sku).label("sku"),
            func.count(func.distinct(Order.id)).label("total_orders"),
            func.count(
                func.distinct(
                    case(
                        (Order.lifecycle_status.in_(FORWARD_CONFIRMED), Order.id),
                        else_=None,
                    )
                )
            ).label("confirmed_orders"),
            func.count(
                func.distinct(
                    case(
                        (Order.lifecycle_status.in_(FORWARD_SHIPPED), Order.id),
                        else_=None,
                    )
                )
            ).label("shipped_orders"),
            func.count(
                func.distinct(case((delivered, Order.id), else_=None))
            ).label("delivered_orders"),
            func.count(
                func.distinct(
                    case(
                        (Order.lifecycle_status == "cancelled", Order.id),
                        else_=None,
                    )
                )
            ).label("cancelled_orders"),
            func.count(
                func.distinct(
                    case(
                        (Order.lifecycle_status == "returned", Order.id),
                        else_=None,
                    )
                )
            ).label("returned_orders"),
            func.coalesce(
                func.sum(case((delivered, OrderItem.quantity), else_=0)), 0
            ).label("units_delivered"),
            func.coalesce(
                func.sum(
                    case(
                        (delivered, OrderItem.unit_price * OrderItem.quantity),
                        else_=0,
                    )
                ),
                0,
            ).label("delivered_revenue"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            delivered & OrderItem.unit_cost.isnot(None),
                            OrderItem.unit_cost * OrderItem.quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("total_cogs"),
            func.coalesce(
                func.sum(case((delivered, 1), else_=0)), 0
            ).label("cost_item_count"),
            func.coalesce(
                func.sum(
                    case(
                        (delivered & OrderItem.unit_cost.isnot(None), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("items_with_cost_count"),
        )
        .join(OrderItem, Product.id == OrderItem.product_id)
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Product.organization_id == organization_id,
            Order.organization_id == organization_id,
            OrderItem.organization_id == organization_id,
        )
    )

    if store_id is not None:
        query = query.filter(
            Product.store_id == store_id,
            Order.store_id == store_id,
            OrderItem.store_id == store_id,
        )
    if product_id is not None:
        query = query.filter(Product.id == product_id)
    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at < date_to)

    return query.group_by(Product.id, Product.title, Product.cost).all()


def _product_stock_by_id(
    db: Session,
    organization_id: int,
    store_id: int | None,
    product_ids: list[int],
) -> dict[int, int]:
    if not product_ids:
        return {}

    query = (
        db.query(
            ProductVariant.product_id,
            func.coalesce(func.sum(ProductVariant.inventory_quantity), 0),
        )
        .join(Product, ProductVariant.product_id == Product.id)
        .filter(
            Product.organization_id == organization_id,
            Product.id.in_(product_ids),
        )
    )
    if store_id is not None:
        query = query.filter(Product.store_id == store_id)

    return {
        int(product_id): int(inventory or 0)
        for product_id, inventory in query.group_by(ProductVariant.product_id).all()
    }


def _product_row_to_metrics(row, inventory_quantity: int = 0) -> dict[str, Any]:
    revenue = float(row.delivered_revenue or 0)
    cogs = float(row.total_cogs or 0)
    gross_profit = revenue - cogs
    cost_item_count = int(row.cost_item_count or 0)
    items_with_cost_count = int(row.items_with_cost_count or 0)
    completeness = (
        _safe_percentage(items_with_cost_count, cost_item_count)
        if cost_item_count
        else 0.0
    )
    units_delivered = int(row.units_delivered or 0)
    shipped_orders = int(row.shipped_orders or 0)
    total_orders = int(row.total_orders or 0)

    return {
        "product_id": int(row.product_id),
        "title": row.title,
        "sku": row.sku,
        "cost": float(row.product_cost) if row.product_cost is not None else None,
        "inventory_quantity": inventory_quantity,
        "total_orders": total_orders,
        "confirmed_orders": int(row.confirmed_orders or 0),
        "shipped_orders": shipped_orders,
        "delivered_orders": int(row.delivered_orders or 0),
        "cancelled_orders": int(row.cancelled_orders or 0),
        "returned_orders": int(row.returned_orders or 0),
        "units_delivered": units_delivered,
        "delivered_revenue": revenue,
        "total_cogs": cogs,
        "gross_profit": gross_profit,
        "gross_margin": _safe_percentage(gross_profit, revenue),
        "profit_per_unit": _safe_div(gross_profit, units_delivered),
        "delivery_rate": _safe_percentage(row.delivered_orders, shipped_orders),
        "cancellation_rate": _safe_percentage(row.cancelled_orders, total_orders),
        "return_rate": _safe_percentage(row.returned_orders, shipped_orders),
        "cost_completeness_pct": completeness,
        "profitability_complete": bool(cost_item_count) and completeness == 100.0,
        "revenue_share_pct": 0.0,
        "profit_share_pct": 0.0,
    }


def _zero_product_metrics(product: Product, inventory_quantity: int) -> dict[str, Any]:
    return {
        "product_id": product.id,
        "title": product.title,
        "sku": None,
        "cost": float(product.cost) if product.cost is not None else None,
        "inventory_quantity": inventory_quantity,
        "total_orders": 0,
        "confirmed_orders": 0,
        "shipped_orders": 0,
        "delivered_orders": 0,
        "cancelled_orders": 0,
        "returned_orders": 0,
        "units_delivered": 0,
        "delivered_revenue": 0.0,
        "total_cogs": 0.0,
        "gross_profit": 0.0,
        "gross_margin": None,
        "profit_per_unit": None,
        "delivery_rate": None,
        "cancellation_rate": None,
        "return_rate": None,
        "cost_completeness_pct": 0.0,
        "profitability_complete": False,
        "revenue_share_pct": 0.0,
        "profit_share_pct": 0.0,
    }


def get_product_profitability(
    db: Session,
    organization_id: int,
    store_id: int | None,
    date_from: Any,
    date_to: Any,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get lifecycle and profitability metrics by product.

    The historical response fields are preserved while lifecycle rates, profit per
    unit, inventory and store-level contribution are added for Product Analytics V2.
    """
    rows = _product_performance_rows(
        db, organization_id, store_id, date_from, date_to
    )
    product_ids = [int(row.product_id) for row in rows]
    inventory = _product_stock_by_id(
        db, organization_id, store_id, product_ids
    )
    products = [
        _product_row_to_metrics(row, inventory.get(int(row.product_id), 0))
        for row in rows
    ]

    total_revenue = sum(product["delivered_revenue"] for product in products)
    total_profit = sum(product["gross_profit"] for product in products)
    for product in products:
        product["revenue_share_pct"] = (
            _safe_percentage(product["delivered_revenue"], total_revenue) or 0.0
        )
        product["profit_share_pct"] = (
            _safe_percentage(product["gross_profit"], total_profit) or 0.0
        )

    products.sort(
        key=lambda item: (item["gross_profit"], item["delivered_revenue"]),
        reverse=True,
    )
    return products[:limit]


def _get_single_product_metrics(
    db: Session,
    organization_id: int,
    store_id: int,
    product: Product,
    date_from: Any,
    date_to: Any,
) -> dict[str, Any]:
    rows = _product_performance_rows(
        db,
        organization_id,
        store_id,
        date_from,
        date_to,
        product_id=product.id,
    )
    stock = _product_stock_by_id(
        db, organization_id, store_id, [product.id]
    ).get(product.id, 0)
    if not rows:
        return _zero_product_metrics(product, stock)
    return _product_row_to_metrics(rows[0], stock)


def _product_timeseries(
    db: Session,
    organization_id: int,
    store_id: int,
    product_id: int,
    date_from: Any,
    date_to: Any,
) -> list[dict[str, Any]]:
    delivered = Order.lifecycle_status == "delivered"
    day = func.date(Order.created_at)
    query = (
        db.query(
            day.label("day"),
            func.count(func.distinct(Order.id)).label("total_orders"),
            func.count(
                func.distinct(case((delivered, Order.id), else_=None))
            ).label("delivered_orders"),
            func.coalesce(
                func.sum(case((delivered, OrderItem.quantity), else_=0)), 0
            ).label("units_delivered"),
            func.coalesce(
                func.sum(
                    case(
                        (delivered, OrderItem.unit_price * OrderItem.quantity),
                        else_=0,
                    )
                ),
                0,
            ).label("delivered_revenue"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            delivered & OrderItem.unit_cost.isnot(None),
                            OrderItem.unit_cost * OrderItem.quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("total_cogs"),
        )
        .join(OrderItem, Order.id == OrderItem.order_id)
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
            OrderItem.organization_id == organization_id,
            OrderItem.store_id == store_id,
            OrderItem.product_id == product_id,
        )
    )
    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at < date_to)

    result = []
    for row in query.group_by(day).order_by(day).all():
        revenue = float(row.delivered_revenue or 0)
        cogs = float(row.total_cogs or 0)
        result.append(
            {
                "date": str(row.day),
                "total_orders": int(row.total_orders or 0),
                "delivered_orders": int(row.delivered_orders or 0),
                "units_delivered": int(row.units_delivered or 0),
                "delivered_revenue": revenue,
                "gross_profit": revenue - cogs,
            }
        )
    return result


def _variant_performance(
    db: Session,
    organization_id: int,
    store_id: int,
    product_id: int,
    date_from: Any,
    date_to: Any,
) -> list[dict[str, Any]]:
    delivered = Order.lifecycle_status == "delivered"
    query = (
        db.query(
            OrderItem.variant_id.label("variant_id"),
            func.min(OrderItem.sku).label("sku"),
            func.count(func.distinct(Order.id)).label("total_orders"),
            func.count(
                func.distinct(case((delivered, Order.id), else_=None))
            ).label("delivered_orders"),
            func.coalesce(
                func.sum(case((delivered, OrderItem.quantity), else_=0)), 0
            ).label("units_delivered"),
            func.coalesce(
                func.sum(
                    case(
                        (delivered, OrderItem.unit_price * OrderItem.quantity),
                        else_=0,
                    )
                ),
                0,
            ).label("delivered_revenue"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            delivered & OrderItem.unit_cost.isnot(None),
                            OrderItem.unit_cost * OrderItem.quantity,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("total_cogs"),
        )
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            OrderItem.organization_id == organization_id,
            OrderItem.store_id == store_id,
            OrderItem.product_id == product_id,
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
    )
    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at < date_to)

    performance = {}
    for row in query.group_by(OrderItem.variant_id).all():
        revenue = float(row.delivered_revenue or 0)
        cogs = float(row.total_cogs or 0)
        performance[row.variant_id] = {
            "variant_id": row.variant_id,
            "sku": row.sku,
            "total_orders": int(row.total_orders or 0),
            "delivered_orders": int(row.delivered_orders or 0),
            "units_delivered": int(row.units_delivered or 0),
            "delivered_revenue": revenue,
            "gross_profit": revenue - cogs,
        }

    variants = (
        db.query(ProductVariant)
        .join(Product, ProductVariant.product_id == Product.id)
        .filter(
            ProductVariant.product_id == product_id,
            Product.organization_id == organization_id,
            Product.store_id == store_id,
        )
        .order_by(ProductVariant.id)
        .all()
    )

    result = []
    known_ids = set()
    for variant in variants:
        known_ids.add(variant.id)
        metrics = performance.get(
            variant.id,
            {
                "variant_id": variant.id,
                "sku": None,
                "total_orders": 0,
                "delivered_orders": 0,
                "units_delivered": 0,
                "delivered_revenue": 0.0,
                "gross_profit": 0.0,
            },
        )
        result.append(
            {
                **metrics,
                "title": variant.title,
                "sku": metrics["sku"] or getattr(variant, "sku", None),
                "inventory_quantity": int(variant.inventory_quantity or 0),
            }
        )

    if None in performance:
        result.append(
            {
                **performance[None],
                "title": "Sin variante",
                "inventory_quantity": 0,
            }
        )

    for variant_id, metrics in performance.items():
        if variant_id is not None and variant_id not in known_ids:
            result.append(
                {
                    **metrics,
                    "title": f"Variante #{variant_id}",
                    "inventory_quantity": 0,
                }
            )

    result.sort(
        key=lambda item: (item["gross_profit"], item["delivered_revenue"]),
        reverse=True,
    )
    return result


def get_product_detail(
    db: Session,
    organization_id: int,
    store_id: int,
    product_id: int,
    date_from: Any,
    date_to: Any,
) -> dict[str, Any] | None:
    """Return detailed analytics for one product in the requested store."""
    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.organization_id == organization_id,
            Product.store_id == store_id,
        )
        .first()
    )
    if product is None:
        return None

    metrics = _get_single_product_metrics(
        db, organization_id, store_id, product, date_from, date_to
    )

    store_products = get_product_profitability(
        db, organization_id, store_id, date_from, date_to, limit=200
    )
    total_revenue = sum(item["delivered_revenue"] for item in store_products)
    total_profit = sum(item["gross_profit"] for item in store_products)
    metrics["revenue_share_pct"] = (
        _safe_percentage(metrics["delivered_revenue"], total_revenue) or 0.0
    )
    metrics["profit_share_pct"] = (
        _safe_percentage(metrics["gross_profit"], total_profit) or 0.0
    )

    comparison = None
    if date_from is not None and date_to is not None:
        duration = date_to - date_from
        if duration.total_seconds() > 0:
            previous_from = date_from - duration
            previous_to = date_from
            previous = _get_single_product_metrics(
                db,
                organization_id,
                store_id,
                product,
                previous_from,
                previous_to,
            )
            comparison = {
                "previous_date_from": previous_from.isoformat(),
                "previous_date_to": previous_to.isoformat(),
                "total_orders_pct": _percentage_change(
                    metrics["total_orders"], previous["total_orders"]
                ),
                "delivered_orders_pct": _percentage_change(
                    metrics["delivered_orders"], previous["delivered_orders"]
                ),
                "units_delivered_pct": _percentage_change(
                    metrics["units_delivered"], previous["units_delivered"]
                ),
                "delivered_revenue_pct": _percentage_change(
                    metrics["delivered_revenue"], previous["delivered_revenue"]
                ),
                "gross_profit_pct": _percentage_change(
                    metrics["gross_profit"], previous["gross_profit"]
                ),
                "delivery_rate_pp": _percentage_point_change(
                    metrics["delivery_rate"], previous["delivery_rate"]
                ),
                "cancellation_rate_pp": _percentage_point_change(
                    metrics["cancellation_rate"], previous["cancellation_rate"]
                ),
                "return_rate_pp": _percentage_point_change(
                    metrics["return_rate"], previous["return_rate"]
                ),
                "gross_margin_pp": _percentage_point_change(
                    metrics["gross_margin"], previous["gross_margin"]
                ),
            }

    return {
        "product": {
            "id": product.id,
            "title": product.title,
            "description": product.description,
        },
        "metrics": metrics,
        "comparison": comparison,
        "timeseries": _product_timeseries(
            db, organization_id, store_id, product_id, date_from, date_to
        ),
        "variants": _variant_performance(
            db, organization_id, store_id, product_id, date_from, date_to
        ),
    }


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
    confirmed = base.filter(Order.lifecycle_status.in_(FORWARD_CONFIRMED)).count()
    shipped = base.filter(Order.lifecycle_status.in_(FORWARD_SHIPPED)).count()
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
