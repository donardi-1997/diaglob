"""HTTP security middleware shared by all API responses."""
from __future__ import annotations

import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def apply_security_headers(
    request_path: str,
    query_string: bytes,
    response: Response,
) -> Response:
    """Apply shared response headers, with narrow Shopify iframe exceptions."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request_path == "/api/shopify/embedded" and response.status_code == 200:
        # The public shell contains no tenant data. A canonical shop hint
        # narrows framing only; it NEVER authenticates a shop or user.
        # Private requests still require independently verified ID tokens.
        ancestors = ["https://admin.shopify.com"]
        if len(query_string) <= 16_384:
            from starlette.datastructures import QueryParams

            shops = QueryParams(query_string.decode("latin-1")).getlist("shop")
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
    elif request_path == "/app/plans" and response.status_code == 302:
        # This fixed-origin redirect handles a legacy/private plan welcome
        # link and is safe to load only inside Shopify Admin.
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors https://admin.shopify.com; "
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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next,
    ) -> Response:
        response = await call_next(request)

        return apply_security_headers(
            request.url.path,
            request.scope.get("query_string", b""),
            response,
        )
