import os

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..shopify_client import (
    ShopifyAPIError,
    ShopifyAuthError,
    ShopifyGraphQLError,
    ShopifyTimeoutError,
    ShopifyUserError,
)
from .deps import require_permission
from ..services.shopify_service import (
    ShopifyConnectionError,
    ShopifyNotFoundError,
    ShopifyOAuthError,
    ShopifyProviderError,
    create_order as svc_create_order,
    create_poc as svc_create_poc,
    disconnect as svc_disconnect,
    get_order as svc_get_order,
    list_orders as svc_list_orders,
    process_oauth_callback as svc_process_oauth_callback,
    start_oauth as svc_start_oauth,
    sync_products as svc_sync_products,
    test_connection as svc_test_connection,
)

router = APIRouter()


# --- DTOs ---


class ShopifyConnectRequest(BaseModel):
    shop_domain: str


class ShopifyOrderItemRequest(BaseModel):
    variant_local_id: int
    quantity: int


class ShopifyOrderCreateRequest(BaseModel):
    items: list[ShopifyOrderItemRequest]
    customer_email: str | None = None
    customer_name: str | None = None
    note: str | None = None
    idempotency_key: str | None = None


class ShopifyPocShippingAddress(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    address1: str = Field(min_length=1, max_length=255)
    address2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    province_code: str | None = Field(default=None, max_length=10)
    country_code: str = Field(min_length=2, max_length=2)
    zip: str = Field(min_length=1, max_length=30)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.isalpha():
            raise ValueError("country_code must be ISO-3166 alpha-2")
        return value


class ShopifyPocOrderRequest(BaseModel):
    variant_id: str = Field(min_length=1, max_length=255)
    quantity: int = Field(ge=1, le=1000)
    customer_email: str = Field(min_length=3, max_length=255)
    customer_phone: str | None = Field(default=None, max_length=50)
    shipping_address: ShopifyPocShippingAddress
    tags: list[str] = Field(default_factory=list, max_length=20)
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=100)

    @field_validator("customer_email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("customer_email must be a valid email")
        return value


# --- Error mapping ---


def _map_oauth_error(exc: Exception):
    if isinstance(exc, ShopifyNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ShopifyOAuthError):
        code = str(exc)
        detail_map = {
            "Invalid Shopify HMAC": (403, "Invalid Shopify HMAC"),
            "Missing required Shopify OAuth parameters": (400, "Missing required Shopify OAuth parameters"),
            "Invalid or already used OAuth state": (400, "Invalid or already used OAuth state"),
            "OAuth state expired": (400, "OAuth state expired"),
            "Invalid shop domain": (400, "Invalid shop domain"),
            "OAuth state does not match the shop domain": (400, "OAuth state does not match the shop domain"),
            "INVALID_SHOPIFY_DOMAIN": (400, {"code": "INVALID_SHOPIFY_DOMAIN", "message": "Dominio Shopify inválido."}),
        }
        status, detail = detail_map.get(code, (400, code))
        raise HTTPException(status_code=status, detail=detail)
    if isinstance(exc, ShopifyConnectionError):
        code = str(exc)
        if code == "COMMERCE_ALREADY_CONNECTED":
            raise HTTPException(status_code=409, detail={"code": code, "message": "Esta tienda ya tiene una integración de comercio."})
        if code == "SHOPIFY_STORE_ALREADY_CONNECTED":
            raise HTTPException(status_code=409, detail={"code": code, "message": "Esta tienda Shopify ya está conectada a DIAGLOB."})
        if code == "SHOPIFY_NOT_CONFIGURED":
            raise HTTPException(status_code=503, detail={"code": code, "message": str(exc)})
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ShopifyProviderError):
        raise HTTPException(status_code=502, detail=str(exc))
    raise exc


# --- Endpoints ---


@router.post("/api/stores/{store_id}/shopify/connect")
def start_shopify_connection(
    store_id: int,
    payload: ShopifyConnectRequest,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_start_oauth(
            db, membership.organization_id, store_id, membership.user_id, payload.shop_domain
        )
    except (ShopifyNotFoundError, ShopifyConnectionError, ShopifyOAuthError) as exc:
        _map_oauth_error(exc)


@router.get("/api/shopify/callback")
def shopify_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    query_params = dict(request.query_params)

    try:
        redirect_url = svc_process_oauth_callback(db, query_params)
    except (ShopifyOAuthError, ShopifyProviderError) as exc:
        _map_oauth_error(exc)

    return RedirectResponse(redirect_url)


@router.delete("/api/stores/{store_id}/shopify/disconnect")
def disconnect_shopify(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_disconnect(db, membership.organization_id, store_id)
    except ShopifyNotFoundError as exc:
        _map_oauth_error(exc)


@router.post("/api/stores/{store_id}/shopify/test")
def shopify_test_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_test_connection(db, membership.organization_id, store_id)
    except ShopifyNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "SHOPIFY_NOT_CONNECTED", "message": "Shopify no está conectado."})
    except ShopifyAuthError as exc:
        raise HTTPException(status_code=401, detail={"connected": False, "error": str(exc)})
    except (ShopifyAPIError, ShopifyGraphQLError) as exc:
        raise HTTPException(status_code=502, detail={"connected": False, "error": str(exc)})


@router.post("/api/stores/{store_id}/shopify/sync/products")
def shopify_sync_products(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_sync_products(db, membership.organization_id, store_id)
    except ShopifyNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "SHOPIFY_NOT_CONNECTED", "message": "Shopify no está conectado."})
    except ShopifyAuthError as exc:
        raise HTTPException(status_code=401, detail={"ok": False, "error": str(exc)})
    except (ShopifyAPIError, ShopifyGraphQLError) as exc:
        raise HTTPException(status_code=502, detail={"ok": False, "error": str(exc)})


@router.post("/api/stores/{store_id}/shopify/poc/order")
def create_shopify_poc_order(
    store_id: int,
    payload: ShopifyPocOrderRequest,
    membership: OrganizationMembership = Depends(require_permission("commerce.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_create_poc(
            db=db,
            organization_id=membership.organization_id,
            store_id=store_id,
            variant_id=payload.variant_id,
            quantity=payload.quantity,
            customer_email=payload.customer_email,
            customer_phone=payload.customer_phone,
            shipping_address=payload.shipping_address.model_dump(),
            tags=payload.tags,
            note=payload.note,
            idempotency_key=payload.idempotency_key,
        )
    except ShopifyNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "SHOPIFY_NOT_CONNECTED", "message": "Shopify no está conectado."})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ShopifyAuthError as exc:
        raise HTTPException(status_code=401, detail={"success": False, "error": str(exc)})
    except ShopifyUserError as exc:
        raise HTTPException(status_code=422, detail={"success": False, "error": str(exc)})
    except ShopifyTimeoutError as exc:
        raise HTTPException(status_code=504, detail={"success": False, "error": str(exc)})
    except (ShopifyAPIError, ShopifyGraphQLError) as exc:
        raise HTTPException(status_code=502, detail={"success": False, "error": str(exc)})


@router.post("/api/stores/{store_id}/shopify/orders")
def create_shopify_order(
    store_id: int,
    payload: ShopifyOrderCreateRequest,
    membership: OrganizationMembership = Depends(require_permission("commerce.write")),
    db: Session = Depends(get_db),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    for item in payload.items:
        if item.quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"Quantity must be > 0 for variant {item.variant_local_id}",
            )

    try:
        return svc_create_order(
            db=db,
            organization_id=membership.organization_id,
            store_id=store_id,
            items_payload=[
                {"variant_local_id": item.variant_local_id, "quantity": item.quantity}
                for item in payload.items
            ],
            customer_email=payload.customer_email,
            customer_name=payload.customer_name,
            note=payload.note,
            idempotency_key=payload.idempotency_key,
        )
    except ShopifyNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "SHOPIFY_NOT_CONNECTED", "message": "Shopify no está conectado."})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ShopifyAuthError as exc:
        raise HTTPException(status_code=401, detail={"ok": False, "error": str(exc)})
    except ShopifyUserError as exc:
        raise HTTPException(status_code=422, detail={"ok": False, "error": str(exc)})
    except (ShopifyAPIError, ShopifyGraphQLError) as exc:
        raise HTTPException(status_code=502, detail={"ok": False, "error": str(exc)})


@router.get("/api/stores/{store_id}/shopify/orders")
def list_orders(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("commerce.read")),
    db: Session = Depends(get_db),
):
    try:
        orders = svc_list_orders(db, membership.organization_id, store_id)
    except ShopifyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {"items": orders, "total": len(orders)}


@router.get("/api/stores/{store_id}/shopify/orders/{order_id}")
def get_order(
    store_id: int,
    order_id: int,
    membership: OrganizationMembership = Depends(require_permission("commerce.read")),
    db: Session = Depends(get_db),
):
    try:
        order = svc_get_order(db, membership.organization_id, store_id, order_id)
    except ShopifyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order
