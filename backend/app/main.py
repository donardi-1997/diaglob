"""Diaglob API — FastAPI application bootstrap."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .db import Base, engine
from .models import OrganizationMembership
from .runtime.lifespan import build_lifespan
from .runtime.rate_limit import InMemoryRateLimitBackend, RateLimitMiddleware
from .settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ============================================================
# APP CREATION
# ============================================================

app = FastAPI(
    title="Diaglob API",
    version="0.5.0",
    description="Backend API for Diaglob",
    lifespan=build_lifespan(settings),
)


# ============================================================
# MIDDLEWARE
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


# Add the rate limiter first so SecurityHeaders and CORS wrap 429 responses too.
# The backend boundary is replaceable; V1 preserves the current single-process
# deployment behavior without coupling the middleware to process-global state.
rate_limit_backend = InMemoryRateLimitBackend()

# Temporary compatibility shim for legacy tests that reset the old module-level
# store via ``_rate_limit_store.clear()``. The state itself now belongs to the
# backend object; migrate those tests to ``rate_limit_backend.clear()`` and remove
# this alias in a follow-up cleanup.
_rate_limit_store = rate_limit_backend

app.add_middleware(
    RateLimitMiddleware,
    backend=rate_limit_backend,
    enabled=settings.rate_limit_enabled,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.is_production and settings.rate_limit_enabled:
    logger.warning(
        "rate_limit.backend=in_memory; configure a shared backend before "
        "running multiple API workers or instances"
    )


# ============================================================
# API ROUTERS
# ============================================================

from .api.analytics import router as analytics_router  # noqa: E402
from .api.admin import router as admin_router  # noqa: E402
from .api.automations import router as automations_router  # noqa: E402
from .api.auth import router as auth_router  # noqa: E402
from .api.billing import router as billing_router  # noqa: E402
from .api.ai_usage import router as ai_usage_router  # noqa: E402
from .api.commerce import router as commerce_router  # noqa: E402
from .api.conversations import router as conversations_router  # noqa: E402
from .api.customer_risk import router as customer_risk_router  # noqa: E402
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
app.include_router(customer_risk_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(commerce_router)
app.include_router(shopify_router)
app.include_router(nuvemshop_router)
app.include_router(knowledge_router)
app.include_router(payments_router)
app.include_router(google_router)
app.include_router(billing_router)
app.include_router(ai_usage_router)
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
