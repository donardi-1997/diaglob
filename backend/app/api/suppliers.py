"""Supplier integration HTTP endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
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
from ..services.shipment_tracking import (
    ShipmentNotFound,
    ShipmentTrackingError,
    configure_cj_logistics_webhook,
    get_supplier_order_shipment,
    sync_cj_shipment,
)
from ..services.supplier_catalog import (
    get_cj_product,
    get_cj_stock,
    list_cj_products,
    list_cj_variants,
    quote_cj_freight,
)
from ..services.supplier_orders import (
    SupplierOrderError,
    SupplierOrderNotFound,
    cancel_cj_supplier_order,
    create_cj_supplier_order,
    sync_cj_supplier_order,
)
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


class CJFreightItemRequest(BaseModel):
    variant_id: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=1000)


class CJSupplierOrderItemRequest(BaseModel):
    order_item_id: int = Field(ge=1)
    external_variant_id: str = Field(min_length=1, max_length=255)
    quantity: int = Field(ge=1, le=1000)


class CJSupplierShippingRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=50)
    country_code: str = Field(min_length=2, max_length=2)
    country: str = Field(min_length=1, max_length=50)
    province: str = Field(min_length=1, max_length=50)
    city: str = Field(min_length=1, max_length=50)
    address1: str = Field(min_length=1, max_length=500)
    address2: str | None = Field(default=None, max_length=500)
    county: str | None = Field(default=None, max_length=50)
    house_number: str | None = Field(default=None, max_length=20)
    zip: str | None = Field(default=None, max_length=20)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=50)
    tax_id: str | None = Field(default=None, max_length=20)


class CJSupplierOrderCreateRequest(BaseModel):
    order_id: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=100)
    from_country_code: str = Field(min_length=2, max_length=2)
    logistic_name: str = Field(min_length=1, max_length=50)
    shipping: CJSupplierShippingRequest
    items: list[CJSupplierOrderItemRequest] = Field(min_length=1, max_length=20)
    remark: str | None = Field(default=None, max_length=500)
    is_sandbox: bool = False


class CJFreightQuoteRequest(BaseModel):
    start_country_code: str = Field(min_length=2, max_length=2)
    end_country_code: str = Field(min_length=2, max_length=2)
    zip_code: str | None = Field(default=None, max_length=50)
    items: list[CJFreightItemRequest] = Field(min_length=1, max_length=100)


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


@router.get("/api/stores/{store_id}/suppliers/cj/products")
def cj_products(
    store_id: int,
    query: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1, le=1000),
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return list_cj_products(
            db,
            membership.organization_id,
            store_id,
            query=query,
            limit=limit,
            page=page,
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        CJError,
    ) as exc:
        _map_error(exc)


@router.get("/api/stores/{store_id}/suppliers/cj/products/{product_id}")
def cj_product_detail(
    store_id: int,
    product_id: str,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return get_cj_product(
            db,
            membership.organization_id,
            store_id,
            product_id,
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        CJError,
    ) as exc:
        _map_error(exc)


@router.get(
    "/api/stores/{store_id}/suppliers/cj/products/{product_id}/variants"
)
def cj_product_variants(
    store_id: int,
    product_id: str,
    country_code: str | None = Query(default=None, min_length=2, max_length=2),
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return {
            "provider": "cj",
            "items": list_cj_variants(
                db,
                membership.organization_id,
                store_id,
                product_id,
                country_code=country_code,
            ),
        }
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        CJError,
        ValueError,
    ) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _map_error(exc)


@router.get("/api/stores/{store_id}/suppliers/cj/variants/{variant_id}/stock")
def cj_variant_stock(
    store_id: int,
    variant_id: str,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return get_cj_stock(
            db,
            membership.organization_id,
            store_id,
            variant_id,
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        CJError,
    ) as exc:
        _map_error(exc)


@router.post("/api/stores/{store_id}/suppliers/cj/freight/quote")
def cj_freight_quote(
    store_id: int,
    payload: CJFreightQuoteRequest,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return quote_cj_freight(
            db,
            membership.organization_id,
            store_id,
            start_country_code=payload.start_country_code,
            end_country_code=payload.end_country_code,
            zip_code=payload.zip_code,
            items=[
                item.model_dump()
                for item in payload.items
            ],
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        CJError,
        ValueError,
    ) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _map_error(exc)


@router.post("/api/stores/{store_id}/suppliers/cj/orders")
def cj_create_supplier_order(
    store_id: int,
    payload: CJSupplierOrderCreateRequest,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return create_cj_supplier_order(
            db,
            membership.organization_id,
            store_id,
            order_id=payload.order_id,
            idempotency_key=payload.idempotency_key,
            items=[item.model_dump() for item in payload.items],
            shipping=payload.shipping.model_dump(),
            from_country_code=payload.from_country_code,
            logistic_name=payload.logistic_name,
            remark=payload.remark,
            is_sandbox=payload.is_sandbox,
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        SupplierOrderNotFound,
        SupplierOrderError,
        CJError,
    ) as exc:
        if isinstance(exc, SupplierOrderNotFound):
            raise HTTPException(
                status_code=404,
                detail={"code": str(exc), "message": str(exc)},
            ) from exc
        if isinstance(exc, SupplierOrderError):
            raise HTTPException(
                status_code=409,
                detail={"code": str(exc), "message": str(exc)},
            ) from exc
        _map_error(exc)


@router.post(
    "/api/stores/{store_id}/suppliers/cj/orders/{supplier_order_id}/sync"
)
def cj_sync_supplier_order(
    store_id: int,
    supplier_order_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return sync_cj_supplier_order(
            db,
            membership.organization_id,
            store_id,
            supplier_order_id,
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        SupplierOrderNotFound,
        SupplierOrderError,
        CJError,
    ) as exc:
        if isinstance(exc, SupplierOrderNotFound):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if isinstance(exc, SupplierOrderError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _map_error(exc)


@router.delete(
    "/api/stores/{store_id}/suppliers/cj/orders/{supplier_order_id}"
)
def cj_cancel_supplier_order(
    store_id: int,
    supplier_order_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return cancel_cj_supplier_order(
            db,
            membership.organization_id,
            store_id,
            supplier_order_id,
        )
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        SupplierOrderNotFound,
        SupplierOrderError,
        CJError,
    ) as exc:
        if isinstance(exc, SupplierOrderNotFound):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if isinstance(exc, SupplierOrderError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        _map_error(exc)


@router.post(
    "/api/stores/{store_id}/suppliers/cj/orders/{supplier_order_id}/tracking/sync"
)
def cj_sync_tracking(
    store_id: int,
    supplier_order_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return sync_cj_shipment(
            db,
            membership.organization_id,
            store_id,
            supplier_order_id,
        )
    except ShipmentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ShipmentTrackingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        CJError,
    ) as exc:
        _map_error(exc)


@router.get(
    "/api/stores/{store_id}/suppliers/cj/orders/{supplier_order_id}/shipment"
)
def cj_get_shipment(
    store_id: int,
    supplier_order_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return get_supplier_order_shipment(
            db,
            membership.organization_id,
            store_id,
            supplier_order_id,
        )
    except ShipmentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/stores/{store_id}/suppliers/cj/webhooks/logistics/enable"
)
def cj_enable_logistics_webhook(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return configure_cj_logistics_webhook(
            db,
            membership.organization_id,
            store_id,
        )
    except ShipmentTrackingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (
        SupplierConnectionNotFound,
        SupplierConnectionError,
        CJError,
    ) as exc:
        _map_error(exc)
