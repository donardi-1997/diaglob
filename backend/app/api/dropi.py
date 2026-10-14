"""Dropi HTTP router."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..integrations.dropi_native import DropiNativeError
from ..models import DropiConnection, OrganizationMembership
from ..services.dropi_mappings import (
    DropiMappingError,
    delete_mapping as svc_delete_mapping,
    list_mappings as svc_list_mappings,
    upsert_mapping as svc_upsert_mapping,
)
from ..services.dropi_readiness import (
    DropiReadinessError,
    order_readiness as svc_order_readiness,
)
from .deps import require_permission
from ..services.dropi_service import (
    DropiConnectionError,
    DropiNotFoundError,
    connect as svc_connect,
    disconnect as svc_disconnect,
    get_connection as svc_get_connection,
    inspect_product as svc_inspect_product,
    preview_catalog as svc_preview_catalog,
    test_connection as svc_test_connection,
)

router = APIRouter()


class DropiConnectRequest(BaseModel):
    api_token: str = Field(min_length=1, max_length=2048)


class DropiVariantMappingRequest(BaseModel):
    external_product_id: str = Field(min_length=1, max_length=255)
    external_variant_id: str = Field(min_length=1, max_length=255)
    external_sku: str | None = Field(default=None, max_length=255)
    active: bool = True


def _map_dropi_error(exc: Exception):
    if isinstance(exc, DropiNotFoundError):
        code = str(exc)
        if code == "DROPPI_NOT_CONNECTED":
            raise HTTPException(
                status_code=404,
                detail={"code": code, "message": "Esta tienda no tiene Dropi conectado."},
            )
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, DropiConnectionError):
        code = str(exc)
        detail_map = {
            "STORE_NOT_ACTIVE": (409, {"code": code, "message": "La tienda debe estar activa para conectar Dropi."}),
            "DROPPI_ALREADY_CONNECTED": (409, {"code": code, "message": "Esta tienda ya tiene una conexión con Dropi."}),
            "DROPPI_TOKEN_REQUIRED": (400, {"code": code, "message": "El token de Dropi es obligatorio."}),
            "DROPPI_ENCRYPTION_NOT_CONFIGURED": (503, {"code": code, "message": "No fue posible almacenar las credenciales de Dropi."}),
            "DROPPI_CONNECTION_SAVE_FAILED": (409, {"code": code, "message": "No fue posible guardar la conexión con Dropi."}),
            "DROPPI_NOT_VERIFIED": (409, {"code": code, "message": "Valida primero el token de Dropi."}),
            "DROPPI_CREDENTIALS_UNAVAILABLE": (503, {"code": code, "message": "No fue posible recuperar las credenciales de Dropi."}),
        }
        status, detail = detail_map.get(code, (409, code))
        raise HTTPException(status_code=status, detail=detail)
    if isinstance(exc, DropiNativeError):
        code = str(exc)
        if code == "DROPI_PARTNER_APPROVAL_REQUIRED":
            status = 503
            message = "La integración directa requiere aprobación de Dropi. No se realizaron llamadas al proveedor."
        elif code in {"DROPI_TOKEN_REQUIRED", "DROPI_INVALID_LIMIT", "DROPI_INVALID_PRODUCT_ID", "DROPI_COUNTRY_UNSUPPORTED"}:
            status = 400
            message = "Revisa la configuración de Dropi."
        elif code in {"DROPI_AUTH_FAILED", "DROPI_AUTH_OR_PROVIDER_ERROR"}:
            status = 422
            message = "Dropi no validó el token o la operación."
        else:
            status = 502
            message = "No se pudo consultar Dropi."
        raise HTTPException(status_code=status, detail={"code": code, "message": message})
    raise exc


@router.get("/api/stores/{store_id}/dropi")
def get_dropi_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return svc_get_connection(db, membership.organization_id, store_id)
    except DropiNotFoundError as exc:
        _map_dropi_error(exc)


@router.post("/api/stores/{store_id}/dropi/connect")
def connect_dropi(
    store_id: int,
    payload: DropiConnectRequest,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return svc_connect(db, membership.organization_id, store_id, payload.api_token)
    except (DropiNotFoundError, DropiConnectionError, DropiNativeError) as exc:
        _map_dropi_error(exc)


@router.delete("/api/stores/{store_id}/dropi/disconnect")
def disconnect_dropi(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return svc_disconnect(db, membership.organization_id, store_id)
    except (DropiNotFoundError, DropiConnectionError) as exc:
        _map_dropi_error(exc)



@router.post("/api/stores/{store_id}/dropi/test")
def test_dropi_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_test_connection(db, membership.organization_id, store_id)
    except (DropiNotFoundError, DropiConnectionError, DropiNativeError) as exc:
        _map_dropi_error(exc)


@router.get("/api/stores/{store_id}/dropi/preview/products")
def preview_dropi_products(
    store_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    membership: OrganizationMembership = Depends(require_permission("stores.read")),
    db: Session = Depends(get_db),
):
    try:
        return svc_preview_catalog(db, membership.organization_id, store_id, limit=limit)
    except (DropiNotFoundError, DropiConnectionError, DropiNativeError) as exc:
        _map_dropi_error(exc)



@router.get("/api/stores/{store_id}/dropi/products/{product_id}")
def inspect_dropi_product_stock(
    store_id: int,
    product_id: str,
    membership: OrganizationMembership = Depends(require_permission("commerce.read")),
    db: Session = Depends(get_db),
):
    try:
        return svc_inspect_product(
            db, membership.organization_id, store_id, product_id
        )
    except (DropiNotFoundError, DropiConnectionError, DropiNativeError) as exc:
        _map_dropi_error(exc)


def _map_mapping_error(exc: Exception):
    code = str(exc)
    if code in {"DROPI_STORE_NOT_FOUND", "DROPI_VARIANT_NOT_FOUND", "DROPI_MAPPING_NOT_FOUND", "DROPI_ORDER_NOT_FOUND"}:
        status = 404
    elif code == "DROPI_MAPPING_IDS_REQUIRED":
        status = 400
    else:
        status = 409
    raise HTTPException(status_code=status, detail={"code": code, "message": "No fue posible completar la operación con Dropi."})


@router.get("/api/stores/{store_id}/dropi/mappings")
def list_dropi_mappings(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("commerce.read")),
    db: Session = Depends(get_db),
):
    try:
        return svc_list_mappings(db, membership.organization_id, store_id)
    except DropiMappingError as exc:
        _map_mapping_error(exc)


@router.put("/api/stores/{store_id}/dropi/mappings/{variant_id}")
def upsert_dropi_mapping(
    store_id: int,
    variant_id: int,
    payload: DropiVariantMappingRequest,
    membership: OrganizationMembership = Depends(require_permission("commerce.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_upsert_mapping(
            db, membership.organization_id, store_id, variant_id,
            external_product_id=payload.external_product_id,
            external_variant_id=payload.external_variant_id,
            external_sku=payload.external_sku,
            active=payload.active,
        )
    except DropiMappingError as exc:
        _map_mapping_error(exc)


@router.delete("/api/stores/{store_id}/dropi/mappings/{variant_id}")
def delete_dropi_mapping(
    store_id: int,
    variant_id: int,
    membership: OrganizationMembership = Depends(require_permission("commerce.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_delete_mapping(db, membership.organization_id, store_id, variant_id)
    except DropiMappingError as exc:
        _map_mapping_error(exc)


@router.get("/api/stores/{store_id}/dropi/orders/{order_id}/readiness")
def dropi_shopify_order_readiness(
    store_id: int,
    order_id: int,
    membership: OrganizationMembership = Depends(require_permission("commerce.read")),
    db: Session = Depends(get_db),
):
    try:
        return svc_order_readiness(db, membership.organization_id, store_id, order_id)
    except DropiReadinessError as exc:
        _map_mapping_error(exc)


@router.post("/api/webhooks/dropi/{webhook_token}")
async def dropi_webhook(
    webhook_token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.webhook_token == webhook_token,
        )
        .first()
    )

    if not connection or connection.status != "connected":
        raise HTTPException(
            status_code=404,
            detail="Webhook not found",
        )

    # TODO: map Dropi events when official API is documented.
    # Currently only confirms receipt; does not assume schema
    # or modify orders. Body is read and ignored.
    await request.body()

    return {"ok": True}
