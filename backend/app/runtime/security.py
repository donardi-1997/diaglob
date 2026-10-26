"""HTTP security middleware shared by all API responses."""
from __future__ import annotations

import re

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
            # The public shell contains no tenant data. A canonical shop hint
            # narrows framing only; it NEVER authenticates a shop or user.
            # Private requests still require independently verified ID tokens.
            ancestors = ["https://admin.shopify.com"]
            if len(request.scope.get("query_string", b"")) <= 16_384:
                shops = request.query_params.getlist("shop")
                if len(shops) == 1 and len(shops[0]) <= 255 and re.fullmatch(
                    r"[a-z0-9][a-z0-9-]*\.myshopify\.com", shops[0],
                ):
                    ancestors.append(f"https://{shops[0]}")
            response.headers["Content-Security-Policy"] = (
                f"frame-ancestors {' '.join(ancestors)}; "
                "base-uri 'none'; object-src 'none'"
            )
            if "X-Frame-Options" in response.headers:
                del response.headers["X-Frame-Options"]
        else:
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        return response
