"""Deterministic decision intelligence for dropshipping analytics.

This layer converts existing product analytics into explainable, structured
insights. It intentionally contains no LLM calls and performs no mutations.
"""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .dropshipping_analytics import get_product_profitability


SEVERITY_RANK = {
    "critical": 0,
    "warning": 1,
    "opportunity": 2,
    "positive": 3,
}

TYPE_PRIORITY = {
    "negative_margin": 0,
    "stockout": 1,
    "stock_runway": 2,
    "cost_incomplete": 3,
    "delivery_risk": 4,
    "cancellation_risk": 5,
    "return_risk": 6,
    "low_margin": 7,
    "revenue_concentration": 8,
    "profit_concentration": 9,
    "opportunity": 10,
    "winner": 11,
}


def _insight(
    *,
    type_: str,
    severity: str,
    product: dict[str, Any],
    title_key: str,
    reason_key: str,
    action_key: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    product_id = int(product["product_id"])
    return {
        "id": f"{type_}:{product_id}",
        "type": type_,
        "severity": severity,
        "product_id": product_id,
        "product_title": product["title"],
        "title_key": title_key,
        "reason_key": reason_key,
        "action_key": action_key,
        "evidence": evidence,
    }


def _is_at_most(value: Any, threshold: float) -> bool:
    return value is None or float(value) <= threshold


def _quality_gates(product: dict[str, Any], *, minimum_delivered: int) -> bool:
    gross_margin = product.get("gross_margin")
    delivery_rate = product.get("delivery_rate")
    cancellation_rate = product.get("cancellation_rate")
    return_rate = product.get("return_rate")
    return (
        bool(product.get("profitability_complete"))
        and int(product.get("total_orders") or 0) >= 5
        and int(product.get("delivered_orders") or 0) >= minimum_delivered
        and gross_margin is not None
        and float(gross_margin) >= 30.0
        and delivery_rate is not None
        and float(delivery_rate) >= 70.0
        and cancellation_rate is not None
        and float(cancellation_rate) <= 20.0
        and _is_at_most(return_rate, 10.0)
        and float(product.get("gross_profit") or 0) > 0
    )


def _bounded_period_days(
    date_from: datetime | None,
    date_to: datetime | None,
) -> float | None:
    if date_from is None or date_to is None:
        return None
    seconds = (date_to - date_from).total_seconds()
    if seconds <= 0:
        return None
    return seconds / 86400


def _magnitude_key(item: dict[str, Any]) -> float:
    evidence = item["evidence"]
    type_ = item["type"]
    if type_ == "negative_margin":
        return float(evidence.get("gross_profit") or 0)
    if type_ == "stock_runway":
        return float(evidence.get("stock_runway_days") or 0)
    if type_ == "delivery_risk":
        rate = float(evidence.get("delivery_rate") or 0)
        return -(100.0 - rate)
    if type_ == "cancellation_risk":
        return -float(evidence.get("cancellation_rate") or 0)
    if type_ == "return_risk":
        return -float(evidence.get("return_rate") or 0)
    if type_ == "revenue_concentration":
        return -float(evidence.get("revenue_share_pct") or 0)
    if type_ == "profit_concentration":
        return -float(evidence.get("profit_share_pct") or 0)
    if type_ in {"winner", "opportunity"}:
        return -float(evidence.get("gross_profit") or 0)
    return 0.0


def _sort_key(item: dict[str, Any]):
    return (
        SEVERITY_RANK[item["severity"]],
        TYPE_PRIORITY[item["type"]],
        _magnitude_key(item),
        str(item.get("product_title") or "").casefold(),
        int(item["product_id"]),
    )


def _evaluate_product(
    product: dict[str, Any],
    *,
    period_days: float | None,
    revenue_contributors: int,
    profit_contributors: int,
) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    total_orders = int(product.get("total_orders") or 0)
    shipped_orders = int(product.get("shipped_orders") or 0)
    delivered_orders = int(product.get("delivered_orders") or 0)
    delivered_units = int(product.get("units_delivered") or 0)
    inventory = int(product.get("inventory_quantity") or 0)
    gross_profit = float(product.get("gross_profit") or 0)
    gross_margin = product.get("gross_margin")
    delivery_rate = product.get("delivery_rate")
    cancellation_rate = product.get("cancellation_rate")
    return_rate = product.get("return_rate")
    cost_coverage = float(product.get("cost_completeness_pct") or 0)
    profitability_complete = bool(product.get("profitability_complete"))

    if delivered_orders > 0 and cost_coverage < 100.0:
        insights.append(
            _insight(
                type_="cost_incomplete",
                severity="warning",
                product=product,
                title_key="cost_incomplete",
                reason_key="cost_coverage_incomplete",
                action_key="complete_product_costs",
                evidence={
                    "cost_completeness_pct": cost_coverage,
                    "delivered_orders": delivered_orders,
                },
            )
        )

    negative_margin = (
        profitability_complete
        and delivered_orders > 0
        and gross_profit < 0
    )
    if negative_margin:
        insights.append(
            _insight(
                type_="negative_margin",
                severity="critical",
                product=product,
                title_key="negative_margin",
                reason_key="gross_profit_below_zero",
                action_key="review_price_and_cost",
                evidence={
                    "gross_profit": gross_profit,
                    "gross_margin": gross_margin,
                    "delivered_revenue": float(product.get("delivered_revenue") or 0),
                },
            )
        )

    if (
        profitability_complete
        and not negative_margin
        and delivered_orders >= 3
        and gross_profit >= 0
        and gross_margin is not None
        and float(gross_margin) < 20.0
    ):
        insights.append(
            _insight(
                type_="low_margin",
                severity="warning",
                product=product,
                title_key="low_margin",
                reason_key="gross_margin_below_threshold",
                action_key="improve_unit_economics",
                evidence={
                    "gross_margin": float(gross_margin),
                    "gross_profit": gross_profit,
                    "delivered_orders": delivered_orders,
                },
            )
        )

    if (
        shipped_orders >= 5
        and delivery_rate is not None
        and float(delivery_rate) < 60.0
    ):
        insights.append(
            _insight(
                type_="delivery_risk",
                severity="warning",
                product=product,
                title_key="delivery_risk",
                reason_key="delivery_rate_below_threshold",
                action_key="review_fulfillment_quality",
                evidence={
                    "delivery_rate": float(delivery_rate),
                    "shipped_orders": shipped_orders,
                    "delivered_orders": delivered_orders,
                },
            )
        )

    if (
        total_orders >= 5
        and cancellation_rate is not None
        and float(cancellation_rate) > 25.0
    ):
        insights.append(
            _insight(
                type_="cancellation_risk",
                severity="warning",
                product=product,
                title_key="cancellation_risk",
                reason_key="cancellation_rate_above_threshold",
                action_key="review_confirmation_and_offer",
                evidence={
                    "cancellation_rate": float(cancellation_rate),
                    "cancelled_orders": int(product.get("cancelled_orders") or 0),
                    "total_orders": total_orders,
                },
            )
        )

    if (
        shipped_orders >= 5
        and return_rate is not None
        and float(return_rate) > 15.0
    ):
        insights.append(
            _insight(
                type_="return_risk",
                severity="warning",
                product=product,
                title_key="return_risk",
                reason_key="return_rate_above_threshold",
                action_key="review_product_expectations",
                evidence={
                    "return_rate": float(return_rate),
                    "returned_orders": int(product.get("returned_orders") or 0),
                    "shipped_orders": shipped_orders,
                },
            )
        )

    stockout = inventory == 0 and delivered_units > 0
    if stockout:
        insights.append(
            _insight(
                type_="stockout",
                severity="critical",
                product=product,
                title_key="stockout",
                reason_key="inventory_zero_with_sales",
                action_key="replenish_stock",
                evidence={
                    "inventory_quantity": inventory,
                    "units_delivered": delivered_units,
                },
            )
        )
    elif period_days is not None and delivered_units >= 3 and inventory > 0:
        units_per_day = delivered_units / period_days
        if units_per_day > 0:
            stock_runway_days = inventory / units_per_day
            severity = None
            if stock_runway_days < 3:
                severity = "critical"
            elif stock_runway_days < 7:
                severity = "warning"
            if severity is not None:
                insights.append(
                    _insight(
                        type_="stock_runway",
                        severity=severity,
                        product=product,
                        title_key=(
                            "stock_runway_critical"
                            if severity == "critical"
                            else "stock_runway_warning"
                        ),
                        reason_key="stock_runway_below_threshold",
                        action_key="replenish_stock",
                        evidence={
                            "inventory_quantity": inventory,
                            "units_delivered": delivered_units,
                            "units_per_day": round(units_per_day, 1),
                            "stock_runway_days": round(stock_runway_days, 1),
                        },
                    )
                )

    if (
        revenue_contributors >= 2
        and float(product.get("delivered_revenue") or 0) > 0
        and float(product.get("revenue_share_pct") or 0) >= 50.0
    ):
        insights.append(
            _insight(
                type_="revenue_concentration",
                severity="warning",
                product=product,
                title_key="revenue_concentration",
                reason_key="revenue_share_above_threshold",
                action_key="diversify_product_mix",
                evidence={
                    "revenue_share_pct": float(product.get("revenue_share_pct") or 0),
                    "delivered_revenue": float(product.get("delivered_revenue") or 0),
                },
            )
        )

    if (
        profit_contributors >= 2
        and gross_profit > 0
        and float(product.get("profit_share_pct") or 0) >= 50.0
    ):
        insights.append(
            _insight(
                type_="profit_concentration",
                severity="warning",
                product=product,
                title_key="profit_concentration",
                reason_key="profit_share_above_threshold",
                action_key="diversify_profit_sources",
                evidence={
                    "profit_share_pct": float(product.get("profit_share_pct") or 0),
                    "gross_profit": gross_profit,
                },
            )
        )

    margin_claims_allowed = profitability_complete and not negative_margin
    winner = margin_claims_allowed and _quality_gates(
        product,
        minimum_delivered=3,
    )
    if winner:
        insights.append(
            _insight(
                type_="winner",
                severity="positive",
                product=product,
                title_key="winner",
                reason_key="winner_quality_thresholds_met",
                action_key="consider_scaling",
                evidence={
                    "gross_profit": gross_profit,
                    "gross_margin": float(gross_margin),
                    "delivery_rate": float(delivery_rate),
                    "revenue_share_pct": float(product.get("revenue_share_pct") or 0),
                },
            )
        )
    elif (
        margin_claims_allowed
        and _quality_gates(product, minimum_delivered=2)
        and float(product.get("revenue_share_pct") or 0) < 15.0
    ):
        insights.append(
            _insight(
                type_="opportunity",
                severity="opportunity",
                product=product,
                title_key="opportunity",
                reason_key="opportunity_quality_thresholds_met",
                action_key="test_more_volume",
                evidence={
                    "gross_profit": gross_profit,
                    "gross_margin": float(gross_margin),
                    "delivery_rate": float(delivery_rate),
                    "revenue_share_pct": float(product.get("revenue_share_pct") or 0),
                },
            )
        )

    return insights


def get_dropshipping_decision_insights(
    db: Session,
    organization_id: int,
    store_id: int,
    currency: str,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int = 20,
) -> dict[str, Any]:
    """Return deterministic, evidence-backed product decision insights."""
    products = get_product_profitability(
        db,
        organization_id,
        store_id,
        date_from,
        date_to,
        limit=None,
    )
    period_days = _bounded_period_days(date_from, date_to)
    revenue_contributors = sum(
        1 for product in products
        if float(product.get("delivered_revenue") or 0) > 0
    )
    profit_contributors = sum(
        1 for product in products
        if float(product.get("gross_profit") or 0) > 0
    )

    all_insights: list[dict[str, Any]] = []
    for product in products:
        all_insights.extend(
            _evaluate_product(
                product,
                period_days=period_days,
                revenue_contributors=revenue_contributors,
                profit_contributors=profit_contributors,
            )
        )

    all_insights.sort(key=_sort_key)
    summary = {
        severity: sum(
            1 for item in all_insights if item["severity"] == severity
        )
        for severity in ("critical", "warning", "opportunity", "positive")
    }
    summary["products_evaluated"] = len(products)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "date_from": date_from.isoformat() if date_from is not None else None,
        "date_to": date_to.isoformat() if date_to is not None else None,
        "currency": currency,
        "summary": summary,
        "insights": all_insights[:limit],
    }
