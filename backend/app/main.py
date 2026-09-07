import secrets
import json
import os
import hmac
import hashlib
import logging
import re
import time
from typing import Literal

from datetime import datetime, timedelta, timezone

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .auth import verify_cognito_access_token

from .markets import AMERICA_MARKETS, get_market
from .plan_limits import get_organization_limits
from .permissions import (
    get_permissions_for_role,
    has_permission,
)
from .db import Base, SessionLocal, engine, get_db
from .models import (
    Agent,
    Automation,
    AutomationCampaign,
    AutomationAudienceMember,
    AutomationRun,
    AutomationRecipientExecution,
    AutomationExecution,
    AutomationFlow,
    AutomationFlowVersion,
    AutomationFlowRun,
    AutomationFlowRecipientExecution,
    AutomationNodeExecution,
    CommerceConnection,
    Customer,
    CustomerStoreProfile,
    DropiConnection,
    KnowledgeBase,
    Order,
    Product,
    ProductVariant,
    Message,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    Store,
    User,
)

from .automations import (
    safe_emit_event,
)

from .dropi_security import (
    encrypt_dropi_secret,
)









Base.metadata.create_all(bind=engine)

logger = logging.getLogger(__name__)


app = FastAPI(
    title="Diaglob API",
    version="0.5.0",
    description="Backend API for Diaglob",
)


@app.on_event("startup")
def reconcile_knowledge_base_provisioning_on_startup() -> None:
    from .api.knowledge import reconcile_knowledge_base_provisioning
    reconcile_knowledge_base_provisioning()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "https://diaglob.tech",
        "https://www.diaglob.tech",
        "https://app.diaglob.tech",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# SECURITY HEADERS MIDDLEWARE
# ============================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        return response


app.add_middleware(SecurityHeadersMiddleware)


# ============================================================
# RATE LIMITING (simple in-memory)
# ============================================================

import time
from collections import defaultdict

_rate_limit_store: dict[str, list[float]] = defaultdict(list)

RATE_LIMIT_RULES = {
    "/api/auth/login": (10, 60),
    "/api/auth/register": (5, 60),
    "/api/billing/checkout": (10, 60),
    "/api/billing/upgrade": (10, 60),
    "/api/billing/upgrade/preview": (20, 60),
    "/api/billing/downgrade": (10, 60),
    "/webhooks/whatsapp": (100, 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        path = request.url.path
        client_ip = (
            request.client.host
            if request.client
            else "unknown"
        )

        rule = RATE_LIMIT_RULES.get(path)

        if rule:
            max_requests, window_seconds = rule
            key = f"{path}:{client_ip}"
            now = time.time()

            _rate_limit_store[key] = [
                t
                for t in _rate_limit_store[key]
                if now - t < window_seconds
            ]

            if len(_rate_limit_store[key]) >= max_requests:
                response = Response(
                    content='{"detail":"Rate limit exceeded"}',
                    status_code=429,
                    media_type="application/json",
                )
                origin = request.headers.get("origin", "")
                allowed_origins = [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "http://localhost:5174",
                    "http://127.0.0.1:5174",
                    "https://diaglob.tech",
                    "https://www.diaglob.tech",
                    "https://app.diaglob.tech",
                ]
                if origin in allowed_origins:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                return response

            _rate_limit_store[key].append(now)

        return await call_next(request)


app.add_middleware(RateLimitMiddleware)

# ============================================================
# API ROUTERS
# ============================================================

from .api.health import router as health_router
from .api.auth import router as auth_router
from .api.organizations import router as organizations_router
from .api.stores import router as stores_router
from .api.customers import router as customers_router
from .api.products import router as products_router
from .api.orders import router as orders_router
from .api.commerce import router as commerce_router
from .api.shopify import router as shopify_router
from .api.google import router as google_router
from .api.knowledge import router as knowledge_router
from .api.billing import router as billing_router
from .api.automations import router as automations_router
from .api.whatsapp import router as whatsapp_router
from .api.conversations import router as conversations_router
from .api.analytics import router as analytics_router

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(stores_router)
app.include_router(customers_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(commerce_router)
app.include_router(shopify_router)
app.include_router(google_router)
app.include_router(knowledge_router)
app.include_router(billing_router)
app.include_router(automations_router)
app.include_router(whatsapp_router)
app.include_router(conversations_router)
app.include_router(analytics_router)

# Re-export dependency functions from deps so that
# tests importing from app.main get the same function
# objects used by the routers.
from .api.deps import (  # noqa: F811
    get_allowed_store_ids,
    get_current_user,
    get_current_membership,
    get_current_organization,
    get_store_scope,
    require_permission,
)

# Re-export Google helpers from api/google for deferred
# endpoints still in main.py (KB/Bedrock endpoints).
from .api.google import (  # noqa: F811
    _get_valid_google_token,
    _require_drive_scope,
)

# Re-export google_security functions for backward
# compatibility (tests mock via app.main.*).
from .google_security import (  # noqa: F811
    encrypt_google_secret,
    decrypt_google_secret,
)

# Re-export google_drive_client functions for backward
# compatibility (tests mock via app.main.*).
from .google_drive_client import (  # noqa: F811
    list_drive_files,
    list_drive_folders,
)


class DropiConnectRequest(BaseModel):
    api_token: str




class AgentAskRequest(BaseModel):
    question: str
    number_of_results: int = 5


class AgentCreate(BaseModel):
    name: str
    role: str
    active: bool = True
    store_ids: list[int] = []
    knowledge_base_ids: list[int] = []


class AgentUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    active: bool | None = None
    store_ids: list[int] | None = None
    knowledge_base_ids: list[int] | None = None


bearer_scheme = HTTPBearer(
    auto_error=False,
)





def get_active_member_usage(
    db: Session,
    organization_id: int,
):
    """
    Cuenta los miembros activos de toda la organización.

    El owner también consume un cupo.
    Miembros inactivos no consumen capacidad.
    """

    return (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id
            == organization_id,
            OrganizationMembership.active.is_(True),
        )
        .count()
    )


def ensure_member_capacity(
    db: Session,
    organization_id: int,
):
    """
    Valida capacidad global de miembros
    para toda la organización.
    """

    organization = (
        db.query(Organization)
        .filter(
            Organization.id
            == organization_id
        )
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=404,
            detail="Organization not found",
        )

    limits = get_organization_limits(
        organization
    )

    active_members = (
        get_active_member_usage(
            db,
            organization_id,
        )
    )

    limit = limits.members

    if active_members >= limit:
        plan_name = (
            (organization.plan or "none")
            .strip()
            .lower()
            .capitalize()
        )

        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "MEMBER_LIMIT_REACHED",

                "message":
                    (
                        f"Tu plan {plan_name} "
                        f"permite hasta {limit} "
                        "miembros activos. "
                        f"Actualmente tienes "
                        f"{active_members}. "
                        "Desactiva un miembro o mejora "
                        "tu plan para agregar otro."
                    ),

                "resource":
                    "members",

                "used":
                    active_members,

                "limit":
                    limit,

                "remaining":
                    max(
                        limit - active_members,
                        0,
                    ),
            },
        )


def get_active_store_usage(
    db: Session,
    organization_id: int,
):
    return (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization_id,
            Store.deleted.is_(False),
            Store.active.is_(True),
        )
        .count()
    )


def ensure_active_store_capacity(
    db: Session,
    organization_id: int,
):
    organization = (
        db.query(Organization)
        .filter(
            Organization.id
            == organization_id
        )
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=404,
            detail="Organization not found",
        )

    if organization.subscription_status in {
        "past_due",
        "paused",
        "canceled",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "Tu suscripción no está activa. "
                "Actualiza tu método de pago o "
                "renueva tu plan para activar tiendas."
            ),
        )

    limits = get_organization_limits(
        organization
    )

    active_stores = (
        get_active_store_usage(
            db,
            organization_id,
        )
    )

    limit = limits.active_stores

    if active_stores >= limit:
        plan_name = (
            (organization.plan or "none")
            .strip()
            .lower()
            .capitalize()
        )

        store_word = (
            "tienda activa"
            if limit == 1
            else "tiendas activas"
        )

        current_word = (
            "tienda activa"
            if active_stores == 1
            else "tiendas activas"
        )

        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "ACTIVE_STORE_LIMIT_REACHED",

                "message":
                    (
                        f"Tu plan {plan_name} "
                        f"permite hasta {limit} "
                        f"{store_word}. "
                        f"Actualmente tienes "
                        f"{active_stores} "
                        f"{current_word}. "
                        "Suspende una tienda o mejora "
                        "tu plan para activar otra."
                    ),

                "resource":
                    "stores",

                "used":
                    active_stores,

                "limit":
                    limit,

                "remaining":
                    max(
                        limit - active_stores,
                        0,
                    ),
            },
        )


def serialize_store_short(
    store: Store,
):
    return {
        "id": store.id,
        "name": store.name,
        "country_code": store.country_code,
        "currency": store.currency,
    }


def serialize_agent(
    agent: Agent,
):
    return {
        "id": agent.id,
        "organization_id": agent.organization_id,
        "name": agent.name,
        "role": agent.role,
        "active": agent.active,
        "stores": [
            serialize_store_short(store)
            for store in agent.stores
            if store.active
        ],
        "knowledge_bases": [
            {
                "id": knowledge_base.id,
                "name": knowledge_base.name,
                "scope": knowledge_base.scope,
                "active": knowledge_base.active,
            }
            for knowledge_base in agent.knowledge_bases
        ],
    }


def serialize_team_invitation(
    invitation: OrganizationInvitation,
):
    status = invitation.status

    if (
        status == "pending"
        and invitation.expires_at
        <= datetime.utcnow()
    ):
        status = "expired"

    return {
        "id":
            invitation.id,

        "organization_id":
            invitation.organization_id,

        "email":
            invitation.email,

        "role":
            invitation.role,

        "all_stores":
            bool(
                invitation.all_stores
            ),

        "active":
            status == "pending",

        "status":
            status,

        "stores": [
            serialize_store_short(store)
            for store in invitation.stores
            if not store.deleted
        ],

        "expires_at":
            invitation.expires_at.isoformat(),

        "accepted_at":
            (
                invitation.accepted_at.isoformat()
                if invitation.accepted_at
                else None
            ),

        "created_at":
            invitation.created_at.isoformat(),
    }


def serialize_team_member(
    membership: OrganizationMembership,
):
    return {
        "id": membership.id,
        "user_id": membership.user_id,
        "name": membership.user.name,
        "email": membership.user.email,
        "role": membership.role,
        "all_stores": bool(
            membership.all_stores
        ),
        "active": bool(
            membership.active
        ),
        "stores": [
            serialize_store_short(store)
            for store in membership.stores
            if not store.deleted
        ],
        "created_at":
            membership.created_at.isoformat(),
    }


def resolve_team_member_stores(
    organization_id: int,
    store_ids: list[int],
    db: Session,
):
    requested_ids = sorted(
        set(store_ids)
    )

    if not requested_ids:
        return []

    stores = (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization_id,
            Store.id.in_(requested_ids),
            Store.deleted.is_(False),
        )
        .all()
    )

    found_ids = {
        store.id
        for store in stores
    }

    if found_ids != set(requested_ids):
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "INVALID_TEAM_STORE",

                "message":
                    (
                        "Una o más tiendas no pertenecen "
                        "a esta organización."
                    ),
            },
        )

    return stores


def resolve_member_stores(
    membership: OrganizationMembership,
    store_ids: list[int],
    db: Session,
):
    requested_ids = sorted(
        set(store_ids)
    )

    if not requested_ids:
        return []

    stores = (
        db.query(Store)
        .filter(
            Store.organization_id
            == membership.organization_id,
            Store.id.in_(requested_ids),
            Store.active.is_(True),
        )
        .all()
    )

    found_ids = {
        store.id
        for store in stores
    }

    if found_ids != set(requested_ids):
        raise HTTPException(
            status_code=400,
            detail="One or more stores are invalid",
        )

    allowed_ids = get_allowed_store_ids(
        membership
    )

    if (
        allowed_ids is not None
        and not set(requested_ids).issubset(
            set(allowed_ids)
        )
    ):
        raise HTTPException(
            status_code=403,
            detail="Store access denied",
        )

    return stores


def resolve_organization_knowledge_bases(
    organization_id: int,
    knowledge_base_ids: list[int],
    db: Session,
):
    requested_ids = sorted(
        set(knowledge_base_ids)
    )

    if not requested_ids:
        return []

    knowledge_bases = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.organization_id
            == organization_id,
            KnowledgeBase.id.in_(requested_ids),
        )
        .all()
    )

    found_ids = {
        knowledge_base.id
        for knowledge_base in knowledge_bases
    }

    if found_ids != set(requested_ids):
        raise HTTPException(
            status_code=400,
            detail="One or more knowledge bases are invalid",
        )

    return knowledge_bases


# ============================================================
# MARKETS
# ============================================================

@app.get("/api/markets")
def list_markets(
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
        )
    ),
):
    return {
        "items":
            AMERICA_MARKETS,

        "total":
            len(
                AMERICA_MARKETS
            ),
    }


@app.get("/api/markets/{country_code}")
def get_market_detail(
    country_code: str,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
        )
    ),
):
    market = get_market(
        country_code
    )

    if not market:
        raise HTTPException(
            status_code=404,
            detail=(
                "Market not supported"
            ),
        )

    return market


def _slugify_store_name(
    value: str,
):
    import re
    import unicodedata

    normalized = (
        unicodedata.normalize(
            "NFKD",
            value,
        )
        .encode(
            "ascii",
            "ignore",
        )
        .decode(
            "ascii"
        )
        .lower()
    )

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        normalized,
    ).strip("-")

    return slug or "store"


@app.get("/api/stores/{store_id}/dropi")
def get_dropi_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
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
        db.query(DropiConnection)
        .filter(
            DropiConnection.store_id
            == store.id,
            DropiConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "external_store_id": None,
            "api_url": None,
            "webhook_url": None,
            "connected_at": None,
            "last_sync_at": None,
            "last_error": None,
        }

    return {
        "connected":
            connection.status
            == "connected",

        "status":
            connection.status,

        "external_store_id":
            connection.external_store_id,

        "api_url":
            connection.api_url,

        "webhook_url":
            (
                "https://api.diaglob.tech"
                "/api/webhooks/dropi/"
                f"{connection.webhook_token}"
            ),

        "connected_at":
            (
                connection.connected_at.isoformat()
                + "Z"
                if connection.connected_at
                else None
            ),

        "last_sync_at":
            (
                connection.last_sync_at.isoformat()
                + "Z"
                if connection.last_sync_at
                else None
            ),

        "last_error":
            connection.last_error,
    }


@app.post("/api/stores/{store_id}/dropi/connect")
def connect_dropi(
    store_id: int,
    payload: DropiConnectRequest,
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
            detail={
                "code":
                    "STORE_NOT_ACTIVE",

                "message":
                    (
                        "La tienda debe estar activa "
                        "para conectar Dropi."
                    ),
            },
        )

    existing_connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.store_id
            == store.id,
        )
        .first()
    )

    if existing_connection:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "DROPPI_ALREADY_CONNECTED",

                "message":
                    (
                        "Esta tienda ya tiene "
                        "una conexión con Dropi."
                    ),
            },
        )

    api_token = (
        payload.api_token
        or ""
    ).strip()

    if not api_token:
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "DROPPI_TOKEN_REQUIRED",

                "message":
                    "El token de Dropi es obligatorio.",
            },
        )

    try:
        encrypted_token = (
            encrypt_dropi_secret(
                api_token
            )
        )

    except (
        RuntimeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "DROPPI_ENCRYPTION_NOT_CONFIGURED",

                "message":
                    (
                        "No fue posible almacenar "
                        "las credenciales de Dropi."
                    ),
            },
        ) from exc

    now = datetime.utcnow()

    connection = DropiConnection(
        organization_id=
            membership.organization_id,

        store_id=
            store.id,

        api_token_encrypted=
            encrypted_token,

        webhook_token=
            secrets.token_urlsafe(32),

        status=
            "connected",

        connected_at=
            now,

        last_sync_at=
            None,

        last_error=
            None,

        created_at=
            now,

        updated_at=
            now,
    )

    db.add(connection)

    try:
        db.commit()
        db.refresh(connection)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "DROPPI_CONNECTION_SAVE_FAILED",

                "message":
                    (
                        "No fue posible guardar "
                        "la conexión con Dropi."
                    ),
            },
        )

    return {
        "ok": True,
        "connected": True,
        "store_id": store.id,
        "status": connection.status,

        "webhook_url":
            (
                "https://api.diaglob.tech"
                "/api/webhooks/dropi/"
                f"{connection.webhook_token}"
            ),
    }


@app.delete("/api/stores/{store_id}/dropi/disconnect")
def disconnect_dropi(
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
        db.query(DropiConnection)
        .filter(
            DropiConnection.store_id
            == store.id,
            DropiConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "DROPPI_NOT_CONNECTED",

                "message":
                    (
                        "Esta tienda no tiene "
                        "Dropi conectado."
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


@app.post("/api/webhooks/dropi/{webhook_token}")
async def dropi_webhook(
    webhook_token: str,
    request: Request,
    db: Session = Depends(get_db),
):
    connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.webhook_token
            == webhook_token,
        )
        .first()
    )

    if (
        not connection
        or connection.status
        != "connected"
    ):
        raise HTTPException(
            status_code=404,
            detail="Webhook not found",
        )

    #
    # TODO: mapear eventos de Dropi cuando
    # la API oficial esté documentada.
    #
    # Por ahora solo se confirma recepción;
    # no se asume esquema ni se modifican
    # pedidos. El cuerpo se lee y se ignora.
    #
    await request.body()

    return {
        "ok": True,
    }


