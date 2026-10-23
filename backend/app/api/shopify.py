import json
import logging
import os

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Query,
)
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership, Store
from ..shopify_client import (
    ShopifyAPIError,
    ShopifyAuthError,
    ShopifyGraphQLError,
    ShopifyProtectedCustomerDataError,
    ShopifyScopeDeniedError,
    ShopifyTimeoutError,
    ShopifyUserError,
)
from .deps import require_permission
from .store_access import require_authorized_path_store
from ..services.auto_fulfillment import (
    enqueue_shopify_order,
    process_auto_fulfillment_job_background,
)
from ..services.attributed_order_service import (
    create_attributed_shopify_order as svc_create_order,
)
from ..services.shopify_service import (
    ShopifyConnectionError,
    ShopifyNotFoundError,
    ShopifyOAuthError,
    ShopifyProviderError,
    create_poc as svc_create_poc,
    disconnect as svc_disconnect,
    ensure_order_webhooks as svc_ensure_order_webhooks,
    get_order as svc_get_order,
    list_orders as svc_list_orders,
    process_oauth_callback as svc_process_oauth_callback,
    start_reauthorization as svc_start_reauthorization,
    sync_products as svc_sync_products,
    test_connection as svc_test_connection,
)
from ..services.shopify_webhook_service import (
    SUPPORTED_TOPICS,
    ShopifyWebhookError,
    process_shopify_order_webhook,
    resolve_shopify_connection,
    verify_shopify_webhook_hmac,
)
from ..services.shopify_compliance_webhooks import (
    process_shopify_compliance_webhook,
)
from ..services.shopify_privacy_processing import ShopifyPrivacyProcessingError
from ..services.shopify_uninstall import (
    ShopifyUninstallError,
    process_shopify_uninstall,
)
from ..services import shopify_public_install
from ..services.shopify_oauth_callback_validation import (
    MAX_CALLBACK_QUERY_BYTES,
    ShopifyCallbackQueryError,
    canonicalize_oauth_callback,
)

# Compliance payloads contain minimal customer/order selectors. The bounded
# streaming read protects memory and rejects unexpectedly large signed payloads.
MAX_COMPLIANCE_BODY_BYTES = 256 * 1024

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
        if code in {"TRIAL_STORE_ALREADY_USED", "TRIAL_NOT_AVAILABLE"}:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": code,
                    "message": (
                        "Esta tienda ya utilizó una prueba gratuita de DIAGLOB. "
                        "Puedes conectarla con un plan de pago."
                    ),
                },
            )
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ShopifyProviderError):
        raise HTTPException(status_code=502, detail=str(exc))
    raise exc


# --- Endpoints ---


@router.get("/api/shopify/install")
def shopify_install_handoff(
    shop: str = Query(..., min_length=1, max_length=255),
    db: Session = Depends(get_db),
):
    """Shopify-owned install must perform OAuth before any DIAGLOB UI.

    When the independently verified public-install rollout is OFF, fail
    closed instead of sending merchants to a DIAGLOB-domain handoff page.
    This endpoint never treats a URL-provided shop as an authorized tenant.
    Shopify managed installations and token exchange require separate live
    Partner version verification before enabling this legacy-code grant.
    """
    # Reject malformed shop domains even while public installation is off.
    try:
        shop = shopify_public_install._canonical_public_shop(shop)
    except (ShopifyOAuthError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="INVALID_SHOPIFY_DOMAIN") from exc

    if not shopify_public_install.enabled():
        raise HTTPException(
            status_code=503,
            detail="SHOPIFY_PUBLIC_INSTALL_NOT_ENABLED",
            headers={"Cache-Control": "no-store"},
        )
    try:
        url = shopify_public_install.begin_public_install(db, shop)
    except (ShopifyOAuthError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="SHOPIFY_NOT_CONFIGURED") from exc
    return RedirectResponse(url, status_code=303, headers={"Cache-Control": "no-store"})


@router.get("/api/shopify/install/pending")
def shopify_pending_install(
    claim_secret: str | None = Cookie(None, alias=shopify_public_install.COOKIE_NAME),
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    """Reveal only the pending authenticated shop domain to an authorized user."""
    return shopify_public_install.pending_install_status(db, claim_secret)


class ShopifyManagedClaimCode(BaseModel):
    claim_code: str = Field(min_length=40, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/api/shopify/install/managed/pending")
def managed_install_pending(
    payload: ShopifyManagedClaimCode,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
) -> dict:
    """Validate one-use Shopify grant without revealing credentials or tenants."""
    grant = shopify_public_install._pending_for_cookie(db, payload.claim_code)
    if grant is None or grant.grant_method != "managed":
        return {"pending": False, "shop_domain": None}
    return {"pending": True, "shop_domain": grant.shop_domain}


@router.post(
    "/api/stores/{store_id}/shopify/install/claim-code",
    dependencies=[Depends(require_authorized_path_store)],
)
def managed_install_claim_code(
    store_id: int,
    payload: ShopifyManagedClaimCode,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
    store: Store = Depends(require_authorized_path_store),
) -> dict:
    grant = shopify_public_install._pending_for_cookie(db, payload.claim_code)
    if grant is None or grant.grant_method != "managed":
        raise HTTPException(status_code=404, detail="Shopify managed grant expired")
    try:
        return shopify_public_install.claim_install(
            db, secret=payload.claim_code, membership=membership, store=store,
        )
    except (ShopifyOAuthError, ShopifyConnectionError) as exc:
        _map_oauth_error(exc)


@router.post(
    "/api/stores/{store_id}/shopify/install/claim",
    dependencies=[Depends(require_authorized_path_store)],
)
def shopify_claim_install(
    store_id: int,
    claim_secret: str | None = Cookie(None, alias=shopify_public_install.COOKIE_NAME),
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
    store: Store = Depends(require_authorized_path_store),
):
    try:
        result = shopify_public_install.claim_install(
            db, secret=claim_secret, membership=membership, store=store
        )
    except (ShopifyOAuthError, ShopifyConnectionError) as exc:
        _map_oauth_error(exc)
    response = JSONResponse(result, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        shopify_public_install.COOKIE_NAME,
        path="/", domain="diaglob.tech", secure=True, httponly=True, samesite="lax",
    )
    return response


@router.post("/api/stores/{store_id}/shopify/connect", dependencies=[Depends(require_authorized_path_store)])
def start_shopify_connection(
    store_id: int,
    payload: ShopifyConnectRequest,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    # Public App Store installs must originate in Shopify Admin and use
    # a signed managed-install grant. Legacy DIAGLOB-origin manual-domain
    # OAuth is intentionally retired; never create OAuth state from this body.
    # Keep the route for a safe, actionable response to older clients.
    raise HTTPException(
        status_code=410,
        detail={
            "code": "SHOPIFY_MANAGED_INSTALL_REQUIRED",
            "message": (
                "Abre DIAGLOB desde Shopify Admin, genera un código de instalación "
                "y vincula la tienda desde /shopify/install?managed=1."
            ),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/stores/{store_id}/shopify/reauthorize", dependencies=[Depends(require_authorized_path_store)])
def reauthorize_shopify(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return svc_start_reauthorization(
            db,
            membership.organization_id,
            store_id,
            membership.user_id,
        )
    except (
        ShopifyNotFoundError,
        ShopifyConnectionError,
        ShopifyOAuthError,
    ) as exc:
        _map_oauth_error(exc)


@router.get("/api/shopify/callback")
def shopify_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    # Reject oversized raw queries BEFORE parsing multi-value parameters.
    raw_query_size = len(request.scope.get("query_string", b""))
    if raw_query_size > MAX_CALLBACK_QUERY_BYTES:
        raise HTTPException(status_code=400, detail="INVALID_SHOPIFY_CALLBACK_QUERY")

    # Never flatten duplicate query parameters: Starlette's dict conversion
    # discards them before signature verification and OAuth state validation.
    try:
        query_params = canonicalize_oauth_callback(
            list(request.query_params.multi_items()),
            raw_query_bytes=raw_query_size,
        )
    except ShopifyCallbackQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # The one-use unbound state is never interpreted as an organization grant.
    if shopify_public_install.pending_state_exists(db, query_params.get("state", "")):
        try:
            cookie_secret = shopify_public_install.finish_public_install(db, query_params)
            redirect_url = shopify_public_install._frontend_install_url()
        except (ShopifyOAuthError, ShopifyProviderError) as exc:
            _map_oauth_error(exc)
        response = RedirectResponse(
            redirect_url, status_code=303, headers={"Cache-Control": "no-store"}
        )
        response.set_cookie(
            shopify_public_install.COOKIE_NAME,
            cookie_secret, max_age=1200, path="/", domain="diaglob.tech",
            secure=True, httponly=True, samesite="lax",
        )
        return response

    try:
        redirect_url = svc_process_oauth_callback(db, query_params)
    except (ShopifyOAuthError, ShopifyProviderError, ShopifyConnectionError) as exc:
        _map_oauth_error(exc)
    return RedirectResponse(redirect_url)


@router.delete("/api/stores/{store_id}/shopify/disconnect", dependencies=[Depends(require_authorized_path_store)])
def disconnect_shopify(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_disconnect(db, membership.organization_id, store_id)
    except ShopifyNotFoundError as exc:
        _map_oauth_error(exc)


@router.post("/api/stores/{store_id}/shopify/webhooks/ensure", dependencies=[Depends(require_authorized_path_store)])
def shopify_ensure_order_webhooks(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("stores.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return svc_ensure_order_webhooks(
            db,
            membership.organization_id,
            store_id,
        )
    except ShopifyNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "SHOPIFY_NOT_CONNECTED",
                "message": str(exc),
            },
        ) from exc
    except ShopifyAuthError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "SHOPIFY_AUTH_FAILED",
                "message": str(exc),
            },
        ) from exc
    except (ShopifyProtectedCustomerDataError, ShopifyScopeDeniedError) as exc:
        # Access errors are merchant-actionable and must not leak provider PII.
        raise HTTPException(
            status_code=403,
            detail={
                "code": str(exc),
                "error": str(exc),
                "message": "Shopify permission or protected data approval required.",
            },
        ) from exc
    except (
        ShopifyAPIError,
        ShopifyGraphQLError,
        ShopifyUserError,
    ) as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "SHOPIFY_WEBHOOK_SETUP_FAILED",
                "message": str(exc),
            },
        ) from exc


@router.post("/api/stores/{store_id}/shopify/test", dependencies=[Depends(require_authorized_path_store)])
def shopify_test_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_test_connection(db, membership.organization_id, store_id)
    except ShopifyNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "SHOPIFY_NOT_CONNECTED", "message": "Shopify no está conectado a esta tienda."},
        ) from exc
    except ShopifyAuthError as exc:
        # An active embedded Shopify session does not prove that the saved
        # backend offline token is valid. Reacquire it via Shopify-managed
        # installation, NEVER by accepting a token in the browser.
        code = (
            "SHOPIFY_SHOP_IDENTITY_MISMATCH"
            if str(exc) == "SHOPIFY_SHOP_IDENTITY_MISMATCH"
            else "SHOPIFY_REAUTH_REQUIRED"
        )
        message = (
            "Shopify devolvió una tienda distinta de la autorizada. Contacta soporte de DIAGLOB."
            if code == "SHOPIFY_SHOP_IDENTITY_MISMATCH"
            else "La credencial guardada de Shopify requiere reautorización. Abre DIAGLOB desde Shopify Admin para recuperar la conexión con tu tienda existente. No la desconectes ni crees otra tienda."
        )
        raise HTTPException(
            status_code=401,
            detail={"connected": False, "code": code, "message": message},
        ) from exc
    except (ShopifyProtectedCustomerDataError, ShopifyScopeDeniedError) as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "code": str(exc),
                "connected": False,
                "message": "Shopify permission or protected data approval required.",
            },
        ) from exc
    except (ShopifyAPIError, ShopifyGraphQLError) as exc:
        # A transport/GraphQL error is not evidence that the merchant's
        # installation is revoked. Don't expose provider response details.
        raise HTTPException(
            status_code=502,
            detail={
                "connected": False,
                "code": "SHOPIFY_CONNECTION_CHECK_FAILED",
                "message": "No se pudo consultar Shopify. Reintenta más tarde; si persiste, revisa los registros del servidor.",
            },
        ) from exc


@router.post("/api/stores/{store_id}/shopify/sync/products", dependencies=[Depends(require_authorized_path_store)])
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
        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "code": "SHOPIFY_REAUTH_REQUIRED",
                "message": "La credencial Shopify requiere reautorización desde Shopify Admin.",
            },
        ) from exc
    except (ShopifyProtectedCustomerDataError, ShopifyScopeDeniedError) as exc:
        # Access errors are merchant-actionable and must not leak provider PII.
        raise HTTPException(
            status_code=403,
            detail={
                "code": str(exc),
                "error": str(exc),
                "message": "Shopify permission or protected data approval required.",
            },
        ) from exc
    except (ShopifyAPIError, ShopifyGraphQLError) as exc:
        raise HTTPException(status_code=502, detail={"ok": False, "error": str(exc)})


@router.post("/api/stores/{store_id}/shopify/poc/order", dependencies=[Depends(require_authorized_path_store)])
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
    except (ShopifyProtectedCustomerDataError, ShopifyScopeDeniedError) as exc:
        # Access errors are merchant-actionable and must not leak provider PII.
        raise HTTPException(
            status_code=403,
            detail={
                "code": str(exc),
                "error": str(exc),
                "message": "Shopify permission or protected data approval required.",
            },
        ) from exc
    except (ShopifyAPIError, ShopifyGraphQLError) as exc:
        raise HTTPException(status_code=502, detail={"success": False, "error": str(exc)})


@router.post("/api/stores/{store_id}/shopify/orders", dependencies=[Depends(require_authorized_path_store)])
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
            actor_type="human",
            human_user_id=membership.user_id,
        )
    except ShopifyNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"code": "SHOPIFY_NOT_CONNECTED", "message": "Shopify no está conectado."})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ShopifyAuthError as exc:
        raise HTTPException(status_code=401, detail={"ok": False, "error": str(exc)})
    except ShopifyUserError as exc:
        raise HTTPException(status_code=422, detail={"ok": False, "error": str(exc)})
    except (ShopifyProtectedCustomerDataError, ShopifyScopeDeniedError) as exc:
        # Access errors are merchant-actionable and must not leak provider PII.
        raise HTTPException(
            status_code=403,
            detail={
                "code": str(exc),
                "error": str(exc),
                "message": "Shopify permission or protected data approval required.",
            },
        ) from exc
    except (ShopifyAPIError, ShopifyGraphQLError) as exc:
        raise HTTPException(status_code=502, detail={"ok": False, "error": str(exc)})


@router.get("/api/stores/{store_id}/shopify/orders", dependencies=[Depends(require_authorized_path_store)])
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


@router.get("/api/stores/{store_id}/shopify/orders/{order_id}", dependencies=[Depends(require_authorized_path_store)])
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

# --- Shopify order webhooks ---


@router.post("/api/webhooks/shopify")
async def shopify_order_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Receive authenticated Shopify order lifecycle webhooks."""

    raw_body = await request.body()
    hmac_header = request.headers.get(
        "x-shopify-hmac-sha256"
    )

    if not verify_shopify_webhook_hmac(
        raw_body,
        hmac_header,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid Shopify webhook signature",
        )

    topic = (
        request.headers.get("x-shopify-topic", "")
        .strip()
        .lower()
    )
    shop_domain = (
        request.headers.get(
            "x-shopify-shop-domain",
            "",
        )
        .strip()
        .lower()
    )

    if not topic or not shop_domain:
        raise HTTPException(
            status_code=400,
            detail="Missing Shopify webhook headers",
        )

    if topic not in SUPPORTED_TOPICS:
        return {
            "ok": True,
            "action": "ignored",
            "topic": topic,
        }

    connection = resolve_shopify_connection(
        db,
        shop_domain,
    )
    if connection is None:
        # Authenticated webhook from a shop that is no longer connected.
        # Acknowledge it so Shopify does not keep retrying obsolete delivery.
        return {
            "ok": True,
            "action": "ignored",
            "topic": topic,
        }

    try:
        payload = json.loads(
            raw_body.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload",
        ) from exc

    try:
        result = process_shopify_order_webhook(
            db,
            connection=connection,
            topic=topic,
            payload=payload,
        )
        order_id = result.get("order_id")
        if order_id:
            job = enqueue_shopify_order(db, int(order_id))
            if job is not None:
                result["auto_fulfillment_job_id"] = job.id
                background_tasks.add_task(
                    process_auto_fulfillment_job_background,
                    job.id,
                )
        return result
    except ShopifyWebhookError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503 if str(exc) == "PRIVACY_SUPPRESSION_CHECK_UNAVAILABLE" else 400,
            detail={
                "code": str(exc),
                "message": str(exc)
                .replace("_", " ")
                .title(),
            },
        ) from exc
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception(
            "Shopify webhook processing failed "
            "for topic=%s shop=%s",
            topic,
            shop_domain,
        )
        # Non-2XX responses make Shopify retry transient failures.
        raise HTTPException(
            status_code=500,
            detail="Shopify webhook processing failed",
        )


@router.post("/api/webhooks/shopify/uninstalled")
async def shopify_app_uninstalled_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Revoke exactly one verified installation; preserve privacy receipts."""
    chunks = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > MAX_COMPLIANCE_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Shopify webhook payload too large")
        chunks.append(chunk)
    raw_body = b"".join(chunks)
    if not verify_shopify_webhook_hmac(
        raw_body, request.headers.get("x-shopify-hmac-sha256")
    ):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature")

    if request.headers.get("x-shopify-topic", "").strip().lower() != "app/uninstalled":
        raise HTTPException(status_code=400, detail="Unsupported Shopify lifecycle topic")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc
    try:
        return process_shopify_uninstall(
            db,
            topic="app/uninstalled",
            header_shop_domain=request.headers.get("x-shopify-shop-domain"),
            triggered_at=request.headers.get("x-shopify-triggered-at"),
            payload=payload,
        )
    except ShopifyUninstallError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logging.getLogger(__name__).exception("Shopify uninstall webhook failed")
        raise HTTPException(status_code=500, detail="Shopify uninstall failed") from exc


@router.post("/api/webhooks/shopify/compliance")
async def shopify_compliance_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Acknowledge and process Shopify App Store privacy webhooks."""
    # Read the request incrementally: a forged Content-Length must never
    # allow an unbounded body allocation before HMAC verification.
    chunks = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > MAX_COMPLIANCE_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Shopify compliance payload too large")
        chunks.append(chunk)
    raw_body = b"".join(chunks)
    if not verify_shopify_webhook_hmac(
        raw_body,
        request.headers.get("x-shopify-hmac-sha256"),
    ):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature")

    topic = request.headers.get("x-shopify-topic", "").strip().lower()
    if topic not in {"customers/data_request", "customers/redact", "shop/redact"}:
        raise HTTPException(status_code=400, detail="Unsupported Shopify compliance topic")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    try:
        return process_shopify_compliance_webhook(
            db,
            topic=topic,
            payload=payload,
            webhook_id=request.headers.get("x-shopify-webhook-id"),
            header_shop_domain=request.headers.get("x-shopify-shop-domain"),
        )
    except ShopifyPrivacyProcessingError as exc:
        # A broken receipt or review queue is an internal integrity fault:
        # return 5xx so Shopify can retry, never mislabel it a bad payload.
        db.rollback()
        logging.getLogger(__name__).error(
            "Shopify privacy intake integrity failure code=%s", type(exc).__name__,
        )
        raise HTTPException(
            status_code=500, detail="Shopify compliance webhook processing failed",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logging.getLogger(__name__).exception(
            "Shopify compliance webhook processing failed for topic=%s", topic
        )
        raise HTTPException(status_code=500, detail="Shopify compliance webhook processing failed") from exc

