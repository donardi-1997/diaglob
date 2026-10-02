"""Bridge domain events into active durable automation flows."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .automation_flow_graph import get_entry_node
from .automation_flow_engine import materialize_flow_trigger
from .models import AutomationFlow, AutomationFlowVersion, Order
from .services.order_confirmation import is_cod_order

logger = logging.getLogger(__name__)


EVENT_TO_FLOW_TRIGGER = {
    "order.created": "order_created",
    "order.failed": "failed_order",
    "post_sales.case_created": "post_sales_case_created",
    "post_sales.case_updated": "post_sales_case_updated",
    "post_sales.case_resolved": "post_sales_case_resolved",
    "shipment.created": "shipment_created",
    "shipment.in_transit": "shipment_in_transit",
    "shipment.out_for_delivery": "shipment_out_for_delivery",
    "shipment.delivered": "shipment_delivered",
    "shipment.delayed": "shipment_delayed",
    "shipment.failed": "shipment_failed",
    "shipment.delivery_exception": "shipment_delivery_exception",
    "shipment.returned": "shipment_returned",
}


def _payload_order_id(payload: dict[str, Any]) -> int | None:
    value = payload.get("order_id")
    order_payload = payload.get("order")
    if value is None and isinstance(order_payload, dict):
        value = order_payload.get("id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_order(
    db: Session,
    organization_id: int,
    store_id: int,
    payload: dict[str, Any],
) -> Order | None:
    order_id = _payload_order_id(payload)
    if order_id is None:
        return None
    return db.query(Order).filter(
        Order.id == order_id,
        Order.organization_id == organization_id,
        Order.store_id == store_id,
    ).first()


def _resolve_customer_id(
    db: Session,
    organization_id: int,
    store_id: int,
    payload: dict[str, Any],
) -> int | None:
    value = payload.get("customer_id")
    if value is None and isinstance(payload.get("customer"), dict):
        value = payload["customer"].get("id")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    order = _resolve_order(db, organization_id, store_id, payload)
    return order.customer_id if order else None


def _order_trigger_context(order: Order) -> dict[str, Any]:
    shipping = dict(order.shipping_address or {})
    items = [
        {
            "id": item.id,
            "title": item.title,
            "sku": item.sku,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price or 0),
            "currency": item.currency,
        }
        for item in order.items
    ]
    items_summary = ", ".join(
        f"{item['quantity']}x {item['title']}"
        for item in items
        if item.get("title")
    )
    return {
        "id": order.id,
        "number": order.order_number,
        "external_id": order.external_order_id,
        "shopify_order_id": order.shopify_order_id,
        "total": float(order.total_amount or 0),
        "currency": order.currency,
        "financial_status": order.financial_status,
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "is_cod": is_cod_order(order),
        "fulfillment_status": order.fulfillment_status,
        "lifecycle_status": order.lifecycle_status,
        "source": order.source,
        "shipping": shipping,
        "country": shipping.get("country_code") or shipping.get("country"),
        "items": items,
        "items_summary": items_summary,
        "confirmation_status": order.confirmation_status,
    }


def _build_trigger_context(
    db: Session,
    *,
    organization_id: int,
    store_id: int,
    event_type: str,
    event_id: str | None,
    payload: dict[str, Any],
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "event": {
            "type": event_type,
            "id": event_id,
        }
    }
    order = _resolve_order(db, organization_id, store_id, payload)
    if order is not None:
        context["order"] = _order_trigger_context(order)
    return context


def dispatch_flow_event(
    db: Session,
    *,
    organization_id: int,
    store_id: int | None,
    event_type: str,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> list[int]:
    trigger_type = EVENT_TO_FLOW_TRIGGER.get(event_type)
    if not trigger_type or store_id is None:
        return []

    customer_id = _resolve_customer_id(
        db,
        organization_id,
        store_id,
        payload,
    )
    if not customer_id:
        return []

    flows = db.query(AutomationFlow).filter(
        AutomationFlow.organization_id == organization_id,
        AutomationFlow.store_id == store_id,
        AutomationFlow.status == "active",
        AutomationFlow.active_version_id.isnot(None),
    ).all()

    created_run_ids: list[int] = []
    for flow in flows:
        version = db.query(AutomationFlowVersion).filter(
            AutomationFlowVersion.id == flow.active_version_id,
            AutomationFlowVersion.flow_id == flow.id,
            AutomationFlowVersion.organization_id == organization_id,
        ).first()
        if not version:
            continue

        entry = get_entry_node(version.graph or {})
        if not entry:
            continue
        if (entry.get("config") or {}).get("trigger_type") != trigger_type:
            continue

        trigger_key = (
            f"{event_id}:flow:{flow.id}"
            if event_id
            else None
        )
        trigger_context = _build_trigger_context(
            db,
            organization_id=organization_id,
            store_id=store_id,
            event_type=event_type,
            event_id=event_id,
            payload=payload,
        )
        try:
            run = materialize_flow_trigger(
                db,
                flow,
                [customer_id],
                trigger_key=trigger_key,
                trigger_context=trigger_context,
            )
        except Exception:
            logger.exception(
                "Failed to materialize flow event",
                extra={
                    "flow_id": flow.id,
                    "event_type": event_type,
                    "store_id": store_id,
                },
            )
            continue
        if run:
            created_run_ids.append(run.id)

    return created_run_ids
