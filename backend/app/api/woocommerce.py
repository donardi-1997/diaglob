"""Public, tenant-scoped WooCommerce endpoints for the Dropify bridge."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..integrations.woocommerce_bridge import WooCommerceError
from ..models import OrganizationMembership, Store
from ..services import woocommerce_service as service
from .deps import require_permission

router = APIRouter()


class WooConnectRequest(BaseModel):
    site_url: str = Field(min_length=10, max_length=500)
    consumer_key: str = Field(min_length=1, max_length=255)
    consumer_secret: str = Field(min_length=1, max_length=255)


def _scope(store_id: int, membership: OrganizationMembership, db: Session) -> None:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if not membership.all_stores and store.id not in {
        assigned.id for assigned in membership.stores if not assigned.deleted
    }:
        raise HTTPException(status_code=404, detail="Store not found")


def _raise_error(exc: Exception) -> None:
    code = str(exc)
    status = {
        "WOO_STORE_NOT_FOUND": 404,
        "WOO_NOT_CONNECTED": 404,
        "WOO_STORE_INACTIVE": 409,
        "COMMERCE_ALREADY_CONNECTED": 409,
        "WOO_SITE_ALREADY_CONNECTED": 409,
        "WOO_TRIAL_IDENTITY_ALREADY_USED": 409,
        "WOO_CONNECTION_CONFLICT": 409,
        "WOO_ENCRYPTION_NOT_CONFIGURED": 503,
        "WOO_CREDENTIALS_UNAVAILABLE": 503,
        "WOO_CREDENTIALS_MISSING": 409,
        "WOO_INVALID_URL": 400,
        "WOO_UNSAFE_DESTINATION": 400,
        "WOO_CREDENTIALS_REQUIRED": 400,
        "WOO_INVALID_LIMIT": 400,
        "WOO_UNSUPPORTED_RESOURCE": 400,
        "WOO_DNS_UNAVAILABLE": 502,
        "WOO_AUTH_FAILED": 401,
        "WOO_API_NOT_FOUND": 502,
        "WOO_REDIRECT_DENIED": 502,
        "WOO_PROVIDER_ERROR": 502,
        "WOO_INVALID_RESPONSE": 502,
        "WOO_RESPONSE_TOO_LARGE": 502,
        "WOO_TIMEOUT": 504,
        "WOO_UNREACHABLE": 502,
    }.get(code, 502)
    raise HTTPException(status_code=status, detail={"code": code, "message": code}) from exc


@router.get("/api/stores/{store_id}/woocommerce")
def get_status(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.read")),
    db: Session = Depends(get_db),
):
    _scope(store_id, membership, db)
    try:
        return service.status(db, membership.organization_id, store_id)
    except service.WooConnectionError as exc:
        _raise_error(exc)


@router.post("/api/stores/{store_id}/woocommerce/connect")
def connect(
    store_id: int,
    payload: WooConnectRequest,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    _scope(store_id, membership, db)
    try:
        return service.connect(
            db,
            membership.organization_id,
            store_id,
            site_url=payload.site_url,
            consumer_key=payload.consumer_key,
            consumer_secret=payload.consumer_secret,
        )
    except (WooCommerceError, service.WooConnectionError) as exc:
        _raise_error(exc)


@router.post("/api/stores/{store_id}/woocommerce/test")
def test_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    _scope(store_id, membership, db)
    try:
        return service.test(db, membership.organization_id, store_id)
    except (WooCommerceError, service.WooConnectionError) as exc:
        _raise_error(exc)


@router.get("/api/stores/{store_id}/woocommerce/preview/products")
def preview_products(
    store_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    membership: OrganizationMembership = Depends(require_permission("commerce.read")),
    db: Session = Depends(get_db),
):
    _scope(store_id, membership, db)
    try:
        return service.preview(db, membership.organization_id, store_id, "products", limit)
    except (WooCommerceError, service.WooConnectionError) as exc:
        _raise_error(exc)


@router.get("/api/stores/{store_id}/woocommerce/preview/orders")
def preview_orders(
    store_id: int,
    limit: int = Query(default=5, ge=1, le=20),
    membership: OrganizationMembership = Depends(require_permission("commerce.read")),
    db: Session = Depends(get_db),
):
    _scope(store_id, membership, db)
    try:
        return service.preview(db, membership.organization_id, store_id, "orders", limit)
    except (WooCommerceError, service.WooConnectionError) as exc:
        _raise_error(exc)


@router.delete("/api/stores/{store_id}/woocommerce/disconnect")
def disconnect(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    _scope(store_id, membership, db)
    try:
        return service.disconnect(db, membership.organization_id, store_id)
    except service.WooConnectionError as exc:
        _raise_error(exc)
