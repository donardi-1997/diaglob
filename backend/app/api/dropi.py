"""Dropi HTTP router."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import DropiConnection, OrganizationMembership
from .deps import require_permission
from ..services.dropi_service import (
    DropiConnectionError,
    DropiNotFoundError,
    connect as svc_connect,
    disconnect as svc_disconnect,
    get_connection as svc_get_connection,
)

router = APIRouter()


class DropiConnectRequest(BaseModel):
    api_token: str


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
        }
        status, detail = detail_map.get(code, (409, code))
        raise HTTPException(status_code=status, detail=detail)
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
    except (DropiNotFoundError, DropiConnectionError) as exc:
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
