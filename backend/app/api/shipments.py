"""Generic carrier and shipment tracking HTTP endpoints."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..services.carrier_tracking import (
    CarrierConnectionNotFound,
    CarrierShipmentNotFound,
    CarrierTrackingError,
    carrier_catalog,
    connect_carrier,
    detect_carrier_from_input,
    disconnect_carrier,
    get_shipment,
    ingest_carrier_webhook,
    list_shipments,
    list_store_carriers,
    register_carrier_shipment,
    sync_registered_shipment,
)
from ..services.shipment_tracking import serialize_shipment
from .deps import get_allowed_store_ids, require_permission


router = APIRouter()


class CarrierDetectRequest(BaseModel):
    carrier_hint: str | None = Field(default=None, max_length=255)
    tracking_number: str | None = Field(default=None, max_length=255)


class CarrierConnectRequest(BaseModel):
    integration_mode: Literal["webhook"] = "webhook"
    external_account_id: str | None = Field(default=None, max_length=255)
    provider_config: dict[str, Any] | None = None


class ShipmentCreateRequest(BaseModel):
    carrier_key: str = Field(min_length=1, max_length=50)
    tracking_number: str = Field(min_length=1, max_length=255)
    order_id: int | None = Field(default=None, ge=1)
    tracking_url: str | None = Field(default=None, max_length=2000)
    source_provider: str | None = Field(default=None, max_length=255)


class CarrierWebhookPayload(BaseModel):
    tracking_number: str = Field(min_length=1, max_length=255)
    status: str | None = Field(default=None, max_length=100)
    status_label: str | None = Field(default=None, max_length=255)
    source_event_id: str | None = Field(default=None, max_length=500)
    event_at: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=10000)
    tracking_url: str | None = Field(default=None, max_length=2000)
    destination_country_code: str | None = Field(default=None, max_length=20)
    order_id: int | None = Field(default=None, ge=1)


def _require_store_access(
    membership: OrganizationMembership,
    store_id: int,
) -> None:
    allowed = get_allowed_store_ids(membership)
    if allowed is not None and store_id not in allowed:
        raise HTTPException(status_code=403, detail="Store access denied")


def _raise_carrier_error(exc: Exception) -> None:
    code = str(exc)
    if isinstance(exc, CarrierConnectionNotFound):
        status = 401 if code == "CARRIER_WEBHOOK_UNAUTHORIZED" else 404
    elif isinstance(exc, CarrierShipmentNotFound):
        status = 404
    elif code in {"STORE_NOT_FOUND", "ORDER_NOT_FOUND"}:
        status = 404
    elif code == "CARRIER_INTEGRATION_MODE_NOT_IMPLEMENTED":
        status = 409
    else:
        status = 400
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": code.replace("_", " ").title()},
    ) from exc


@router.get("/api/carriers")
def carriers_catalog(
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
):
    return carrier_catalog(country_code)


@router.post("/api/carriers/detect")
def carriers_detect(payload: CarrierDetectRequest):
    return detect_carrier_from_input(
        carrier_hint=payload.carrier_hint,
        tracking_number=payload.tracking_number,
    )


@router.get("/api/stores/{store_id}/carriers")
def store_carriers(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    _require_store_access(membership, store_id)
    try:
        return list_store_carriers(
            db,
            membership.organization_id,
            store_id,
        )
    except CarrierTrackingError as exc:
        _raise_carrier_error(exc)


@router.post("/api/stores/{store_id}/carriers/{carrier_key}/connect")
def carrier_connect(
    store_id: int,
    carrier_key: str,
    payload: CarrierConnectRequest,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    _require_store_access(membership, store_id)
    try:
        return connect_carrier(
            db,
            membership.organization_id,
            store_id,
            carrier_key,
            integration_mode=payload.integration_mode,
            external_account_id=payload.external_account_id,
            provider_config=payload.provider_config,
        )
    except CarrierTrackingError as exc:
        _raise_carrier_error(exc)


@router.delete("/api/stores/{store_id}/carriers/{carrier_key}")
def carrier_disconnect(
    store_id: int,
    carrier_key: str,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    _require_store_access(membership, store_id)
    try:
        return disconnect_carrier(
            db,
            membership.organization_id,
            store_id,
            carrier_key,
        )
    except CarrierTrackingError as exc:
        _raise_carrier_error(exc)


@router.get("/api/stores/{store_id}/shipments")
def shipments_list(
    store_id: int,
    status: str | None = Query(default=None, max_length=40),
    carrier_key: str | None = Query(default=None, max_length=50),
    limit: int = Query(default=100, ge=1, le=500),
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    _require_store_access(membership, store_id)
    try:
        return list_shipments(
            db,
            membership.organization_id,
            store_id,
            status=status,
            carrier_key=carrier_key,
            limit=limit,
        )
    except CarrierTrackingError as exc:
        _raise_carrier_error(exc)


@router.post("/api/stores/{store_id}/shipments")
def shipment_register(
    store_id: int,
    payload: ShipmentCreateRequest,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    _require_store_access(membership, store_id)
    try:
        return register_carrier_shipment(
            db,
            membership.organization_id,
            store_id,
            carrier_key=payload.carrier_key,
            tracking_number=payload.tracking_number,
            order_id=payload.order_id,
            tracking_url_value=payload.tracking_url,
            source_provider=payload.source_provider,
        )
    except CarrierTrackingError as exc:
        _raise_carrier_error(exc)


@router.get("/api/stores/{store_id}/shipments/{shipment_id}")
def shipment_detail(
    store_id: int,
    shipment_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    _require_store_access(membership, store_id)
    try:
        shipment = get_shipment(
            db,
            membership.organization_id,
            store_id,
            shipment_id,
        )
        return serialize_shipment(shipment)
    except CarrierTrackingError as exc:
        _raise_carrier_error(exc)


@router.post("/api/stores/{store_id}/shipments/{shipment_id}/sync")
def shipment_sync(
    store_id: int,
    shipment_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    _require_store_access(membership, store_id)
    try:
        return sync_registered_shipment(
            db,
            membership.organization_id,
            store_id,
            shipment_id,
        )
    except CarrierTrackingError as exc:
        _raise_carrier_error(exc)


@router.post("/api/webhooks/carriers/{carrier_key}/{webhook_token}")
def carrier_webhook(
    carrier_key: str,
    webhook_token: str,
    payload: CarrierWebhookPayload,
    db: Session = Depends(get_db),
):
    try:
        return ingest_carrier_webhook(
            db,
            carrier_key,
            webhook_token,
            payload.model_dump(),
        )
    except CarrierTrackingError as exc:
        _raise_carrier_error(exc)
