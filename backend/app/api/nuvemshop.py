"""Nuvemshop HTTP router.

Thin HTTP layer — business logic lives in services/nuvemshop_service.py.
"""
import hashlib
import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CommerceConnection, OrganizationMembership
from .deps import require_permission
from ..services.nuvemshop_service import (
    NuvemshopConnectionError,
    NuvemshopNotFoundError,
    NuvemshopOAuthError,
    NuvemshopProviderError,
    connect_account as svc_connect,
    disconnect as svc_disconnect,
    get_connection_status as svc_get_status,
    get_oauth_url as svc_get_oauth_url,
    process_oauth_callback as svc_process_oauth_callback,
    process_webhook_event,
    sync_orders as svc_sync_orders,
    sync_products as svc_sync_products,
)
from ..integrations.nuvemshop.client import NuvemshopError

router = APIRouter()


# --- DTOs ---


class NuvemshopConnectRequest(BaseModel):
    store_id: int


# --- Error mapping ---


def _map_nuvemshop_error(exc: Exception):
    if isinstance(exc, NuvemshopNotFoundError):
        code = str(exc)
        if code == "NUVEMSHOP_NOT_CONNECTED":
            raise HTTPException(
                status_code=404,
                detail={"code": code, "message": "Nuvemshop no está conectado."},
            )
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, NuvemshopConnectionError):
        code = str(exc)
        detail_map = {
            "STORE_NOT_ACTIVE": (409, {"code": code, "message": "La tienda debe estar activa para conectar Nuvemshop."}),
            "COMMERCE_ALREADY_CONNECTED": (409, {"code": code, "message": "Esta tienda ya tiene una integración de comercio."}),
            "NUVEMSHOP_STORE_ALREADY_CONNECTED": (409, {"code": code, "message": "Esta tienda Nuvemshop ya está conectada a DIAGLOB."}),
            "TRIAL_STORE_ALREADY_USED": (409, {"code": code, "message": "Esta tienda ya utilizó una prueba gratuita de DIAGLOB. Puedes conectarla con un plan de pago."}),
            "TRIAL_NOT_AVAILABLE": (409, {"code": code, "message": "La prueba gratuita ya no está disponible para esta cuenta."}),
            "NUVEMSHOP_NOT_CONFIGURED": (503, {"code": code, "message": "Nuvemshop no está configurado en el servidor."}),
            "TOKEN_EXCHANGE_FAILED": (502, {"code": code, "message": "No fue posible completar la autenticación con Nuvemshop."}),
            "STORE_INFO_FAILED": (502, {"code": code, "message": "No fue posible obtener la información de la tienda."}),
        }
        status, detail = detail_map.get(code, (409, code))
        raise HTTPException(status_code=status, detail=detail)
    if isinstance(exc, NuvemshopOAuthError):
        code = str(exc)
        detail_map = {
            "Invalid or already used OAuth state": (400, "Estado OAuth inválido o ya utilizado"),
            "OAuth state expired": (400, "El estado OAuth ha expirado"),
            "OAuth state does not match the target store": (400, "El estado OAuth no coincide con la tienda"),
            "NUVEMSHOP_NOT_CONFIGURED": (503, "Nuvemshop no está configurado"),
        }
        status, detail = detail_map.get(code, (400, code))
        raise HTTPException(status_code=status, detail=detail)
    if isinstance(exc, NuvemshopProviderError):
        raise HTTPException(status_code=502, detail=str(exc))
    raise exc


# --- Endpoints ---


@router.post("/api/stores/{store_id}/nuvemshop/connect")
def start_nuvemshop_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return svc_get_oauth_url(
            db,
            membership.organization_id,
            store_id,
            membership.user_id,
        )
    except (NuvemshopConnectionError, NuvemshopOAuthError) as exc:
        _map_nuvemshop_error(exc)


@router.get("/api/nuvemshop/callback")
def nuvemshop_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")

    if not code or not state:
        raise HTTPException(
            status_code=400,
            detail="Missing required OAuth parameters",
        )

    try:
        # State lookup returns org/store info from persisted state.
        # The callback itself does not require user auth.
        from ..models import NuvemshopOAuthState

        oauth_state = (
            db.query(NuvemshopOAuthState)
            .filter(
                NuvemshopOAuthState.state == state,
                NuvemshopOAuthState.used.is_(False),
            )
            .first()
        )
        if not oauth_state:
            raise NuvemshopOAuthError("Invalid or already used OAuth state")

        result = svc_process_oauth_callback(
            db,
            code,
            state,
            oauth_state.organization_id,
            oauth_state.store_id,
        )

        # After successful token exchange, persist the connection
        svc_connect(
            db,
            oauth_state.organization_id,
            oauth_state.store_id,
            result["encrypted_token"],
            result["nuvemshop_store_id"],
            result["store_name"],
            result["currency"],
            result["timezone"],
            result["country"],
        )

        return RedirectResponse(url="/settings/commerce?nuvemshop=connected")

    except (NuvemshopOAuthError, NuvemshopConnectionError, NuvemshopProviderError) as exc:
        _map_nuvemshop_error(exc)


@router.get("/api/stores/{store_id}/nuvemshop/status")
def get_nuvemshop_status(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.read")
    ),
    db: Session = Depends(get_db),
):
    return svc_get_status(
        db,
        membership.organization_id,
        store_id,
    )


@router.delete("/api/stores/{store_id}/nuvemshop/disconnect")
def disconnect_nuvemshop(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return svc_disconnect(
            db,
            membership.organization_id,
            store_id,
        )
    except NuvemshopNotFoundError as exc:
        _map_nuvemshop_error(exc)


@router.post("/api/stores/{store_id}/nuvemshop/sync/products")
def sync_nuvemshop_products(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return svc_sync_products(
            db,
            membership.organization_id,
            store_id,
        )
    except NuvemshopNotFoundError as exc:
        _map_nuvemshop_error(exc)
    except NuvemshopError as exc:
        raise HTTPException(
            status_code=502,
            detail={"ok": False, "error": str(exc)},
        )


@router.post("/api/stores/{store_id}/nuvemshop/sync/orders")
def sync_nuvemshop_orders(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return svc_sync_orders(
            db,
            membership.organization_id,
            store_id,
        )
    except NuvemshopNotFoundError as exc:
        _map_nuvemshop_error(exc)
    except NuvemshopError as exc:
        raise HTTPException(
            status_code=502,
            detail={"ok": False, "error": str(exc)},
        )


# --- Webhook verification ---


def _verify_nuvemshop_signature(
    raw_body: bytes,
    hmac_header: str | None,
) -> bool:
    """Verify Nuvemshop webhook HMAC-SHA256 signature.

    Uses NUVEMSHOP_CLIENT_SECRET as the HMAC key.
    Returns False if header is missing or signature doesn't match.
    """
    client_secret = os.getenv("NUVEMSHOP_CLIENT_SECRET", "")
    if not client_secret or not hmac_header:
        return False
    expected = hmac.new(
        client_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, hmac_header)


# --- Webhook endpoint ---


@router.post("/api/webhooks/nuvemshop")
async def nuvemshop_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    hmac_header = request.headers.get(
        "x-linkedstore-hmac-sha256"
    )

    if not _verify_nuvemshop_signature(raw_body, hmac_header):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload",
        )

    event = payload.get("event", "")
    store_id_ns = payload.get("store_id")
    resource_id = payload.get("id")

    if not event or not store_id_ns:
        raise HTTPException(
            status_code=400,
            detail="Missing event or store_id",
        )

    # Look up the connection for this Nuvemshop store
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider == "nuvemshop",
            CommerceConnection.external_store_url == str(store_id_ns),
            CommerceConnection.status == "connected",
        )
        .first()
    )

    if not connection:
        # Unknown store — acknowledge but do nothing
        return {"ok": True}

    try:
        process_webhook_event(
            db,
            connection,
            event,
            resource_id,
        )
    except Exception as exc:
        # Log but don't fail — Nuvemshop retries on non-2XX
        import logging
        logging.getLogger(__name__).warning(
            "Nuvemshop webhook processing error: %s", exc
        )

    return {"ok": True}


# --- Uninstall callback ---


@router.post("/api/webhooks/nuvemshop/uninstall")
async def nuvemshop_uninstall_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    hmac_header = request.headers.get(
        "x-linkedstore-hmac-sha256"
    )

    if not _verify_nuvemshop_signature(raw_body, hmac_header):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload",
        )

    store_id_ns = payload.get("store_id")
    if not store_id_ns:
        raise HTTPException(
            status_code=400,
            detail="Missing store_id",
        )

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider == "nuvemshop",
            CommerceConnection.external_store_url == str(store_id_ns),
        )
        .first()
    )

    if connection:
        # Mark as disconnected, don't delete — preserve audit trail
        connection.status = "disconnected"
        connection.last_error = "App uninstalled from Nuvemshop store"
        db.commit()

    return {"ok": True}
