"""Diaglob API — FastAPI application bootstrap."""

import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .db import Base, engine
from .models import OrganizationMembership

logger = logging.getLogger(__name__)


# ============================================================
# LIFESPAN
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: runs startup/shutdown logic.

    CRITICAL: Base.metadata.create_all is NOT called here.
    Schema is managed by Alembic. For local/test environments
    that need automatic schema creation, use alembic upgrade head
    or the test-local create_all fixtures.
    """
    from .services.knowledge_provisioning import reconcile_knowledge_base_provisioning

    reconcile_knowledge_base_provisioning()

    yield


# ============================================================
# APP CREATION
# ============================================================

app = FastAPI(
    title="Diaglob API",
    version="0.5.0",
    description="Backend API for Diaglob",
    lifespan=lifespan,
)

# ============================================================
# MIDDLEWARE
# ============================================================

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

from .api.analytics import router as analytics_router  # noqa: E402
from .api.admin import router as admin_router  # noqa: E402
from .api.automations import router as automations_router  # noqa: E402
from .api.auth import router as auth_router  # noqa: E402
from .api.billing import router as billing_router  # noqa: E402
from .api.commerce import router as commerce_router  # noqa: E402
from .api.conversations import router as conversations_router  # noqa: E402
from .api.customers import router as customers_router  # noqa: E402
from .api.dropi import router as dropi_router  # noqa: E402
from .api.google import router as google_router  # noqa: E402
from .api.health import router as health_router  # noqa: E402
from .api.knowledge import router as knowledge_router  # noqa: E402
from .api.markets import router as markets_router  # noqa: E402
from .api.orders import router as orders_router  # noqa: E402
from .api.organizations import router as organizations_router  # noqa: E402
from .api.products import router as products_router  # noqa: E402
from .api.nuvemshop import router as nuvemshop_router  # noqa: E402
from .api.payments import router as payments_router  # noqa: E402
from .api.shopify import router as shopify_router  # noqa: E402
from .api.dropshipping_analytics import router as dropshipping_analytics_router  # noqa: E402
from .api.stores import router as stores_router  # noqa: E402
from .api.telegram import router as telegram_router  # noqa: E402
from .api.whatsapp import router as whatsapp_router  # noqa: E402

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(organizations_router)
app.include_router(stores_router)
app.include_router(customers_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(commerce_router)
app.include_router(shopify_router)
app.include_router(nuvemshop_router)
app.include_router(knowledge_router)
app.include_router(payments_router)
app.include_router(google_router)
app.include_router(billing_router)
app.include_router(automations_router)
app.include_router(whatsapp_router)
app.include_router(telegram_router)
app.include_router(conversations_router)
app.include_router(analytics_router)
app.include_router(dropshipping_analytics_router)
app.include_router(dropi_router)
app.include_router(markets_router)
app.include_router(admin_router)

# ============================================================
# TEST COMPATIBILITY RE-EXPORTS
# ============================================================
# Tests import these from app.main for dependency overrides.
# Keep until tests are migrated to import from api.deps directly.

from .api.deps import (  # noqa: E402, F401
    get_current_user,
    get_current_membership,
    require_permission,
)
