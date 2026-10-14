"""HTTP security middleware shared by all API responses."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path == "/api/shopify/embedded" and response.status_code == 200:
            # Only Shopify App Home is frameable, and only by Shopify admin.
            response.headers["Content-Security-Policy"] = (
                "frame-ancestors https://admin.shopify.com https://*.myshopify.com; "
                "base-uri 'none'; object-src 'none'"
            )
            response.headers.pop("X-Frame-Options", None)
        else:
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        return response
