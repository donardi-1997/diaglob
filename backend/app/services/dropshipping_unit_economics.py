"""Deterministic store-level Unit Economics for dropshipping analytics."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..models import Order, OrderItem, Store
from .unit_economics_config_service import (
    get_unit_economics_config,
    normalize_payment_method,
)
from .unit_economics_meta import resolve_meta_ad_spend


ZERO = Decimal("0")
HUNDRED = Decimal("100")


def _decimal(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return Decimal(str(value))


def _component(
    amount: Decimal | None,
    source: str,
    *,
    status: str = "available",
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "amount": None if amount is None else float(amount),
        "source": source,
        "status": status,
        "reason": reason,
        "metadata": metadata or {},
    }


def _not_applicable(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return _component(
        ZERO,
        "not_applicable",
        status="not_applicable",
        metadata=metadata,
    )


def _missing(
    reason: str,
    *,
    amount: Decimal | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _component(
        amount,
        "missing",
        status="missing",
        reason=reason,
        metadata=metadata,
    )


def _order_cohort(
    db: Session,
    organization_id: int,
    store_id: int,
    date_from: Any,
    date_to: Any,
) -> list[Order]:
    query = db.query(Order).filter(
        Order.organization_id == organization_id,
        Order.store_id == store_id,
    )
    if date_from is not None:
        query = query.filter(Order.created_at >= date_from)
    if date_to is not None:
        query = query.filter(Order.created_at < date_to)
    return query.order_by(Order.id.asc()).all()


def _resolve_cogs(
    db: Session,
    organization_id: int,
    store_id: int,
    delivered_orders: list[Order],
) -> dict[str, Any]:
    if not delivered_orders:
        return _not_applicable(
            {"cost_completeness_pct": 100.0, "item_count": 0}
        )

    delivered_ids = [order.id for order in delivered_orders]
    items = (
        db.query(OrderItem)
        .filter(
            OrderItem.organization_id == organization_id,
            OrderItem.store_id == store_id,
            OrderItem.order_id.in_(delivered_ids),
        )
        .all()
    )
    if not items:
        return _not_applicable(
            {"cost_completeness_pct": 100.0, "item_count": 0}
        )

    known = ZERO
    with_cost = 0
    for item in items:
        if item.unit_cost is None:
            continue
        with_cost += 1
        known += _decimal(item.unit_cost) * Decimal(item.quantity)

    completeness = float(
        (Decimal(with_cost) / Decimal(len(items)) * HUNDRED)
    )
    metadata = {
        "cost_completeness_pct": completeness,
        "item_count": len(items),
        "items_with_cost": with_cost,
    }
    if with_cost != len(items):
        return _missing(
            "cogs_incomplete",
            amount=known,
            metadata=metadata,
        )
    return _component(known, "actual", metadata=metadata)


def _resolve_outbound_shipping(
    config: dict[str, Any],
    fulfilled_outcomes: int,
) -> dict[str, Any]:
    if fulfilled_outcomes == 0:
        return _not_applicable({"applicable_orders": 0})

    unit_cost = config.get("outbound_shipping_cost")
    if unit_cost is None:
        return _missing(
            "shipping_estimate_missing",
            metadata={"applicable_orders": fulfilled_outcomes},
        )
    amount = _decimal(unit_cost) * Decimal(fulfilled_outcomes)
    return _component(
        amount,
        "estimated",
        metadata={
            "applicable_orders": fulfilled_outcomes,
            "per_order": float(_decimal(unit_cost)),
        },
    )


def _method_rules(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        rule["payment_method"]: rule
        for rule in config.get("payment_methods", [])
    }


def _resolve_payment_fees(
    config: dict[str, Any],
    delivered_orders: list[Order],
) -> dict[str, Any]:
    if not delivered_orders:
        return _not_applicable({"applicable_orders": 0})

    rules = _method_rules(config)
    default_percent = config.get("default_payment_fee_percent")
    default_fixed = config.get("default_payment_fee_fixed")
    known = ZERO
    unresolved: set[str] = set()

    for order in delivered_orders:
        method = normalize_payment_method(order.payment_method)
        if not method:
            unresolved.add("__missing__")
            continue

        rule = rules.get(method)
        percent = (
            rule.get("fee_percent")
            if rule is not None and rule.get("fee_percent") is not None
            else default_percent
        )
        fixed = (
            rule.get("fee_fixed")
            if rule is not None and rule.get("fee_fixed") is not None
            else default_fixed
        )
        if percent is None and fixed is None:
            unresolved.add(method)
            continue

        known += (
            _decimal(order.total_amount) * _decimal(percent) / HUNDRED
            + _decimal(fixed)
        )

    metadata = {
        "applicable_orders": len(delivered_orders),
        "unresolved_payment_methods": sorted(unresolved),
    }
    if unresolved:
        return _missing(
            "payment_fee_rule_missing",
            amount=known,
            metadata=metadata,
        )
    return _component(known, "estimated", metadata=metadata)


def _resolve_cod_fees(
    config: dict[str, Any],
    delivered_orders: list[Order],
) -> dict[str, Any]:
    if not delivered_orders:
        return _not_applicable({"applicable_orders": 0})

    rules = _method_rules(config)
    default_percent = config.get("default_cod_fee_percent")
    known = ZERO
    cod_orders = 0
    unresolved: set[str] = set()

    for order in delivered_orders:
        method = normalize_payment_method(order.payment_method)
        rule = rules.get(method) if method else None
        if not rule or not bool(rule.get("is_cod")):
            continue

        cod_orders += 1
        percent = (
            rule.get("cod_fee_percent")
            if rule.get("cod_fee_percent") is not None
            else default_percent
        )
        if percent is None:
            unresolved.add(method or "__missing__")
            continue
        known += _decimal(order.total_amount) * _decimal(percent) / HUNDRED

    if cod_orders == 0:
        return _not_applicable({"applicable_orders": 0})

    metadata = {
        "applicable_orders": cod_orders,
        "unresolved_payment_methods": sorted(unresolved),
    }
    if unresolved:
        return _missing(
            "cod_fee_rule_missing",
            amount=known,
            metadata=metadata,
        )
    return _component(known, "estimated", metadata=metadata)


def _resolve_reverse_logistics(
    config: dict[str, Any],
    returned_orders: list[Order],
) -> dict[str, Any]:
    if not returned_orders:
        return _not_applicable({"applicable_orders": 0})

    unit_cost = config.get("return_logistics_cost")
    if unit_cost is None:
        return _missing(
            "return_cost_missing",
            metadata={"applicable_orders": len(returned_orders)},
        )
    amount = _decimal(unit_cost) * Decimal(len(returned_orders))
    return _component(
        amount,
        "estimated",
        metadata={
            "applicable_orders": len(returned_orders),
            "per_order": float(_decimal(unit_cost)),
        },
    )


def _resolve_ad_component(meta: dict[str, Any]) -> dict[str, Any]:
    if meta.get("status") == "actual":
        return _component(
            _decimal(meta.get("amount")),
            "actual",
            metadata=meta.get("metadata") or {},
        )
    return _missing(
        meta.get("reason") or "provider_error",
        amount=(
            None
            if meta.get("amount") is None
            else _decimal(meta.get("amount"))
        ),
        metadata=meta.get("metadata") or {},
    )


def _data_quality(components: dict[str, dict[str, Any]]) -> dict[str, Any]:
    missing_components = [
        name
        for name, component in components.items()
        if component["status"] == "missing"
    ]
    return {
        "status": "incomplete" if missing_components else "complete",
        "missing_components": missing_components,
        "missing_reasons": {
            name: components[name]["reason"] for name in missing_components
        },
        "estimated_components": [
            name
            for name, component in components.items()
            if component["source"] == "estimated"
        ],
        "actual_components": [
            name
            for name, component in components.items()
            if component["source"] == "actual"
        ],
    }


def get_store_unit_economics(
    db: Session,
    organization_id: int,
    store: Store,
    date_from: Any,
    date_to: Any,
) -> dict[str, Any]:
    """Calculate contribution economics for one store and exact order cohort."""
    orders = _order_cohort(
        db,
        organization_id,
        store.id,
        date_from,
        date_to,
    )
    delivered_orders = [
        order for order in orders if order.lifecycle_status == "delivered"
    ]
    returned_orders = [
        order for order in orders if order.lifecycle_status == "returned"
    ]
    cancelled_orders = [
        order for order in orders if order.lifecycle_status == "cancelled"
    ]

    recognized_revenue = sum(
        (_decimal(order.total_amount) for order in delivered_orders),
        ZERO,
    )
    config = get_unit_economics_config(db, organization_id, store.id)

    cogs = _resolve_cogs(
        db,
        organization_id,
        store.id,
        delivered_orders,
    )
    components = {
        "cogs": cogs,
        "outbound_shipping": _resolve_outbound_shipping(
            config,
            len(delivered_orders) + len(returned_orders),
        ),
        "payment_fees": _resolve_payment_fees(config, delivered_orders),
        "cod_fees": _resolve_cod_fees(config, delivered_orders),
        "reverse_logistics": _resolve_reverse_logistics(config, returned_orders),
        "ad_spend": _resolve_ad_component(
            resolve_meta_ad_spend(
                db,
                organization_id,
                store,
                date_from,
                date_to,
            )
        ),
    }

    quality = _data_quality(components)
    known_cost_subtotal = sum(
        (
            _decimal(component["amount"])
            for component in components.values()
            if component["amount"] is not None
        ),
        ZERO,
    )

    cogs_amount = _decimal(cogs["amount"])
    gross_profit = recognized_revenue - cogs_amount
    gross_margin = (
        gross_profit / recognized_revenue * HUNDRED
        if recognized_revenue != ZERO
        else None
    )

    contribution_profit: Decimal | None = None
    contribution_margin: Decimal | None = None
    if quality["status"] == "complete":
        contribution_profit = recognized_revenue - known_cost_subtotal
        if recognized_revenue != ZERO:
            contribution_margin = (
                contribution_profit / recognized_revenue * HUNDRED
            )

    return {
        "store_id": store.id,
        "currency": store.currency,
        "date_from": date_from.isoformat() if date_from is not None else None,
        "date_to": date_to.isoformat() if date_to is not None else None,
        "recognized_revenue": float(recognized_revenue),
        "gross_profit": float(gross_profit),
        "gross_margin": None if gross_margin is None else float(gross_margin),
        "known_cost_subtotal": float(known_cost_subtotal),
        "contribution_profit": (
            None if contribution_profit is None else float(contribution_profit)
        ),
        "contribution_margin": (
            None if contribution_margin is None else float(contribution_margin)
        ),
        "components": components,
        "data_quality": quality,
        "order_counts": {
            "total": len(orders),
            "delivered": len(delivered_orders),
            "returned": len(returned_orders),
            "cancelled": len(cancelled_orders),
            "fulfilled_outcomes": len(delivered_orders) + len(returned_orders),
        },
    }
