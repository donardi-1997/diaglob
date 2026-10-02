"""Generic multi-carrier shipment tracking orchestration."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..model_domains.shipments import CarrierConnection, Shipment, TrackingEvent
from ..models import Order, Store
from ..settings import get_settings
from .carrier_registry import (
    detect_carrier,
    get_carrier,
    list_carriers,
    normalize_carrier_status,
    tracking_url,
)
from .shipment_tracking import emit_shipment_status_events, serialize_shipment


class CarrierTrackingError(Exception):
    pass


class CarrierConnectionNotFound(CarrierTrackingError):
    pass


class CarrierShipmentNotFound(CarrierTrackingError):
    pass


def _require_store(
    db: Session,
    organization_id: int,
    store_id: int,
) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if store is None:
        raise CarrierTrackingError("STORE_NOT_FOUND")
    return store


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def carrier_catalog(country_code: str | None = None) -> dict[str, Any]:
    return {
        "country_code": country_code.upper() if country_code else None,
        "items": list_carriers(country_code),
    }


def detect_carrier_from_input(
    *,
    carrier_hint: str | None = None,
    tracking_number: str | None = None,
) -> dict[str, Any]:
    return detect_carrier(
        carrier_hint=carrier_hint,
        tracking_number=tracking_number,
    )


def connect_carrier(
    db: Session,
    organization_id: int,
    store_id: int,
    carrier_key: str,
    *,
    integration_mode: str = "webhook",
    external_account_id: str | None = None,
    provider_config: dict | None = None,
) -> dict[str, Any]:
    _require_store(db, organization_id, store_id)
    carrier = get_carrier(carrier_key)
    if carrier is None:
        raise CarrierTrackingError("CARRIER_NOT_SUPPORTED")
    if integration_mode not in carrier.integration_modes:
        raise CarrierTrackingError("CARRIER_INTEGRATION_MODE_NOT_IMPLEMENTED")

    token = secrets.token_urlsafe(32)
    secret_hash = _hash_secret(token)
    now = datetime.utcnow()

    connection = (
        db.query(CarrierConnection)
        .filter(
            CarrierConnection.organization_id == organization_id,
            CarrierConnection.store_id == store_id,
            CarrierConnection.carrier_key == carrier.key,
        )
        .first()
    )
    if connection is None:
        connection = CarrierConnection(
            organization_id=organization_id,
            store_id=store_id,
            carrier_key=carrier.key,
            integration_mode=integration_mode,
            status="connected",
            external_account_id=external_account_id,
            webhook_secret_hash=secret_hash,
            provider_config=provider_config or {},
            connected_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(connection)
    else:
        connection.integration_mode = integration_mode
        connection.status = "connected"
        connection.external_account_id = external_account_id
        connection.webhook_secret_hash = secret_hash
        connection.provider_config = provider_config or {}
        connection.connected_at = now
        connection.updated_at = now
        connection.last_error = None

    db.commit()
    db.refresh(connection)

    callback_base = get_settings().public_api_base_url.rstrip("/")
    return {
        "ok": True,
        "carrier": carrier.serialize(),
        "connection": serialize_carrier_connection(connection),
        "webhook_token": token,
        "callback_url": (
            f"{callback_base}/api/webhooks/carriers/"
            f"{carrier.key}/{token}"
        ),
    }


def disconnect_carrier(
    db: Session,
    organization_id: int,
    store_id: int,
    carrier_key: str,
) -> dict[str, Any]:
    carrier = get_carrier(carrier_key)
    if carrier is None:
        raise CarrierTrackingError("CARRIER_NOT_SUPPORTED")

    connection = (
        db.query(CarrierConnection)
        .filter(
            CarrierConnection.organization_id == organization_id,
            CarrierConnection.store_id == store_id,
            CarrierConnection.carrier_key == carrier.key,
        )
        .first()
    )
    if connection is None:
        raise CarrierConnectionNotFound("CARRIER_CONNECTION_NOT_FOUND")

    connection.status = "disconnected"
    connection.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "carrier_key": carrier.key, "status": "disconnected"}


def serialize_carrier_connection(connection: CarrierConnection) -> dict[str, Any]:
    return {
        "id": connection.id,
        "carrier_key": connection.carrier_key,
        "integration_mode": connection.integration_mode,
        "status": connection.status,
        "external_account_id": connection.external_account_id,
        "provider_config": connection.provider_config or {},
        "last_sync_at": (
            connection.last_sync_at.isoformat() + "Z"
            if connection.last_sync_at
            else None
        ),
        "last_error": connection.last_error,
        "connected_at": connection.connected_at.isoformat() + "Z",
    }


def list_store_carriers(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict[str, Any]:
    store = _require_store(db, organization_id, store_id)
    connections = {
        item.carrier_key: item
        for item in db.query(CarrierConnection)
        .filter(
            CarrierConnection.organization_id == organization_id,
            CarrierConnection.store_id == store_id,
        )
        .all()
    }
    items = []
    for carrier in list_carriers(store.country_code):
        connection = connections.get(carrier["key"])
        items.append(
            {
                **carrier,
                "connection": (
                    serialize_carrier_connection(connection)
                    if connection is not None
                    else None
                ),
            }
        )
    return {
        "store_id": store_id,
        "country_code": store.country_code,
        "items": items,
    }


def register_carrier_shipment(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    carrier_key: str,
    tracking_number: str,
    order_id: int | None = None,
    tracking_url_value: str | None = None,
    source_provider: str | None = None,
) -> dict[str, Any]:
    _require_store(db, organization_id, store_id)
    carrier = get_carrier(carrier_key)
    if carrier is None:
        raise CarrierTrackingError("CARRIER_NOT_SUPPORTED")

    tracking = str(tracking_number or "").strip()
    if not tracking:
        raise CarrierTrackingError("TRACKING_NUMBER_REQUIRED")

    order = None
    if order_id is not None:
        order = (
            db.query(Order)
            .filter(
                Order.id == order_id,
                Order.organization_id == organization_id,
                Order.store_id == store_id,
            )
            .first()
        )
        if order is None:
            raise CarrierTrackingError("ORDER_NOT_FOUND")

    provider = carrier.key
    shipment = (
        db.query(Shipment)
        .filter(
            Shipment.store_id == store_id,
            Shipment.provider == provider,
            Shipment.tracking_number == tracking,
        )
        .first()
    )
    created = shipment is None
    now = datetime.utcnow()
    if shipment is None:
        shipment = Shipment(
            organization_id=organization_id,
            store_id=store_id,
            order_id=order.id if order else None,
            provider=provider,
            tracking_number=tracking,
            tracking_provider=carrier.key,
            tracking_url=(
                tracking_url_value
                or tracking_url(carrier.key, tracking)
            ),
            last_mile_carrier=carrier.name,
            normalized_status="PENDING",
            created_at=now,
            updated_at=now,
        )
        db.add(shipment)
        db.flush()
    else:
        if order is not None:
            shipment.order_id = order.id
        shipment.tracking_provider = carrier.key
        shipment.last_mile_carrier = carrier.name
        shipment.tracking_url = (
            tracking_url_value
            or shipment.tracking_url
            or tracking_url(carrier.key, tracking)
        )
        shipment.updated_at = now

    if source_provider:
        shipment.logistic_name = source_provider[:255]

    db.commit()
    db.refresh(shipment)

    if created:
        emit_shipment_status_events(
            db,
            shipment,
            None,
            event_source_id=f"carrier-register:{carrier.key}:{tracking}",
        )

    return {
        "created": created,
        "shipment": serialize_shipment(shipment),
    }


def list_shipments(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    status: str | None = None,
    carrier_key: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    _require_store(db, organization_id, store_id)
    query = db.query(Shipment).filter(
        Shipment.organization_id == organization_id,
        Shipment.store_id == store_id,
    )
    if status:
        query = query.filter(Shipment.normalized_status == status.upper())
    if carrier_key:
        carrier = get_carrier(carrier_key)
        if carrier is None:
            raise CarrierTrackingError("CARRIER_NOT_SUPPORTED")
        query = query.filter(Shipment.provider == carrier.key)

    shipments = (
        query.order_by(Shipment.updated_at.desc(), Shipment.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [serialize_shipment(item) for item in shipments],
        "total": len(shipments),
    }


def get_shipment(
    db: Session,
    organization_id: int,
    store_id: int,
    shipment_id: int,
) -> Shipment:
    shipment = (
        db.query(Shipment)
        .filter(
            Shipment.id == shipment_id,
            Shipment.organization_id == organization_id,
            Shipment.store_id == store_id,
        )
        .first()
    )
    if shipment is None:
        raise CarrierShipmentNotFound("SHIPMENT_NOT_FOUND")
    return shipment


def sync_registered_shipment(
    db: Session,
    organization_id: int,
    store_id: int,
    shipment_id: int,
) -> dict[str, Any]:
    shipment = get_shipment(
        db,
        organization_id,
        store_id,
        shipment_id,
    )
    if shipment.provider == "cj" and shipment.supplier_order_id:
        from .shipment_tracking import sync_cj_shipment

        return sync_cj_shipment(
            db,
            organization_id,
            store_id,
            shipment.supplier_order_id,
        )

    carrier = get_carrier(shipment.provider)
    return {
        "available": True,
        "sync_mode": "webhook",
        "direct_sync": False,
        "reason": "PUSH_UPDATES_REQUIRED",
        "carrier": carrier.serialize() if carrier else None,
        "shipment": serialize_shipment(shipment),
    }


def _parse_event_at(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if value:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            pass
    return datetime.utcnow()


def _event_key(payload: dict[str, Any], normalized_status: str) -> str:
    supplied = str(payload.get("source_event_id") or "").strip()
    if supplied:
        return hashlib.sha256(supplied.encode("utf-8")).hexdigest()[:64]
    canonical = json.dumps(
        {
            "tracking_number": payload.get("tracking_number"),
            "status": normalized_status,
            "status_label": payload.get("status_label"),
            "event_at": str(payload.get("event_at") or ""),
            "location": payload.get("location"),
            "description": payload.get("description"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:64]


def _resolve_webhook_connection(
    db: Session,
    carrier_key: str,
    webhook_token: str,
) -> CarrierConnection:
    carrier = get_carrier(carrier_key)
    if carrier is None:
        raise CarrierTrackingError("CARRIER_NOT_SUPPORTED")
    secret_hash = _hash_secret(webhook_token)
    connection = (
        db.query(CarrierConnection)
        .filter(
            CarrierConnection.carrier_key == carrier.key,
            CarrierConnection.webhook_secret_hash == secret_hash,
            CarrierConnection.status == "connected",
        )
        .first()
    )
    if connection is None:
        raise CarrierConnectionNotFound("CARRIER_WEBHOOK_UNAUTHORIZED")
    return connection


def ingest_carrier_webhook(
    db: Session,
    carrier_key: str,
    webhook_token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    connection = _resolve_webhook_connection(
        db,
        carrier_key,
        webhook_token,
    )
    tracking = str(payload.get("tracking_number") or "").strip()
    if not tracking:
        raise CarrierTrackingError("TRACKING_NUMBER_REQUIRED")

    shipment = (
        db.query(Shipment)
        .filter(
            Shipment.organization_id == connection.organization_id,
            Shipment.store_id == connection.store_id,
            Shipment.provider == connection.carrier_key,
            Shipment.tracking_number == tracking,
        )
        .first()
    )
    if shipment is None:
        order_id = payload.get("order_id")
        if order_id is None:
            raise CarrierShipmentNotFound("SHIPMENT_NOT_REGISTERED")
        registered = register_carrier_shipment(
            db,
            connection.organization_id,
            connection.store_id,
            carrier_key=connection.carrier_key,
            tracking_number=tracking,
            order_id=int(order_id),
            tracking_url_value=payload.get("tracking_url"),
            source_provider="carrier_webhook",
        )
        shipment = get_shipment(
            db,
            connection.organization_id,
            connection.store_id,
            int(registered["shipment"]["id"]),
        )

    previous_status = shipment.normalized_status
    normalized = normalize_carrier_status(
        payload.get("status"),
        payload.get("status_label"),
    )
    now = datetime.utcnow()
    event_at = _parse_event_at(payload.get("event_at"))

    shipment.normalized_status = normalized
    shipment.provider_status_label = (
        str(payload.get("status_label") or payload.get("status") or "")[:255]
        or None
    )
    shipment.tracking_provider = connection.carrier_key
    carrier = get_carrier(connection.carrier_key)
    shipment.last_mile_carrier = carrier.name if carrier else connection.carrier_key
    shipment.last_mile_tracking_number = tracking
    shipment.tracking_url = (
        payload.get("tracking_url")
        or shipment.tracking_url
        or tracking_url(connection.carrier_key, tracking)
    )
    shipment.destination_country_code = (
        str(payload.get("destination_country_code") or "").strip().upper()[:20]
        or shipment.destination_country_code
    )
    shipment.last_event_at = max(
        [value for value in (shipment.last_event_at, event_at) if value is not None]
    )
    shipment.last_synced_at = now
    shipment.updated_at = now

    if normalized == "DELIVERED":
        shipment.delivered_at = event_at
    if normalized not in {"PENDING"} and shipment.shipped_at is None:
        shipment.shipped_at = event_at

    provider_event_key = _event_key(payload, normalized)
    existing = (
        db.query(TrackingEvent)
        .filter(
            TrackingEvent.shipment_id == shipment.id,
            TrackingEvent.provider_event_key == provider_event_key,
        )
        .first()
    )
    duplicate = existing is not None
    if existing is None:
        event = TrackingEvent(
            shipment_id=shipment.id,
            provider_event_key=provider_event_key,
            normalized_status=normalized,
            description=(
                str(payload.get("description") or "")[:10000]
                or shipment.provider_status_label
            ),
            location=str(payload.get("location") or "")[:500] or None,
            event_at=event_at,
            created_at=now,
        )
        db.add(event)

    connection.last_sync_at = now
    connection.last_error = None
    connection.updated_at = now
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = True
        shipment = (
            db.query(Shipment)
            .filter(
                Shipment.organization_id == connection.organization_id,
                Shipment.store_id == connection.store_id,
                Shipment.provider == connection.carrier_key,
                Shipment.tracking_number == tracking,
            )
            .one()
        )

    db.refresh(shipment)
    if not duplicate:
        emit_shipment_status_events(
            db,
            shipment,
            previous_status,
            event_source_id=f"carrier:{connection.carrier_key}:{provider_event_key}",
        )

    return {
        "ok": True,
        "duplicate": duplicate,
        "shipment_id": shipment.id,
        "status": shipment.normalized_status,
        "shipment": serialize_shipment(shipment),
    }
