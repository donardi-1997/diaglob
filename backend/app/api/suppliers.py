"""Supplier integration HTTP endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..integrations.cj.client import (
    CJAuthError,
    CJError,
    CJRateLimitError,
    CJTemporaryError,
)
from ..models import OrganizationMembership
from ..services.supplier_connections import (
    SupplierConnectionError,
    SupplierConnectionNotFound,
    connect_cj,
    disconnect_cj,
    get_cj_status,
    test_cj_connection,
)
from .deps import require_permission

router = APIRouter()


class CJConnectRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=200)


def _map_error(exc: Exception):
    if isinstance(exc, SupplierConnectionNotFound):
        code = str(exc)
        status = 404
    elif isinstance(exc, SupplierConnectionError):
        code = str(exc)
        status = {
            "STORE_NOT_ACTIVE": 409,
            "CJ_API_KEY_REQUIRED": 400,
            "SUPPLIER_ENCRYPTION_NOT_CONFIGURED": 503,
            "SUPPLIER_CREDENTIAL_DECRYPT_FAILED": 503,
            "SUPPLIER_CONNECTION_SAVE_FAILED": 409,
        }.get(code, 400)
    elif isinstance(exc, CJAuthError):
        raise HTTPException(
            status_code=401,
            detail={"code": "CJ_AUTH_FAILED", "message": str(exc)},
        )
    elif isinstance(exc, CJRateLimitError):
        raise HTTPException(
            status_code=429,
            detail={"code": "CJ_RATE_LIMITED", "message": str(exc)},
        )
    elif isinstance(exc, CJTemporaryError):
        raise HTTPException(
            status_code=503,
            detail={"code": "CJ_TEMPORARY_ERROR", "message": str(exc)},
        )
    elif isinstance(exc, CJError):
        raise HTTPException(
            status_code=502,
            detail={"code": "CJ_PROVIDER_ERROR", "message": str(exc)},
        )
    else:
        raise exc

    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": code.replace("_", " ").title()},
    )


@router.get("/api/stores/{store_id}/suppliers/cj")
def cj_status(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return get_cj_status(db, membership.organization_id, store_id)
    except SupplierConnectionNotFound as exc:
        _map_error(exc)


@router.post("/api/stores/{store_id}/suppliers/cj/connect")
def cj_connect(
    store_id: int,
    payload: CJConnectRequest,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return connect_cj(
            db,
            membership.organization_id,
            store_id,
            payload.api_key,
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        CJError,
    ) as exc:
        _map_error(exc)


@router.post("/api/stores/{store_id}/suppliers/cj/test")
def cj_test(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return test_cj_connection(
            db,
            membership.organization_id,
            store_id,
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        CJError,
    ) as exc:
        _map_error(exc)


@router.delete("/api/stores/{store_id}/suppliers/cj/disconnect")
def cj_disconnect(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return disconnect_cj(
            db,
            membership.organization_id,
            store_id,
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
    ) as exc:
        _map_error(exc)
