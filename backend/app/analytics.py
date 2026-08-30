"""
Analytics service for Diaglob Phase 1.

Pure SQL aggregation queries over existing data.
No new tables, no mock data, no ETL.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import (
    case,
    cast,
    Date,
    extract,
    func,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Session

from .models import (
    Automation,
    AutomationExecution,
    Conversation,
    Message,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Store,
)


# ============================================================
# DATE HELPERS
# ============================================================


def parse_date(
    value: str | None,
    default: datetime | None = None,
) -> datetime | None:
    """Parse ISO date string to datetime."""
    if not value:
        return default

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        return default


def get_date_range(
    date_from: str | None,
    date_to: str | None,
) -> tuple[datetime | None, datetime | None]:
    """Parse and validate date range."""
    d_from = parse_date(date_from)
    d_to = parse_date(date_to)

    if d_to:
        d_to = d_to + timedelta(days=1)

    return d_from, d_to


def day_col(
    model,
    tz_offset: int = 0,
):
    """Get a date-truncated column for grouping."""
    col = func.date(model.created_at)

    if tz_offset != 0:
        col = func.date(
            model.created_at,
            f"+{tz_offset} hours",
        )

    return col


# ============================================================
# GENERAL SUMMARY
# ============================================================


def get_summary(
    db: Session,
    organization_id: int,
    store_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Get overview analytics for a store."""

    base_conv = (
        db.query(Conversation)
        .filter(
            Conversation.organization_id
            == organization_id,
            Conversation.store_id == store_id,
        )
    )

    base_msg = (
        db.query(Message)
        .join(Conversation)
        .filter(
            Conversation.organization_id
            == organization_id,
            Conversation.store_id == store_id,
        )
    )

    base_order = (
        db.query(Order)
        .filter(
            Order.organization_id
            == organization_id,
            Order.store_id == store_id,
        )
    )

    base_auto = (
        db.query(AutomationExecution)
        .filter(
            AutomationExecution.organization_id
            == organization_id,
            AutomationExecution.store_id
            == store_id,
        )
    )

    if date_from:
        base_conv = base_conv.filter(
            Conversation.created_at >= date_from
        )
        base_msg = base_msg.filter(
            Message.created_at >= date_from
        )
        base_order = base_order.filter(
            Order.created_at >= date_from
        )
        base_auto = base_auto.filter(
            AutomationExecution.started_at
            >= date_from
        )

    if date_to:
        base_conv = base_conv.filter(
            Conversation.created_at < date_to
        )
        base_msg = base_msg.filter(
            Message.created_at < date_to
        )
        base_order = base_order.filter(
            Order.created_at < date_to
        )
        base_auto = base_auto.filter(
            AutomationExecution.started_at
            < date_to
        )

    total_conversations = (
        base_conv.count()
    )

    total_messages = base_msg.count()

    total_products = (
        db.query(Product)
        .filter(
            Product.organization_id
            == organization_id,
            Product.store_id == store_id,
        )
        .count()
    )

    total_variants = (
        db.query(ProductVariant)
        .join(Product)
        .filter(
            Product.organization_id
            == organization_id,
            Product.store_id == store_id,
        )
        .count()
    )

    total_orders = base_order.count()

    order_value_row = (
        db.query(
            func.coalesce(
                func.sum(Order.total_amount), 0
            )
        )
        .filter(
            Order.organization_id
            == organization_id,
            Order.store_id == store_id,
        )
    )

    if date_from:
        order_value_row = order_value_row.filter(
            Order.created_at >= date_from
        )

    if date_to:
        order_value_row = order_value_row.filter(
            Order.created_at < date_to
        )

    total_order_value = float(
        order_value_row.scalar()
    )

    avg_order_value = 0.0

    if total_orders > 0:
        avg_order_value = round(
            total_order_value / total_orders, 2
        )

    active_automations = (
        db.query(Automation)
        .filter(
            Automation.organization_id
            == organization_id,
            Automation.store_id == store_id,
            Automation.active.is_(True),
        )
        .count()
    )

    total_executions = base_auto.count()

    success_executions = (
        base_auto.filter(
            AutomationExecution.status == "success"
        ).count()
    )

    automation_success_rate = 0.0

    if total_executions > 0:
        automation_success_rate = round(
            (success_executions / total_executions)
            * 100,
            1,
        )

    avg_messages_per_conversation = 0.0

    if total_conversations > 0:
        avg_messages_per_conversation = round(
            total_messages / total_conversations,
            1,
        )

    return {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "total_products": total_products,
        "total_variants": total_variants,
        "total_orders": total_orders,
        "total_order_value": total_order_value,
        "avg_order_value": avg_order_value,
        "active_automations": active_automations,
        "total_executions": total_executions,
        "success_executions": success_executions,
        "automation_success_rate": (
            automation_success_rate
        ),
        "avg_messages_per_conversation": (
            avg_messages_per_conversation
        ),
    }


# ============================================================
# TIMESERIES
# ============================================================


def get_timeseries(
    db: Session,
    organization_id: int,
    store_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict[str, Any]]:
    """Get daily aggregated timeseries."""

    conv_by_day = _count_by_day(
        db,
        Conversation,
        organization_id,
        store_id,
        date_from,
        date_to,
        "conversations",
    )

    msg_by_day = _count_by_day(
        db,
        Message,
        organization_id,
        store_id,
        date_from,
        date_to,
        "messages",
        join_conversation=True,
    )

    order_by_day = _order_by_day(
        db,
        organization_id,
        store_id,
        date_from,
        date_to,
    )

    exec_by_day = _count_by_day(
        db,
        AutomationExecution,
        organization_id,
        store_id,
        date_from,
        date_to,
        "executions",
        date_col="started_at",
    )

    all_dates = sorted(
        set(
            list(conv_by_day.keys())
            + list(msg_by_day.keys())
            + list(order_by_day.keys())
            + list(exec_by_day.keys())
        )
    )

    result = []

    for date_str in all_dates:
        order_data = order_by_day.get(
            date_str,
            {"count": 0, "value": 0},
        )

        result.append(
            {
                "date": date_str,
                "conversations": conv_by_day.get(
                    date_str, 0
                ),
                "messages": msg_by_day.get(
                    date_str, 0
                ),
                "orders": order_data["count"],
                "order_value": order_data[
                    "value"
                ],
                "executions": exec_by_day.get(
                    date_str, 0
                ),
            }
        )

    return result


def _count_by_day(
    db: Session,
    model,
    organization_id: int,
    store_id: int,
    date_from: datetime | None,
    date_to: datetime | None,
    label: str,
    join_conversation: bool = False,
    date_col: str = "created_at",
) -> dict[str, int]:
    """Count records grouped by day."""

    col = getattr(model, date_col)
    date_expr = func.date(col)

    query = db.query(
        date_expr.label("day"),
        func.count().label("cnt"),
    )

    if join_conversation:
        query = query.join(Conversation)
        query = query.filter(
            Conversation.organization_id
            == organization_id,
            Conversation.store_id == store_id,
        )
    else:
        query = query.filter(
            model.organization_id
            == organization_id,
        )

    if hasattr(model, "store_id") and not join_conversation:
        query = query.filter(
            model.store_id == store_id
        )

    if date_from:
        query = query.filter(
            col >= date_from
        )

    if date_to:
        query = query.filter(
            col < date_to
        )

    rows = (
        query.group_by(date_expr)
        .order_by(date_expr)
        .all()
    )

    return {
        str(row.day): row.cnt for row in rows
    }


def _order_by_day(
    db: Session,
    organization_id: int,
    store_id: int,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, dict]:
    """Count orders and sum value grouped by day."""

    date_expr = func.date(Order.created_at)

    query = db.query(
        date_expr.label("day"),
        func.count().label("cnt"),
        func.coalesce(
            func.sum(Order.total_amount), 0
        ).label("val"),
    ).filter(
        Order.organization_id == organization_id,
        Order.store_id == store_id,
    )

    if date_from:
        query = query.filter(
            Order.created_at >= date_from
        )

    if date_to:
        query = query.filter(
            Order.created_at < date_to
        )

    rows = (
        query.group_by(date_expr)
        .order_by(date_expr)
        .all()
    )

    return {
        str(row.day): {
            "count": row.cnt,
            "value": float(row.val),
        }
        for row in rows
    }


# ============================================================
# CONVERSATIONS ANALYTICS
# ============================================================


def get_conversations_analytics(
    db: Session,
    organization_id: int,
    store_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Get conversation-specific analytics."""

    base = (
        db.query(Conversation)
        .filter(
            Conversation.organization_id
            == organization_id,
            Conversation.store_id == store_id,
        )
    )

    if date_from:
        base = base.filter(
            Conversation.created_at >= date_from
        )

    if date_to:
        base = base.filter(
            Conversation.created_at < date_to
        )

    total = base.count()

    base_msg = (
        db.query(Message)
        .join(Conversation)
        .filter(
            Conversation.organization_id
            == organization_id,
            Conversation.store_id == store_id,
        )
    )

    if date_from:
        base_msg = base_msg.filter(
            Message.created_at >= date_from
        )

    if date_to:
        base_msg = base_msg.filter(
            Message.created_at < date_to
        )

    total_messages = base_msg.count()

    avg_per_conversation = 0.0

    if total > 0:
        avg_per_conversation = round(
            total_messages / total, 1
        )

    by_channel = dict(
        db.query(
            Conversation.channel,
            func.count().label("cnt"),
        )
        .filter(
            Conversation.organization_id
            == organization_id,
            Conversation.store_id == store_id,
        )
        .group_by(Conversation.channel)
        .all()
    )

    by_mode = dict(
        db.query(
            Conversation.mode,
            func.count().label("cnt"),
        )
        .filter(
            Conversation.organization_id
            == organization_id,
            Conversation.store_id == store_id,
        )
        .group_by(Conversation.mode)
        .all()
    )

    sender_dist = dict(
        db.query(
            Message.sender,
            func.count().label("cnt"),
        )
        .join(Conversation)
        .filter(
            Conversation.organization_id
            == organization_id,
            Conversation.store_id == store_id,
        )
        .group_by(Message.sender)
        .all()
    )

    top_conversations = (
        db.query(
            Conversation.id,
            func.count(Message.id).label(
                "msg_count"
            ),
        )
        .join(Message)
        .filter(
            Conversation.organization_id
            == organization_id,
            Conversation.store_id == store_id,
        )
        .group_by(Conversation.id)
        .order_by(
            func.count(Message.id).desc()
        )
        .limit(5)
        .all()
    )

    return {
        "total_conversations": total,
        "total_messages": total_messages,
        "avg_messages_per_conversation": (
            avg_per_conversation
        ),
        "by_channel": by_channel,
        "by_mode": by_mode,
        "sender_distribution": sender_dist,
        "top_conversations": [
            {
                "conversation_id": row.id,
                "message_count": row.msg_count,
            }
            for row in top_conversations
        ],
    }


# ============================================================
# COMMERCE ANALYTICS
# ============================================================


def get_commerce_analytics(
    db: Session,
    organization_id: int,
    store_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Get commerce-specific analytics."""

    base = (
        db.query(Order)
        .filter(
            Order.organization_id
            == organization_id,
            Order.store_id == store_id,
        )
    )

    if date_from:
        base = base.filter(
            Order.created_at >= date_from
        )

    if date_to:
        base = base.filter(
            Order.created_at < date_to
        )

    total_orders = base.count()

    value_row = (
        db.query(
            func.coalesce(
                func.sum(Order.total_amount), 0
            )
        )
        .filter(
            Order.organization_id
            == organization_id,
            Order.store_id == store_id,
        )
    )

    if date_from:
        value_row = value_row.filter(
            Order.created_at >= date_from
        )

    if date_to:
        value_row = value_row.filter(
            Order.created_at < date_to
        )

    total_value = float(value_row.scalar())

    avg_ticket = 0.0

    if total_orders > 0:
        avg_ticket = round(
            total_value / total_orders, 2
        )

    by_status = dict(
        db.query(
            Order.external_creation_status,
            func.count().label("cnt"),
        )
        .filter(
            Order.organization_id
            == organization_id,
            Order.store_id == store_id,
        )
        .group_by(
            Order.external_creation_status
        )
        .all()
    )

    by_source = dict(
        db.query(
            Order.source,
            func.count().label("cnt"),
        )
        .filter(
            Order.organization_id
            == organization_id,
            Order.store_id == store_id,
        )
        .group_by(Order.source)
        .all()
    )

    top_products = (
        db.query(
            OrderItem.title,
            func.sum(
                OrderItem.quantity
            ).label("total_units"),
            func.count(
                func.distinct(OrderItem.order_id)
            ).label("order_count"),
            func.coalesce(
                func.sum(
                    OrderItem.quantity
                    * OrderItem.unit_price
                ),
                0,
            ).label("total_value"),
        )
        .filter(
            OrderItem.organization_id
            == organization_id,
            OrderItem.store_id == store_id,
        )
    )

    if date_from:
        top_products = top_products.filter(
            OrderItem.created_at >= date_from
        )

    if date_to:
        top_products = top_products.filter(
            OrderItem.created_at < date_to
        )

    top_products = (
        top_products.group_by(
            OrderItem.title
        )
        .order_by(
            func.sum(
                OrderItem.quantity
            ).desc()
        )
        .limit(10)
        .all()
    )

    return {
        "total_orders": total_orders,
        "total_value": total_value,
        "avg_ticket": avg_ticket,
        "by_status": by_status,
        "by_source": by_source,
        "top_products": [
            {
                "title": row.title,
                "total_units": int(
                    row.total_units
                ),
                "order_count": int(
                    row.order_count
                ),
                "total_value": float(
                    row.total_value
                ),
            }
            for row in top_products
        ],
    }


# ============================================================
# AUTOMATIONS ANALYTICS
# ============================================================


def get_automations_analytics(
    db: Session,
    organization_id: int,
    store_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Get automation-specific analytics."""

    total_automations = (
        db.query(Automation)
        .filter(
            Automation.organization_id
            == organization_id,
            Automation.store_id == store_id,
        )
        .count()
    )

    active_automations = (
        db.query(Automation)
        .filter(
            Automation.organization_id
            == organization_id,
            Automation.store_id == store_id,
            Automation.active.is_(True),
        )
        .count()
    )

    base_exec = (
        db.query(AutomationExecution)
        .filter(
            AutomationExecution.organization_id
            == organization_id,
            AutomationExecution.store_id
            == store_id,
        )
    )

    if date_from:
        base_exec = base_exec.filter(
            AutomationExecution.started_at
            >= date_from
        )

    if date_to:
        base_exec = base_exec.filter(
            AutomationExecution.started_at
            < date_to
        )

    total_executions = base_exec.count()

    by_status = dict(
        db.query(
            AutomationExecution.status,
            func.count().label("cnt"),
        )
        .filter(
            AutomationExecution.organization_id
            == organization_id,
            AutomationExecution.store_id
            == store_id,
        )
        .group_by(
            AutomationExecution.status
        )
        .all()
    )

    if date_from:
        base_status = (
            db.query(AutomationExecution)
            .filter(
                AutomationExecution.organization_id
                == organization_id,
                AutomationExecution.store_id
                == store_id,
                AutomationExecution.started_at
                >= date_from,
            )
        )

        if date_to:
            base_status = base_status.filter(
                AutomationExecution.started_at
                < date_to
            )

        by_status = dict(
            db.query(
                AutomationExecution.status,
                func.count().label("cnt"),
            )
            .filter(
                AutomationExecution.organization_id
                == organization_id,
                AutomationExecution.store_id
                == store_id,
                AutomationExecution.started_at
                >= date_from,
            )
            .group_by(
                AutomationExecution.status
            )
            .all()
        )

        if date_to:
            by_status = dict(
                db.query(
                    AutomationExecution.status,
                    func.count().label("cnt"),
                )
                .filter(
                    AutomationExecution.organization_id
                    == organization_id,
                    AutomationExecution.store_id
                    == store_id,
                    AutomationExecution.started_at
                    >= date_from,
                    AutomationExecution.started_at
                    < date_to,
                )
                .group_by(
                    AutomationExecution.status
                )
                .all()
            )

    success = by_status.get("success", 0)
    failed = by_status.get("failed", 0)
    skipped = by_status.get("skipped", 0)

    success_rate = 0.0

    if total_executions > 0:
        success_rate = round(
            (success / total_executions) * 100,
            1,
        )

    by_trigger = dict(
        db.query(
            Automation.trigger_type,
            func.count(Automation.id).label(
                "cnt"
            ),
        )
        .filter(
            Automation.organization_id
            == organization_id,
            Automation.store_id == store_id,
        )
        .group_by(Automation.trigger_type)
        .all()
    )

    top_by_executions = (
        db.query(
            Automation.name,
            func.count(
                AutomationExecution.id
            ).label("exec_count"),
        )
        .join(AutomationExecution)
        .filter(
            Automation.organization_id
            == organization_id,
            Automation.store_id == store_id,
        )
        .group_by(Automation.id, Automation.name)
        .order_by(
            func.count(
                AutomationExecution.id
            ).desc()
        )
        .limit(5)
        .all()
    )

    top_by_failures = (
        db.query(
            Automation.name,
            func.count(
                AutomationExecution.id
            ).label("fail_count"),
        )
        .join(AutomationExecution)
        .filter(
            Automation.organization_id
            == organization_id,
            Automation.store_id == store_id,
            AutomationExecution.status
            == "failed",
        )
        .group_by(Automation.id, Automation.name)
        .order_by(
            func.count(
                AutomationExecution.id
            ).desc()
        )
        .limit(5)
        .all()
    )

    avg_duration = None

    # Portable duration calculation:
    # PostgreSQL: EXTRACT(EPOCH FROM (completed_at - started_at))
    # SQLite: (julianday(completed_at) - julianday(started_at)) * 86400
    from sqlalchemy import inspect as sa_inspect

    dialect_name = (
        db.bind.dialect.name
        if hasattr(db.bind, 'dialect')
        else "sqlite"
    )

    if dialect_name == "sqlite":
        duration_seconds = (
            func.julianday(AutomationExecution.completed_at)
            - func.julianday(AutomationExecution.started_at)
        ) * 86400
    else:
        duration_seconds = extract(
            "epoch",
            AutomationExecution.completed_at
            - AutomationExecution.started_at,
        )

    duration_row = (
        db.query(
            func.avg(duration_seconds)
        )
        .filter(
            AutomationExecution.organization_id
            == organization_id,
            AutomationExecution.store_id
            == store_id,
            AutomationExecution.completed_at
            .isnot(None),
            AutomationExecution.status.in_(
                ["success", "failed"]
            ),
        )
    )

    if date_from:
        duration_row = duration_row.filter(
            AutomationExecution.started_at
            >= date_from
        )

    if date_to:
        duration_row = duration_row.filter(
            AutomationExecution.started_at
            < date_to
        )

    avg_seconds = duration_row.scalar()

    if avg_seconds is not None:
        avg_duration = round(
            float(avg_seconds), 1
        )

    return {
        "total_automations": total_automations,
        "active_automations": active_automations,
        "inactive_automations": (
            total_automations - active_automations
        ),
        "total_executions": total_executions,
        "by_status": by_status,
        "success_rate": success_rate,
        "avg_duration_seconds": avg_duration,
        "by_trigger": by_trigger,
        "top_by_executions": [
            {
                "name": row.name,
                "execution_count": row.exec_count,
            }
            for row in top_by_executions
        ],
        "top_by_failures": [
            {
                "name": row.name,
                "failure_count": row.fail_count,
            }
            for row in top_by_failures
        ],
    }
