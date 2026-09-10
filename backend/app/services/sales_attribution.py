"""Order sales attribution and attribution analytics.

Attribution is explicit. Provider-imported orders without trustworthy evidence
remain unattributed; this service never guesses a closer from conversation
state, channel, or timestamps.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..model_domains.sales_attribution import OrderSalesAttribution
from ..models import (
    Agent,
    Conversation,
    Order,
    OrderItem,
    OrganizationMembership,
    User,
)


class SalesAttributionError(Exception):
    """Raised when an attribution actor or order is invalid."""


def _percentage(numerator: Any, denominator: Any) -> float | None:
    if denominator is None or denominator == 0:
        return None
    value = Decimal(str(numerator)) / Decimal(str(denominator)) * Decimal("100")
    return float(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _divide(numerator: Any, denominator: Any) -> float | None:
    if denominator is None or denominator == 0:
        return None
    return float(Decimal(str(numerator)) / Decimal(str(denominator)))


def _require_order(
    db: Session,
    organization_id: int,
    store_id: int,
    order_id: int,
) -> Order:
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
        .first()
    )
    if not order:
        raise SalesAttributionError("Order not found")
    return order


def _human_actor(
    db: Session,
    organization_id: int,
    store_id: int,
    user_id: int,
) -> tuple[int, str]:
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.active.is_(True),
        )
        .first()
    )
    if not membership:
        raise SalesAttributionError("Human closer is not an active organization member")

    if not membership.all_stores:
        allowed_store_ids = {store.id for store in membership.stores}
        if store_id not in allowed_store_ids:
            raise SalesAttributionError("Human closer does not have access to this store")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise SalesAttributionError("Human closer user not found")

    label = (user.name or "").strip() or user.email
    return user.id, label


def _ai_actor(
    db: Session,
    organization_id: int,
    store_id: int,
    agent_id: int,
) -> tuple[int, str]:
    agent = (
        db.query(Agent)
        .filter(
            Agent.id == agent_id,
            Agent.organization_id == organization_id,
            Agent.active.is_(True),
        )
        .first()
    )
    if not agent:
        raise SalesAttributionError("AI closer is not an active organization agent")

    allowed_store_ids = {store.id for store in agent.stores if store.active}
    if store_id not in allowed_store_ids:
        raise SalesAttributionError("AI closer does not belong to this store")

    return agent.id, agent.name


def _validate_conversation(
    db: Session,
    organization_id: int,
    store_id: int,
    conversation_id: int | None,
) -> int | None:
    if conversation_id is None:
        return None

    exists = (
        db.query(Conversation.id)
        .filter(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
            Conversation.store_id == store_id,
        )
        .first()
    )
    if not exists:
        raise SalesAttributionError("Conversation not found for this store")
    return conversation_id


def record_order_attribution(
    db: Session,
    organization_id: int,
    store_id: int,
    order_id: int,
    *,
    actor_type: str,
    human_user_id: int | None = None,
    ai_agent_id: int | None = None,
    conversation_id: int | None = None,
    source: str = "diaglob_order_creation",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Persist an explicit closer for an order.

    Automatic flows should leave ``overwrite`` false so an existing explicit
    attribution is never silently replaced. Administrative correction flows
    can opt in to overwrite after an explicit user action.
    """
    _require_order(db, organization_id, store_id, order_id)
    conversation_id = _validate_conversation(
        db,
        organization_id,
        store_id,
        conversation_id,
    )

    if actor_type == "human":
        if human_user_id is None or ai_agent_id is not None:
            raise SalesAttributionError("Human attribution requires only human_user_id")
        actor_id, actor_label = _human_actor(
            db,
            organization_id,
            store_id,
            human_user_id,
        )
        normalized_human_user_id = actor_id
        normalized_ai_agent_id = None
    elif actor_type == "ai":
        if ai_agent_id is None or human_user_id is not None:
            raise SalesAttributionError("AI attribution requires only ai_agent_id")
        actor_id, actor_label = _ai_actor(
            db,
            organization_id,
            store_id,
            ai_agent_id,
        )
        normalized_human_user_id = None
        normalized_ai_agent_id = actor_id
    else:
        raise SalesAttributionError("actor_type must be human or ai")

    existing = (
        db.query(OrderSalesAttribution)
        .filter(
            OrderSalesAttribution.order_id == order_id,
            OrderSalesAttribution.organization_id == organization_id,
            OrderSalesAttribution.store_id == store_id,
        )
        .first()
    )

    if existing and not overwrite:
        same_actor = (
            existing.actor_type == actor_type
            and existing.human_user_id == normalized_human_user_id
            and existing.ai_agent_id == normalized_ai_agent_id
        )
        if not same_actor:
            return _serialize_attribution(existing)

        if existing.conversation_id is None and conversation_id is not None:
            existing.conversation_id = conversation_id
            existing.updated_at = datetime.utcnow()
            db.commit()
        return _serialize_attribution(existing)

    now = datetime.utcnow()
    if existing:
        attribution = existing
        attribution.actor_type = actor_type
        attribution.actor_label = actor_label
        attribution.human_user_id = normalized_human_user_id
        attribution.ai_agent_id = normalized_ai_agent_id
        attribution.conversation_id = conversation_id
        attribution.source = source
        attribution.updated_at = now
    else:
        attribution = OrderSalesAttribution(
            organization_id=organization_id,
            store_id=store_id,
            order_id=order_id,
            actor_type=actor_type,
            actor_label=actor_label,
            human_user_id=normalized_human_user_id,
            ai_agent_id=normalized_ai_agent_id,
            conversation_id=conversation_id,
            source=source,
            created_at=now,
            updated_at=now,
        )
        db.add(attribution)

    db.commit()
    db.refresh(attribution)
    return _serialize_attribution(attribution)


def record_human_order_attribution(
    db: Session,
    organization_id: int,
    store_id: int,
    order_id: int,
    user_id: int,
    *,
    conversation_id: int | None = None,
    source: str = "diaglob_order_creation",
) -> dict[str, Any]:
    return record_order_attribution(
        db,
        organization_id,
        store_id,
        order_id,
        actor_type="human",
        human_user_id=user_id,
        conversation_id=conversation_id,
        source=source,
    )


def record_ai_order_attribution(
    db: Session,
    organization_id: int,
    store_id: int,
    order_id: int,
    agent_id: int,
    *,
    conversation_id: int | None = None,
    source: str = "ai_order_creation",
) -> dict[str, Any]:
    return record_order_attribution(
        db,
        organization_id,
        store_id,
        order_id,
        actor_type="ai",
        ai_agent_id=agent_id,
        conversation_id=conversation_id,
        source=source,
    )


def _serialize_attribution(attribution: OrderSalesAttribution) -> dict[str, Any]:
    actor_id = (
        attribution.human_user_id
        if attribution.actor_type == "human"
        else attribution.ai_agent_id
    )
    return {
        "actor_type": attribution.actor_type,
        "actor_id": actor_id,
        "actor_label": attribution.actor_label,
        "human_user_id": attribution.human_user_id,
        "ai_agent_id": attribution.ai_agent_id,
        "conversation_id": attribution.conversation_id,
        "source": attribution.source,
    }


def get_order_attribution_map(
    db: Session,
    organization_id: int,
    store_id: int,
    order_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not order_ids:
        return {}

    rows = (
        db.query(OrderSalesAttribution)
        .filter(
            OrderSalesAttribution.organization_id == organization_id,
            OrderSalesAttribution.store_id == store_id,
            OrderSalesAttribution.order_id.in_(order_ids),
        )
        .all()
    )
    return {row.order_id: _serialize_attribution(row) for row in rows}


def enrich_orders_with_attribution(
    db: Session,
    organization_id: int,
    store_id: int,
    orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach closer information to existing serialized commerce orders."""
    attribution_map = get_order_attribution_map(
        db,
        organization_id,
        store_id,
        [int(order["id"]) for order in orders],
    )
    return [
        {
            **order,
            "sales_attribution": attribution_map.get(int(order["id"])),
        }
        for order in orders
    ]


def _cost_maps(
    db: Session,
    delivered_order_ids: list[int],
) -> tuple[dict[int, float], dict[int, int], dict[int, int]]:
    if not delivered_order_ids:
        return {}, {}, {}

    rows = (
        db.query(
            OrderItem.order_id,
            func.coalesce(func.sum(OrderItem.unit_cost * OrderItem.quantity), 0),
            func.count(OrderItem.id),
            func.count(OrderItem.unit_cost),
        )
        .filter(OrderItem.order_id.in_(delivered_order_ids))
        .group_by(OrderItem.order_id)
        .all()
    )

    cogs: dict[int, float] = {}
    item_counts: dict[int, int] = {}
    cost_counts: dict[int, int] = {}
    for order_id, order_cogs, item_count, cost_count in rows:
        cogs[int(order_id)] = float(order_cogs or 0)
        item_counts[int(order_id)] = int(item_count or 0)
        cost_counts[int(order_id)] = int(cost_count or 0)
    return cogs, item_counts, cost_counts


def _metrics(
    orders: list[Order],
    cogs: dict[int, float],
    item_counts: dict[int, int],
    cost_counts: dict[int, int],
) -> dict[str, Any]:
    total_orders = len(orders)
    delivered = [order for order in orders if order.lifecycle_status == "delivered"]
    cancelled = [order for order in orders if order.lifecycle_status == "cancelled"]
    returned = [order for order in orders if order.lifecycle_status == "returned"]

    gross_order_value = sum(Decimal(str(order.total_amount or 0)) for order in orders)
    delivered_revenue = sum(
        Decimal(str(order.total_amount or 0)) for order in delivered
    )
    delivered_cogs = sum(Decimal(str(cogs.get(order.id, 0))) for order in delivered)
    gross_profit = delivered_revenue - delivered_cogs

    delivered_item_count = sum(item_counts.get(order.id, 0) for order in delivered)
    delivered_cost_count = sum(cost_counts.get(order.id, 0) for order in delivered)
    completeness = (
        _percentage(delivered_cost_count, delivered_item_count)
        if delivered_item_count
        else 0.0
    )

    return {
        "total_orders": total_orders,
        "delivered_orders": len(delivered),
        "cancelled_orders": len(cancelled),
        "returned_orders": len(returned),
        "gross_order_value": float(gross_order_value),
        "delivered_revenue": float(delivered_revenue),
        "total_cogs": float(delivered_cogs),
        "gross_profit": float(gross_profit),
        "gross_margin": _percentage(gross_profit, delivered_revenue),
        "delivered_aov": _divide(delivered_revenue, len(delivered)),
        "delivery_rate": _percentage(len(delivered), total_orders),
        "cancellation_rate": _percentage(len(cancelled), total_orders),
        "return_rate": _percentage(len(returned), total_orders),
        "cost_completeness_pct": completeness,
        "profitability_complete": bool(delivered_item_count) and completeness == 100.0,
    }


def get_sales_attribution_analytics(
    db: Session,
    organization_id: int,
    store_id: int,
    date_from: Any,
    date_to: Any,
) -> dict[str, Any]:
    """Compare AI, human and unattributed sales for one store/date cohort."""
    query = db.query(Order).filter(
        Order.organization_id == organization_id,
        Order.store_id == store_id,
    )
    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at < date_to)

    orders = query.all()
    order_ids = [order.id for order in orders]
    order_map = {order.id: order for order in orders}
    delivered_ids = [
        order.id for order in orders if order.lifecycle_status == "delivered"
    ]
    cogs, item_counts, cost_counts = _cost_maps(db, delivered_ids)

    attribution_rows = (
        db.query(OrderSalesAttribution)
        .filter(
            OrderSalesAttribution.organization_id == organization_id,
            OrderSalesAttribution.store_id == store_id,
            OrderSalesAttribution.order_id.in_(order_ids),
        )
        .all()
        if order_ids
        else []
    )
    attribution_map = {row.order_id: row for row in attribution_rows}

    human_orders = [
        order
        for order in orders
        if attribution_map.get(order.id)
        and attribution_map[order.id].actor_type == "human"
    ]
    ai_orders = [
        order
        for order in orders
        if attribution_map.get(order.id)
        and attribution_map[order.id].actor_type == "ai"
    ]
    unattributed_orders = [order for order in orders if order.id not in attribution_map]

    overall = _metrics(orders, cogs, item_counts, cost_counts)
    human_metrics = _metrics(human_orders, cogs, item_counts, cost_counts)
    ai_metrics = _metrics(ai_orders, cogs, item_counts, cost_counts)
    unattributed_metrics = _metrics(
        unattributed_orders,
        cogs,
        item_counts,
        cost_counts,
    )

    total_orders = len(orders)
    attributed_orders = len(human_orders) + len(ai_orders)
    total_delivered_revenue = overall["delivered_revenue"]

    def actor_rows(actor_type: str) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, int | str], dict[str, Any]] = {}
        for attribution in attribution_rows:
            if attribution.actor_type != actor_type:
                continue
            order = order_map.get(attribution.order_id)
            if order is None:
                continue

            actor_id = (
                attribution.human_user_id
                if actor_type == "human"
                else attribution.ai_agent_id
            )
            group_key: tuple[str, int | str] = (
                actor_type,
                actor_id if actor_id is not None else attribution.actor_label,
            )
            group = grouped.setdefault(
                group_key,
                {
                    "actor_id": actor_id,
                    "actor_label": attribution.actor_label,
                    "orders": [],
                },
            )
            group["orders"].append(order)

        result: list[dict[str, Any]] = []
        for group in grouped.values():
            metrics = _metrics(group["orders"], cogs, item_counts, cost_counts)
            result.append(
                {
                    "actor_id": group["actor_id"],
                    "actor_label": group["actor_label"],
                    **metrics,
                    "order_share_pct": _percentage(metrics["total_orders"], total_orders),
                    "revenue_share_pct": _percentage(
                        metrics["delivered_revenue"],
                        total_delivered_revenue,
                    ),
                }
            )

        result.sort(
            key=lambda row: (row["delivered_revenue"], row["total_orders"]),
            reverse=True,
        )
        return result

    return {
        "total_orders": total_orders,
        "attributed_orders": attributed_orders,
        "unattributed_orders": len(unattributed_orders),
        "attribution_rate_pct": (
            _percentage(attributed_orders, total_orders) if total_orders else 0.0
        ),
        "overall": overall,
        "by_actor_type": {
            "human": human_metrics,
            "ai": ai_metrics,
            "unattributed": unattributed_metrics,
        },
        "employees": actor_rows("human"),
        "ai_agents": actor_rows("ai"),
    }
