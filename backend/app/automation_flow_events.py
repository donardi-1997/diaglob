"""Bridge domain events into active durable automation flows."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .automation_flow_graph import get_entry_node
from .automation_flow_engine import materialize_flow_trigger
from .models import AutomationFlow, AutomationFlowVersion, Order

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

    order_id = payload.get("order_id")
    if order_id is None:
        return None
    try:
        order_id = int(order_id)
    except (TypeError, ValueError):
        return None

    order = db.query(Order).filter(
        Order.id == order_id,
        Order.organization_id == organization_id,
        Order.store_id == store_id,
    ).first()
    return order.customer_id if order else None


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
        try:
            run = materialize_flow_trigger(
                db,
                flow,
                [customer_id],
                trigger_key=trigger_key,
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
