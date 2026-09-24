"""Shipment tracking orchestration for CJ supplier orders."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..integrations.cj import client as cj_client
from ..model_domains.shipments import Shipment
from ..model_domains.supplier_orders import SupplierOrder
from ..settings import get_settings
from .supplier_connections import get_valid_cj_access_token


class ShipmentTrackingError(Exception):
    pass


class ShipmentNotFound(ShipmentTrackingError):
    pass


STATUS_CODE_MAP = {
    0: "PENDING",
    1: "SHIPPED",
    2: "IN_TRANSIT",
    3: "RETURNED",
    4: "IN_TRANSIT",
    5: "IN_TRANSIT",
    6: "IN_TRANSIT",
    7: "CUSTOMS",
    8: "IN_TRANSIT",
    9: "IN_TRANSIT",
    10: "OUT_FOR_DELIVERY",
    11: "READY_FOR_PICKUP",
    12: "DELIVERED",
    13: "EXCEPTION",
    14: "RETURNED",
}


def normalize_cj_tracking_code(value: int | str | None) -> str:
    try:
        code = int(value) if value is not None else None
    except (TypeError, ValueError):
        return "PENDING"
    return STATUS_CODE_MAP.get(code, "PENDING")


def normalize_tracking_label(value: str | None) -> str:
    label = (value or "").strip().lower()
    if not label or "no tracking" in label or "not found" in label:
        return "PENDING"
    if "delivered" in label:
        return "DELIVERED"
    if "out for delivery" in label:
        return "OUT_FOR_DELIVERY"
    if "ready for pickup" in label or "ready for pick up" in label:
        return "READY_FOR_PICKUP"
    if "custom" in label:
        return "CUSTOMS"
    if "return" in label:
        return "RETURNED"
    if "failed" in label or "exception" in label:
        return "EXCEPTION"
    if "shipped" in label or "dispatch" in label:
        return "SHIPPED"
    if "transit" in label:
        return "IN_TRANSIT"
    return "IN_TRANSIT"


def parse_cj_event_time(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _require_supplier_order(
    db: Session,
    organization_id: int,
    store_id: int,
    supplier_order_id: int,
) -> SupplierOrder:
    order = (
        db.query(SupplierOrder)
        .filter(
            SupplierOrder.id == supplier_order_id,
            SupplierOrder.organization_id == organization_id,
            SupplierOrder.store_id == store_id,
            SupplierOrder.provider == "cj",
        )
        .first()
    )
    if not order:
        raise ShipmentNotFound("SUPPLIER_ORDER_NOT_FOUND")
    return order


def _upsert_shipment(
    db: Session,
    supplier_order: SupplierOrder,
    *,
    tracking_number: str,
    logistic_name: str | None = None,
    tracking_provider: str | None = None,
    tracking_url: str | None = None,
) -> Shipment:
    shipment = (
        db.query(Shipment)
        .filter(
            Shipment.store_id == supplier_order.store_id,
            Shipment.provider == "cj",
            Shipment.tracking_number == tracking_number,
        )
        .first()
    )
    now = datetime.utcnow()
    if shipment is None:
        shipment = Shipment(
            organization_id=supplier_order.organization_id,
            store_id=supplier_order.store_id,
            order_id=supplier_order.order_id,
            supplier_order_id=supplier_order.id,
            provider="cj",
            tracking_number=tracking_number,
            normalized_status="PENDING",
            created_at=now,
            updated_at=now,
        )
        db.add(shipment)
    else:
        shipment.order_id = supplier_order.order_id
        shipment.supplier_order_id = supplier_order.id

    if logistic_name:
        shipment.logistic_name = logistic_name
    if tracking_provider:
        shipment.tracking_provider = tracking_provider
    if tracking_url:
        shipment.tracking_url = tracking_url
    shipment.updated_at = now
    return shipment


def serialize_shipment(shipment: Shipment) -> dict[str, Any]:
    return {
        "id": shipment.id,
        "provider": shipment.provider,
        "order_id": shipment.order_id,
        "supplier_order_id": shipment.supplier_order_id,
        "tracking_number": shipment.tracking_number,
        "logistic_name": shipment.logistic_name,
        "tracking_provider": shipment.tracking_provider,
        "tracking_url": shipment.tracking_url,
        "origin_country_code": shipment.origin_country_code,
        "destination_country_code": shipment.destination_country_code,
        "last_mile_carrier": shipment.last_mile_carrier,
        "last_mile_tracking_number": shipment.last_mile_tracking_number,
        "status": shipment.normalized_status,
        "provider_status_code": shipment.provider_status_code,
        "provider_status_label": shipment.provider_status_label,
        "delivery_days": shipment.delivery_days,
        "delivery_time": (
            shipment.delivery_time.isoformat() + "Z"
            if shipment.delivery_time
            else None
        ),
        "shipped_at": (
            shipment.shipped_at.isoformat() + "Z"
            if shipment.shipped_at
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
        "last_synced_at": (
            shipment.last_synced_at.isoformat() + "Z"
            if shipment.last_synced_at
            else None
        ),
        "events": [
            {
                "id": event.id,
                "status": event.normalized_status,
                "provider_status_code": event.provider_status_code,
                "description": event.description,
                "location": event.location,
                "event_at": event.event_at.isoformat() + "Z",
            }
            for event in shipment.events
        ],
    }


def sync_cj_shipment(
    db: Session,
    organization_id: int,
    store_id: int,
    supplier_order_id: int,
) -> dict[str, Any]:
    supplier_order = _require_supplier_order(
        db,
        organization_id,
        store_id,
        supplier_order_id,
    )
    token = get_valid_cj_access_token(
        db,
        organization_id,
        store_id,
    )
    remote_order = cj_client.get_order(
        token,
        supplier_order.external_order_id
        or supplier_order.provider_order_number,
    )
    tracking_number = str(remote_order.get("trackNumber") or "").strip()
    if not tracking_number:
        return {
            "available": False,
            "supplier_order_id": supplier_order.id,
            "reason": "TRACKING_NUMBER_NOT_AVAILABLE",
        }

    shipment = _upsert_shipment(
        db,
        supplier_order,
        tracking_number=tracking_number,
        logistic_name=remote_order.get("logisticName"),
        tracking_provider=remote_order.get("trackingProvider"),
        tracking_url=remote_order.get("trackingUrl"),
    )
    db.flush()

    tracking_items = cj_client.get_tracking_info(token, [tracking_number])
    summary = next(
        (
            item
            for item in tracking_items
            if str(item.get("trackingNumber") or "").strip() == tracking_number
        ),
        None,
    )
    now = datetime.utcnow()
    if summary:
        shipment.origin_country_code = summary.get("trackingFrom")
        shipment.destination_country_code = summary.get("trackingTo")
        shipment.delivery_days = (
            str(summary.get("deliveryDay"))
            if summary.get("deliveryDay") not in (None, "")
            else None
        )
        shipment.delivery_time = parse_cj_event_time(summary.get("deliveryTime"))
        shipment.provider_status_label = summary.get("trackingStatus")
        shipment.normalized_status = normalize_tracking_label(
            summary.get("trackingStatus")
        )
        shipment.last_mile_carrier = summary.get("lastMileCarrier")
        shipment.last_mile_tracking_number = summary.get("lastTrackNumber")

        if shipment.normalized_status == "DELIVERED":
            shipment.delivered_at = (
                shipment.delivery_time or shipment.delivered_at or now
            )
        if (
            shipment.normalized_status
            not in {"PENDING", "PROCESSING"}
            and shipment.shipped_at is None
        ):
            shipment.shipped_at = now

    shipment.last_synced_at = now
    shipment.updated_at = now
    db.commit()
    db.refresh(shipment)

    return {
        "available": True,
        "shipment": serialize_shipment(shipment),
    }


def get_supplier_order_shipment(
    db: Session,
    organization_id: int,
    store_id: int,
    supplier_order_id: int,
) -> dict[str, Any]:
    _require_supplier_order(
        db,
        organization_id,
        store_id,
        supplier_order_id,
    )
    shipment = (
        db.query(Shipment)
        .filter(
            Shipment.organization_id == organization_id,
            Shipment.store_id == store_id,
            Shipment.supplier_order_id == supplier_order_id,
            Shipment.provider == "cj",
        )
        .order_by(Shipment.id.desc())
        .first()
    )
    if shipment is None:
        return {
            "available": False,
            "supplier_order_id": supplier_order_id,
            "reason": "SHIPMENT_NOT_CREATED",
        }
    return {
        "available": True,
        "shipment": serialize_shipment(shipment),
    }


def configure_cj_logistics_webhook(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict[str, Any]:
    # Reuse the same tenant-scoped order guard so a foreign store cannot
    # configure callbacks with another organization's CJ credentials.
    token = get_valid_cj_access_token(
        db,
        organization_id,
        store_id,
    )
    callback_url = (
        f"{get_settings().public_api_base_url}/api/webhooks/cj"
    )
    configured = cj_client.set_webhook_configuration(
        token,
        callback_url,
    )
    if not configured:
        raise ShipmentTrackingError("CJ_WEBHOOK_CONFIGURATION_REJECTED")

    return {
        "ok": True,
        "provider": "cj",
        "topic": "LOGISTIC",
        "callback_url": callback_url,
    }
