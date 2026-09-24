"""Customer-scoped order intelligence for conversational support.

This service intentionally exposes only customer-facing order and shipment
facts. Supplier costs, internal provider identifiers and shipping addresses do
not enter the LLM context.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from ..model_domains.shipments import Shipment
from ..model_domains.supplier_orders import SupplierOrder
from ..models import Order


_ORDER_INTENT_KEYWORDS = (
    "my order",
    "my orders",
    "order status",
    "order #",
    "track my",
    "tracking",
    "tracking number",
    "my shipment",
    "shipment status",
    "my package",
    "package status",
    "delivery status",
    "was it delivered",
    "has it shipped",
    "where is my",
    "mi pedido",
    "mis pedidos",
    "estado del pedido",
    "pedido #",
    "mi orden",
    "estado de mi orden",
    "rastreo",
    "rastrear mi",
    "número de guía",
    "numero de guia",
    "seguimiento",
    "mi envío",
    "mi envio",
    "mi paquete",
    "estado de entrega",
    "ya llegó",
    "ya llego",
    "dónde está mi",
    "donde esta mi",
    "meu pedido",
    "meus pedidos",
    "status do pedido",
    "rastreio",
    "rastrear meu",
    "minha encomenda",
    "meu pacote",
    "status da entrega",
    "onde está meu",
    "onde esta meu",
)

_ORDER_REFERENCE_RE = re.compile(
    r"(?:order|pedido|orden)\s*#?\s*([a-z0-9-]*\d[a-z0-9-]*)",
    re.IGNORECASE,
)


def is_order_intent(question: str) -> bool:
    normalized = (question or "").strip().lower()
    if not normalized:
        return False
    if any(keyword in normalized for keyword in _ORDER_INTENT_KEYWORDS):
        return True
    return bool(_ORDER_REFERENCE_RE.search(normalized))


def _normalize_reference(value: str | None) -> str:
    return re.sub(
        r"[^a-z0-9]",
        "",
        (value or "").lower(),
    )


def _select_orders(
    orders: list[Order],
    question: str,
) -> list[Order]:
    """Prefer a clearly referenced order, otherwise expose recent orders.

    Matching happens only inside the already tenant/store/customer-scoped set.
    """
    compact_question = _normalize_reference(question)

    explicit_reference = _ORDER_REFERENCE_RE.search(question or "")
    if explicit_reference:
        reference = _normalize_reference(explicit_reference.group(1))
        explicit = [
            order
            for order in orders
            if _normalize_reference(order.order_number) == reference
        ]
        return explicit[:1]

    explicit = [
        order
        for order in orders
        if (
            len(_normalize_reference(order.order_number)) >= 3
            and _normalize_reference(order.order_number)
            in compact_question
        )
    ]
    if explicit:
        return explicit[:1]

    return orders[:3]


def _serialize_event(event) -> dict[str, Any]:
    return {
        "status": event.normalized_status,
        "description": event.description,
        "location": event.location,
        "event_at": (
            event.event_at.isoformat() + "Z"
            if event.event_at
            else None
        ),
    }


def _serialize_shipment(shipment: Shipment | None) -> dict[str, Any] | None:
    if shipment is None:
        return None

    events = list(shipment.events or [])
    recent_events = events[-5:]

    return {
        "status": shipment.normalized_status,
        "tracking_number": shipment.tracking_number,
        "carrier": (
            shipment.last_mile_carrier
            or shipment.tracking_provider
            or shipment.logistic_name
        ),
        "tracking_url": shipment.tracking_url,
        "last_mile_tracking_number": shipment.last_mile_tracking_number,
        "delivery_time": (
            shipment.delivery_time.isoformat() + "Z"
            if shipment.delivery_time
            else None
        ),
        "delivered_at": (
            shipment.delivered_at.isoformat() + "Z"
            if shipment.delivered_at
            else None
        ),
        "last_event_at": (
            shipment.last_event_at.isoformat() + "Z"
            if shipment.last_event_at
            else None
        ),
        "events": [
            _serialize_event(event)
            for event in recent_events
        ],
    }


def build_customer_order_context(
    db: Session,
    *,
    organization_id: int,
    store_id: int,
    customer_id: int,
    question: str,
) -> dict[str, Any] | None:
    """Build customer-facing order facts only for order-related questions."""
    if not is_order_intent(question):
        return None

    orders = (
        db.query(Order)
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
            Order.customer_id == customer_id,
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(10)
        .all()
    )

    selected = _select_orders(orders, question)
    if not selected:
        return {
            "requested": True,
            "orders": [],
        }

    order_ids = [order.id for order in selected]

    supplier_orders = (
        db.query(SupplierOrder)
        .filter(
            SupplierOrder.organization_id == organization_id,
            SupplierOrder.store_id == store_id,
            SupplierOrder.order_id.in_(order_ids),
        )
        .order_by(SupplierOrder.id.desc())
        .all()
    )
    supplier_by_order: dict[int, SupplierOrder] = {}
    for supplier_order in supplier_orders:
        if supplier_order.order_id is not None:
            supplier_by_order.setdefault(
                supplier_order.order_id,
                supplier_order,
            )

    shipments = (
        db.query(Shipment)
        .filter(
            Shipment.organization_id == organization_id,
            Shipment.store_id == store_id,
            Shipment.order_id.in_(order_ids),
        )
        .order_by(Shipment.id.desc())
        .all()
    )
    shipment_by_order: dict[int, Shipment] = {}
    for shipment in shipments:
        if shipment.order_id is not None:
            shipment_by_order.setdefault(
                shipment.order_id,
                shipment,
            )

    payload = []
    for order in selected:
        supplier_order = supplier_by_order.get(order.id)
        shipment = shipment_by_order.get(order.id)

        payload.append(
            {
                "order_number": order.order_number,
                "created_at": (
                    order.created_at.isoformat() + "Z"
                    if order.created_at
                    else None
                ),
                "financial_status": order.financial_status,
                "payment_status": order.payment_status,
                "fulfillment_status": order.fulfillment_status,
                "lifecycle_status": order.lifecycle_status,
                "supplier_status": (
                    supplier_order.supplier_status
                    if supplier_order
                    else None
                ),
                "supplier_substatus": (
                    supplier_order.supplier_substatus
                    if supplier_order
                    else None
                ),
                "shipment": _serialize_shipment(shipment),
            }
        )

    return {
        "requested": True,
        "orders": payload,
    }
