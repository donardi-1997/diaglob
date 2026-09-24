"""CJ webhook signature verification and logistics ingestion."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..model_domains.shipments import CJWebhookReceipt, Shipment, TrackingEvent
from ..model_domains.supplier_integrations import SupplierConnection
from ..model_domains.supplier_orders import SupplierOrder
from .shipment_tracking import (
    _upsert_shipment,
    normalize_cj_tracking_code,
    parse_cj_event_time,
)


class CJWebhookError(Exception):
    pass


class CJWebhookAuthError(CJWebhookError):
    pass


def compute_cj_webhook_signature(open_id: str, raw_body: bytes) -> str:
    digest = hmac.new(
        open_id.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _event_key(event: dict[str, Any]) -> str:
    stable = "|".join(
        str(event.get(key) or "")
        for key in (
            "status",
            "activity",
            "location",
            "eventTime",
            "thirdActivity",
            "thirdLocation",
            "thirdEventTime",
        )
    )
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _decode_tracking_events(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _find_supplier_order(
    db: Session,
    connections: list[SupplierConnection],
    params: dict[str, Any],
) -> SupplierOrder | None:
    connection_ids = [connection.id for connection in connections]
    if not connection_ids:
        return None

    remote_order_id = str(params.get("orderId") or "").strip()
    store_order_numbers = [
        str(value).strip()
        for value in (params.get("storeOrderNumbers") or [])
        if str(value).strip()
    ]

    predicates = []
    if remote_order_id:
        predicates.append(SupplierOrder.external_order_id == remote_order_id)
    if store_order_numbers:
        predicates.append(
            SupplierOrder.provider_order_number.in_(store_order_numbers)
        )
    if not predicates:
        return None

    return (
        db.query(SupplierOrder)
        .filter(
            SupplierOrder.supplier_connection_id.in_(connection_ids),
            SupplierOrder.provider == "cj",
            or_(*predicates),
        )
        .first()
    )

def _insert_events(
    db: Session,
    shipment: Shipment,
    events: list[dict[str, Any]],
) -> None:
    existing_keys = {
        key
        for (key,) in (
            db.query(TrackingEvent.provider_event_key)
            .filter(TrackingEvent.shipment_id == shipment.id)
            .all()
        )
    }

    event_times: list[datetime] = []
    for raw_event in events:
        key = _event_key(raw_event)
        if key in existing_keys:
            continue
        event_at = (
            parse_cj_event_time(raw_event.get("eventTime"))
            or parse_cj_event_time(raw_event.get("thirdEventTime"))
            or datetime.utcnow()
        )
        try:
            status_code = int(raw_event.get("status"))
        except (TypeError, ValueError):
            status_code = None

        db.add(
            TrackingEvent(
                shipment_id=shipment.id,
                provider_event_key=key,
                provider_status_code=status_code,
                normalized_status=normalize_cj_tracking_code(status_code),
                description=(
                    raw_event.get("statusDesc")
                    or raw_event.get("activity")
                    or raw_event.get("thirdActivity")
                ),
                location=(
                    raw_event.get("location")
                    or raw_event.get("thirdLocation")
                ),
                event_at=event_at,
                created_at=datetime.utcnow(),
            )
        )
        existing_keys.add(key)
        event_times.append(event_at)

    if event_times:
        newest = max(event_times)
        if shipment.last_event_at is None or newest > shipment.last_event_at:
            shipment.last_event_at = newest


def process_cj_webhook(
    db: Session,
    *,
    raw_body: bytes,
    signature: str | None,
) -> dict[str, Any]:
    if not signature:
        raise CJWebhookAuthError("CJ_WEBHOOK_SIGNATURE_REQUIRED")

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CJWebhookError("CJ_WEBHOOK_INVALID_JSON") from exc

    if not isinstance(payload, dict):
        raise CJWebhookError("CJ_WEBHOOK_INVALID_PAYLOAD")

    open_id = str(payload.get("openId") or "").strip()
    if not open_id:
        raise CJWebhookAuthError("CJ_WEBHOOK_OPEN_ID_REQUIRED")

    connections = (
        db.query(SupplierConnection)
        .filter(
            SupplierConnection.provider == "cj",
            SupplierConnection.external_account_id == open_id,
            SupplierConnection.status == "connected",
        )
        .all()
    )
    if not connections:
        raise CJWebhookAuthError("CJ_WEBHOOK_ACCOUNT_UNKNOWN")

    expected = compute_cj_webhook_signature(open_id, raw_body)
    if not hmac.compare_digest(expected, signature.strip()):
        raise CJWebhookAuthError("CJ_WEBHOOK_SIGNATURE_INVALID")

    message_id = str(payload.get("messageId") or "").strip()
    if not message_id:
        raise CJWebhookError("CJ_WEBHOOK_MESSAGE_ID_REQUIRED")

    account_key_hash = hashlib.sha256(
        open_id.encode("utf-8")
    ).hexdigest()

    existing = (
        db.query(CJWebhookReceipt)
        .filter(
            CJWebhookReceipt.account_key_hash == account_key_hash,
            CJWebhookReceipt.message_id == message_id,
        )
        .first()
    )
    if existing:
        return {
            "ok": True,
            "duplicate": True,
            "message_id": message_id,
        }

    now = datetime.utcnow()
    topic = str(payload.get("type") or "UNKNOWN").upper()
    params = payload.get("params") or {}
    supplier_order = (
        _find_supplier_order(db, connections, params)
        if topic == "LOGISTIC" and isinstance(params, dict)
        else None
    )
    resolved_connection_id = (
        supplier_order.supplier_connection_id
        if supplier_order is not None
        else None
    )

    receipt = CJWebhookReceipt(
        supplier_connection_id=resolved_connection_id,
        account_key_hash=account_key_hash,
        message_id=message_id,
        topic=topic[:50],
        message_type=(
            str(payload.get("messageType"))[:30]
            if payload.get("messageType") is not None
            else None
        ),
        processing_status="received",
        received_at=now,
    )
    db.add(receipt)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {
            "ok": True,
            "duplicate": True,
            "message_id": message_id,
        }

    if topic != "LOGISTIC":
        receipt.processing_status = "ignored"
        receipt.error_code = "UNSUPPORTED_TOPIC"
        receipt.processed_at = now
        db.commit()
        return {
            "ok": True,
            "duplicate": False,
            "ignored": True,
            "message_id": message_id,
        }

    if not isinstance(params, dict):
        receipt.processing_status = "ignored"
        receipt.error_code = "INVALID_PARAMS"
        receipt.processed_at = now
        db.commit()
        return {"ok": True, "ignored": True, "message_id": message_id}

    if supplier_order is None:
        receipt.processing_status = "ignored"
        receipt.error_code = "SUPPLIER_ORDER_NOT_FOUND"
        receipt.processed_at = now
        db.commit()
        return {"ok": True, "ignored": True, "message_id": message_id}

    tracking_number = str(params.get("trackingNumber") or "").strip()
    if not tracking_number:
        receipt.processing_status = "ignored"
        receipt.error_code = "TRACKING_NUMBER_MISSING"
        receipt.processed_at = now
        db.commit()
        return {"ok": True, "ignored": True, "message_id": message_id}

    shipment = _upsert_shipment(
        db,
        supplier_order,
        tracking_number=tracking_number,
        logistic_name=params.get("logisticName"),
        tracking_provider=params.get("trackingProvider"),
        tracking_url=params.get("trackingUrl"),
    )
    db.flush()

    try:
        status_code = int(params.get("trackingStatus"))
    except (TypeError, ValueError):
        status_code = None

    shipment.provider_status_code = status_code
    shipment.provider_status_label = None
    shipment.normalized_status = normalize_cj_tracking_code(status_code)
    shipment.last_synced_at = now
    shipment.updated_at = now

    events = _decode_tracking_events(params.get("logisticsTrackEvents"))
    _insert_events(db, shipment, events)

    if shipment.normalized_status == "DELIVERED":
        shipment.delivered_at = shipment.last_event_at or now
    if (
        shipment.normalized_status not in {"PENDING", "PROCESSING"}
        and shipment.shipped_at is None
    ):
        shipment.shipped_at = shipment.last_event_at or now

    receipt.processing_status = "processed"
    receipt.processed_at = now
    db.commit()
    db.refresh(shipment)

    return {
        "ok": True,
        "duplicate": False,
        "shipment_id": shipment.id,
        "status": shipment.normalized_status,
        "message_id": message_id,
    }
