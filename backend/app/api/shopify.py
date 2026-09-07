import os
from datetime import datetime, timedelta

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
from ..models import (
    CommerceConnection,
    OrganizationMembership,
    ShopifyOAuthState,
    Store,
)
from ..shopify_oauth import (
    SHOPIFY_SCOPES,
    build_authorization_url,
    exchange_access_token,
    generate_oauth_state,
    normalize_shop_domain,
    verify_shopify_hmac,
)
from ..shopify_security import encrypt_shopify_secret
from ..shopify_sync import (
    sync_shopify_products,
    test_shopify_connection,
)
from ..shopify_orders import (
    create_shopify_draft_order,
    get_shopify_order,
    list_shopify_orders,
)
from ..shopify_poc import create_poc_order
from ..shopify_client import (
    ShopifyAPIError,
    ShopifyAuthError,
    ShopifyGraphQLError,
    ShopifyTimeoutError,
    ShopifyUserError,
)
from .deps import require_permission

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


# --- Helper ---


def _shopify_connect_frontend_url(
    connected: bool,
) -> str:
    base_url = os.getenv(
        "FRONTEND_URL",
        "https://diaglob.tech",
    ).strip().rstrip("/")

    status = (
        "connected"
        if connected
        else "already-connected"
    )

    return (
        f"{base_url}"
        f"?shopify={status}"
    )


# --- Endpoints ---


@router.post("/api/stores/{store_id}/shopify/connect")
def start_shopify_connection(
    store_id: int,
    payload: ShopifyConnectRequest,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.write"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    if not store.active:
        raise HTTPException(
            status_code=409,
            detail=(
                "La tienda debe estar activa "
                "para conectar Shopify."
            ),
        )

    existing_connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
        )
        .first()
    )

    if existing_connection:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "COMMERCE_ALREADY_CONNECTED",

                "message":
                    (
                        "Esta tienda ya tiene una "
                        "integración de comercio."
                    ),

                "provider":
                    existing_connection.provider,
            },
        )

    try:
        shop_domain = (
            normalize_shop_domain(
                payload.shop_domain
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "INVALID_SHOPIFY_DOMAIN",

                "message":
                    "Dominio Shopify inválido.",
            },
        ) from exc

    conflicting_connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider
            == "shopify",
            CommerceConnection.external_store_url
            == shop_domain,
        )
        .first()
    )

    if conflicting_connection:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "SHOPIFY_STORE_ALREADY_CONNECTED",

                "message":
                    (
                        "Esta tienda Shopify ya "
                        "está conectada a DIAGLOB."
                    ),
            },
        )

    state = generate_oauth_state()

    now = datetime.utcnow()

    oauth_state = ShopifyOAuthState(
        state=state,

        organization_id=
            membership.organization_id,

        store_id=
            store.id,

        user_id=
            membership.user_id,

        shop_domain=
            shop_domain,

        expires_at=
            now + timedelta(
                minutes=10
            ),

        used=False,

        created_at=now,
    )

    db.add(oauth_state)

    # Limpiamos estados antiguos del mismo
    # usuario/tienda para evitar acumulación.
    (
        db.query(ShopifyOAuthState)
        .filter(
            ShopifyOAuthState.store_id
            == store.id,

            ShopifyOAuthState.user_id
            == membership.user_id,

            ShopifyOAuthState.state
            != state,

            ShopifyOAuthState.used
            .is_(False),
        )
        .update(
            {
                ShopifyOAuthState.used:
                    True,
            },
            synchronize_session=False,
        )
    )

    try:
        authorization_url = (
            build_authorization_url(
                shop_domain,
                state,
            )
        )

    except RuntimeError as exc:
        db.rollback()

        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "SHOPIFY_NOT_CONFIGURED",

                "message":
                    str(exc),
            },
        ) from exc

    db.commit()

    return {
        "ok": True,
        "provider": "shopify",
        "store_id": store.id,
        "shop_domain": shop_domain,
        "expires_in_seconds": 600,
        "authorization_url":
            authorization_url,
    }


@router.get("/api/shopify/callback")
def shopify_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    query_params = dict(
        request.query_params
    )

    if not verify_shopify_hmac(
        query_params
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid Shopify HMAC",
        )

    code = query_params.get(
        "code",
        "",
    )

    state = query_params.get(
        "state",
        "",
    )

    shop = query_params.get(
        "shop",
        "",
    )

    if not (code and state and shop):
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing required Shopify "
                "OAuth parameters"
            ),
        )

    oauth_state = (
        db.query(ShopifyOAuthState)
        .filter(
            ShopifyOAuthState.state
            == state,
            ShopifyOAuthState.used
            .is_(False),
        )
        .first()
    )

    if not oauth_state:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid or already used "
                "OAuth state"
            ),
        )

    if (
        oauth_state.expires_at
        < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=400,
            detail="OAuth state expired",
        )

    try:
        normalized_shop = (
            normalize_shop_domain(
                shop
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid shop domain",
        ) from exc

    if (
        oauth_state.shop_domain
        != normalized_shop
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "OAuth state does not match "
                "the shop domain"
            ),
        )

    try:
        access_token = (
            exchange_access_token(
                normalized_shop,
                code,
            )
        )

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    encrypted_token = (
        encrypt_shopify_secret(
            access_token
        )
    )

    existing_connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == oauth_state.store_id,
        )
        .first()
    )

    if existing_connection:
        (
            db.query(ShopifyOAuthState)
            .filter(
                ShopifyOAuthState.id
                == oauth_state.id,
            )
            .update(
                {
                    ShopifyOAuthState.used:
                        True,
                },
                synchronize_session=False,
            )
        )

        db.commit()

        return RedirectResponse(
            _shopify_connect_frontend_url(
                connected=False
            )
        )

    now = datetime.utcnow()

    connection = CommerceConnection(
        organization_id=
            oauth_state.organization_id,

        store_id=
            oauth_state.store_id,

        provider="shopify",

        external_store_url=
            normalized_shop,

        access_token_encrypted=
            encrypted_token,

        scopes=SHOPIFY_SCOPES,

        status="connected",

        connected_at=now,
    )

    db.add(connection)

    (
        db.query(ShopifyOAuthState)
        .filter(
            ShopifyOAuthState.id
            == oauth_state.id,
        )
        .update(
            {
                ShopifyOAuthState.used:
                    True,
            },
            synchronize_session=False,
        )
    )

    db.commit()

    return RedirectResponse(
        _shopify_connect_frontend_url(
            connected=True
        )
    )


@router.delete("/api/stores/{store_id}/shopify/disconnect")
def disconnect_shopify(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.write"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
            CommerceConnection.provider
            == "shopify",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "SHOPIFY_NOT_CONNECTED",

                "message":
                    (
                        "Esta tienda no tiene "
                        "Shopify conectado."
                    ),
            },
        )

    db.delete(connection)
    db.commit()

    return {
        "ok": True,
        "connected": False,
        "store_id": store.id,
    }


@router.post(
    "/api/stores/{store_id}"
    "/shopify/test"
)
def shopify_test_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.write"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
            CommerceConnection.provider
            == "shopify",
            CommerceConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "SHOPIFY_NOT_CONNECTED",
                "message":
                    (
                        "Shopify no está "
                        "conectado."
                    ),
            },
        )

    try:
        result = (
            test_shopify_connection(
                connection
            )
        )

    except ShopifyAuthError as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=401,
            detail={
                "connected": False,
                "error": str(exc),
            },
        ) from exc

    except (
        ShopifyAPIError,
        ShopifyGraphQLError,
    ) as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "connected": False,
                "error": str(exc),
            },
        ) from exc

    connection.status = "connected"
    connection.last_error = None
    db.commit()

    return result


@router.post(
    "/api/stores/{store_id}"
    "/shopify/sync/products"
)
def shopify_sync_products(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.write"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
            CommerceConnection.provider
            == "shopify",
            CommerceConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "SHOPIFY_NOT_CONNECTED",
                "message":
                    (
                        "Shopify no está "
                        "conectado."
                    ),
            },
        )

    try:
        result = sync_shopify_products(
            db, connection
        )

    except ShopifyAuthError as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    except (
        ShopifyAPIError,
        ShopifyGraphQLError,
    ) as exc:
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    return result


@router.post("/api/stores/{store_id}/shopify/poc/order")
def create_shopify_poc_order(
    store_id: int,
    payload: ShopifyPocOrderRequest,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
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

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id == store.id,
            CommerceConnection.organization_id == membership.organization_id,
            CommerceConnection.provider == "shopify",
            CommerceConnection.status == "connected",
        )
        .first()
    )
    if not connection:
        raise HTTPException(
            status_code=404,
            detail={"code": "SHOPIFY_NOT_CONNECTED", "message": "Shopify no está conectado."},
        )

    try:
        return create_poc_order(
            db=db,
            store=store,
            connection=connection,
            variant_id=payload.variant_id,
            quantity=payload.quantity,
            customer_email=payload.customer_email,
            customer_phone=payload.customer_phone,
            shipping_address=payload.shipping_address.model_dump(),
            tags=payload.tags,
            note=payload.note,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ShopifyAuthError as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=401, detail={"success": False, "error": str(exc)}) from exc
    except ShopifyUserError as exc:
        raise HTTPException(status_code=422, detail={"success": False, "error": str(exc)}) from exc
    except ShopifyTimeoutError as exc:
        raise HTTPException(status_code=504, detail={"success": False, "error": str(exc)}) from exc
    except (ShopifyAPIError, ShopifyGraphQLError) as exc:
        connection.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail={"success": False, "error": str(exc)}) from exc


@router.post(
    "/api/stores/{store_id}"
    "/shopify/orders"
)
def create_shopify_order(
    store_id: int,
    payload: ShopifyOrderCreateRequest,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.write"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
            CommerceConnection.provider
            == "shopify",
            CommerceConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "SHOPIFY_NOT_CONNECTED",
                "message":
                    (
                        "Shopify no está "
                        "conectado."
                    ),
            },
        )

    if not payload.items:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one item is required"
            ),
        )

    for item in payload.items:
        if item.quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Quantity must be > 0 for "
                    f"variant "
                    f"{item.variant_local_id}"
                ),
            )

    try:
        result = create_shopify_draft_order(
            db=db,
            store=store,
            connection=connection,
            items_payload=[
                {
                    "variant_local_id":
                        item.variant_local_id,
                    "quantity": item.quantity,
                }
                for item in payload.items
            ],
            customer_email=(
                payload.customer_email
            ),
            customer_name=(
                payload.customer_name
            ),
            note=payload.note,
            idempotency_key=(
                payload.idempotency_key
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except ShopifyAuthError as exc:
        connection.status = "error"
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    except ShopifyUserError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    except (
        ShopifyAPIError,
        ShopifyGraphQLError,
    ) as exc:
        connection.last_error = str(exc)
        db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "error": str(exc),
            },
        ) from exc

    return result


@router.get(
    "/api/stores/{store_id}"
    "/shopify/orders"
)
def list_orders(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    orders = list_shopify_orders(
        db=db,
        store_id=store.id,
        organization_id=store.organization_id,
    )

    return {
        "items": orders,
        "total": len(orders),
    }


@router.get(
    "/api/stores/{store_id}"
    "/shopify/orders/{order_id}"
)
def get_order(
    store_id: int,
    order_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    order = get_shopify_order(
        db=db,
        order_id=order_id,
        store_id=store.id,
        organization_id=store.organization_id,
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    return order
