"""
Operations Center service for Diaglob.

Aggregates real data from existing entities for the
Operations Center dashboard. No mock data, no hardcodes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import (
    Agent,
    Automation,
    AutomationExecution,
    Conversation,
    Customer,
    Message,
    Order,
    Product,
    ProductVariant,
    Store,
    WhatsAppConnection,
)

logger = logging.getLogger(__name__)


def _get_whatsapp_connection_count(
    db: Session,
    organization_id: int,
    store_id: int,
) -> int | None:
    """Return WhatsApp connection count without poisoning the summary session."""
    try:
        with db.begin_nested():
            return (
                db.query(WhatsAppConnection)
                .filter(
                    WhatsAppConnection.organization_id == organization_id,
                    WhatsAppConnection.store_id == store_id,
                    WhatsAppConnection.status == "connected",
                )
                .count()
            )
    except Exception:
        logger.exception(
            "Operations WhatsApp status lookup failed",
            extra={
                "organization_id": organization_id,
                "store_id": store_id,
            },
        )
        return None


def get_operations_summary(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict[str, Any]:
    """
    Aggregate real-time operations data for the dashboard.

    Reuses existing models and queries. No new tables.
    """
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    # --- Conversations ---
    active_conversations = (
        db.query(Conversation)
        .filter(
            Conversation.organization_id == organization_id,
            Conversation.store_id == store_id,
            Conversation.created_at >= last_24h,
        )
        .count()
    )

    total_conversations = (
        db.query(Conversation)
        .filter(
            Conversation.organization_id == organization_id,
            Conversation.store_id == store_id,
        )
        .count()
    )

    # --- Messages ---
    total_messages = (
        db.query(Message)
        .join(Conversation)
        .filter(
            Conversation.organization_id == organization_id,
            Conversation.store_id == store_id,
        )
        .count()
    )

    recent_messages = (
        db.query(Message)
        .join(Conversation)
        .filter(
            Conversation.organization_id == organization_id,
            Conversation.store_id == store_id,
            Message.created_at >= last_24h,
        )
        .count()
    )

    ai_messages = (
        db.query(Message)
        .join(Conversation)
        .filter(
            Conversation.organization_id == organization_id,
            Conversation.store_id == store_id,
            Message.sender == "ai",
            Message.created_at >= last_7d,
        )
        .count()
    )

    human_messages = (
        db.query(Message)
        .join(Conversation)
        .filter(
            Conversation.organization_id == organization_id,
            Conversation.store_id == store_id,
            Message.sender == "user",
            Message.created_at >= last_7d,
        )
        .count()
    )

    total_ai_human = ai_messages + human_messages
    ai_message_share_pct = (
        round((ai_messages / total_ai_human) * 100, 1)
        if total_ai_human > 0
        else 0.0
    )

    # --- Orders ---
    total_orders = (
        db.query(Order)
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
        .count()
    )

    recent_orders = (
        db.query(Order)
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
            Order.created_at >= last_24h,
        )
        .count()
    )

    order_value_row = (
        db.query(
            func.coalesce(func.sum(Order.total_amount), 0)
        )
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
    )

    total_order_value = float(order_value_row.scalar())

    orders_by_status = dict(
        db.query(
            Order.external_creation_status,
            func.count().label("cnt"),
        )
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
        .group_by(Order.external_creation_status)
        .all()
    )

    # --- Automations ---
    active_automations = (
        db.query(Automation)
        .filter(
            Automation.organization_id == organization_id,
            Automation.store_id == store_id,
            Automation.active.is_(True),
        )
        .count()
    )

    total_automations = (
        db.query(Automation)
        .filter(
            Automation.organization_id == organization_id,
            Automation.store_id == store_id,
        )
        .count()
    )

    recent_executions = (
        db.query(AutomationExecution)
        .filter(
            AutomationExecution.organization_id == organization_id,
            AutomationExecution.store_id == store_id,
            AutomationExecution.started_at >= last_24h,
        )
        .count()
    )

    failed_executions = (
        db.query(AutomationExecution)
        .filter(
            AutomationExecution.organization_id == organization_id,
            AutomationExecution.store_id == store_id,
            AutomationExecution.status == "failed",
            AutomationExecution.started_at >= last_7d,
        )
        .count()
    )

    # --- Products ---
    total_products = (
        db.query(Product)
        .filter(
            Product.organization_id == organization_id,
            Product.store_id == store_id,
        )
        .count()
    )

    total_variants = (
        db.query(ProductVariant)
        .join(Product)
        .filter(
            Product.organization_id == organization_id,
            Product.store_id == store_id,
        )
        .count()
    )

    # --- Agents ---
    total_agents = (
        db.query(Agent)
        .filter(
            Agent.organization_id == organization_id,
        )
        .count()
    )

    active_agents = (
        db.query(Agent)
        .filter(
            Agent.organization_id == organization_id,
            Agent.active.is_(True),
        )
        .count()
    )

    # --- Integrations ---
    whatsapp_connected = _get_whatsapp_connection_count(
        db=db,
        organization_id=organization_id,
        store_id=store_id,
    )

    store = (
        db.query(Store)
        .filter(Store.id == store_id)
        .first()
    )

    shopify_connected = bool(
        store and store.shopify_domain
    )

    # --- Alerts ---
    alerts = []

    if failed_executions > 0:
        alerts.append({
            "type": "failed_automations",
            "severity": "warning",
            "message": (
                f"{failed_executions} automation(s) "
                f"failed in the last 7 days"
            ),
        })

    if whatsapp_connected == 0:
        alerts.append({
            "type": "no_whatsapp",
            "severity": "info",
            "message": "No WhatsApp connection for this store",
        })

    if not shopify_connected:
        alerts.append({
            "type": "no_shopify",
            "severity": "info",
            "message": "No Shopify connection for this store",
        })

    unknown_orders = (
        db.query(Order)
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
            Order.external_creation_status == "unknown",
        )
        .count()
    )

    if unknown_orders > 0:
        alerts.append({
            "type": "unknown_orders",
            "severity": "warning",
            "message": (
                f"{unknown_orders} order(s) with unknown status"
            ),
        })

    # --- Recent Activity ---
    recent_conversations = (
        db.query(Conversation)
        .filter(
            Conversation.organization_id == organization_id,
            Conversation.store_id == store_id,
        )
        .order_by(Conversation.created_at.desc())
        .limit(5)
        .all()
    )

    recent_order_list = (
        db.query(Order)
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
        .order_by(Order.created_at.desc())
        .limit(5)
        .all()
    )

    recent_exec_list = (
        db.query(AutomationExecution)
        .filter(
            AutomationExecution.organization_id == organization_id,
            AutomationExecution.store_id == store_id,
        )
        .order_by(AutomationExecution.started_at.desc())
        .limit(5)
        .all()
    )

    activity = []

    for conv in recent_conversations:
        activity.append({
            "type": "conversation",
            "icon": "message",
            "title": f"Conversation #{conv.id}",
            "detail": conv.channel or "whatsapp",
            "timestamp": conv.created_at.isoformat()
            if conv.created_at
            else None,
        })

    for order in recent_order_list:
        activity.append({
            "type": "order",
            "icon": "shopping-bag",
            "title": f"Order #{order.id}",
            "detail": order.external_creation_status or "created",
            "timestamp": order.created_at.isoformat()
            if order.created_at
            else None,
        })

    for exe in recent_exec_list:
        activity.append({
            "type": "automation",
            "icon": "workflow",
            "title": "Automation execution",
            "detail": exe.status,
            "timestamp": exe.started_at.isoformat()
            if exe.started_at
            else None,
        })

    activity.sort(
        key=lambda x: x.get("timestamp") or "",
        reverse=True,
    )

    return {
        "conversations": {
            "active_24h": active_conversations,
            "total": total_conversations,
            "messages_total": total_messages,
            "messages_24h": recent_messages,
            "ai_message_share_pct": ai_message_share_pct,
            # Internal compatibility alias. Dynamic Operations output removes it.
            "ai_resolved_pct": ai_message_share_pct,
        },
        "orders": {
            "total": total_orders,
            "last_24h": recent_orders,
            "total_value": total_order_value,
            "by_status": orders_by_status,
        },
        "automations": {
            "total": total_automations,
            "active": active_automations,
            "executions_24h": recent_executions,
            "failed_7d": failed_executions,
        },
        "products": {
            "total": total_products,
            "variants": total_variants,
        },
        "agents": {
            "total": total_agents,
            "active": active_agents,
        },
        "integrations": {
            "whatsapp_connected": (
                whatsapp_connected is not None and whatsapp_connected > 0
            ),
            "shopify_connected": shopify_connected,
        },
        "alerts": alerts,
        "activity": activity[:10],
    }
