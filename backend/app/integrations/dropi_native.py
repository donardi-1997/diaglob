"""Read-only Dropi Integrations transport for a native Shopify supplier connector.

This transport is opt-in: Diaglob must be enabled/authorized by Dropi
before any calls. No WooCommerce instance, Woo REST key or WordPress needed.
"""
from __future__ import annotations

import os

import httpx


BASE_URLS = {
    "CO": "https://api.dropi.co/integrations/",
    "MX": "https://api.dropi.mx/integrations/",
    "EC": "https://api.dropi.ec/integrations/",
    "CL": "https://api.dropi.cl/integrations/",
    "PE": "https://api.dropi.pe/integrations/",
    "PA": "https://api.dropi.pa/integrations/",
}


class DropiNativeError(Exception):
    """Contains only a safe error code, never the supplied token."""


def get_base_url(country_code: str) -> str:
    base = BASE_URLS.get((country_code or "").upper())
    if not base:
        raise DropiNativeError("DROPI_COUNTRY_UNSUPPORTED")
    return base


def preview_products(
    token: str,
    *,
    country_code: str = "CO",
    limit: int = 5,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Validate a user-supplied integration token through a bounded catalog read.

    No order creation, write permissions, credential logging or user-defined URLs.
    Access is off by default until Dropi authorizes the Diaglob integration.
    """
    if os.getenv("DROPI_NATIVE_API_ENABLED", "").lower() not in {"1", "true"}:
        raise DropiNativeError("DROPI_PARTNER_APPROVAL_REQUIRED")
    if not isinstance(token, str) or not token.strip():
        raise DropiNativeError("DROPI_TOKEN_REQUIRED")
    if not 1 <= limit <= 20:
        raise DropiNativeError("DROPI_INVALID_LIMIT")

    url = get_base_url(country_code) + "products/index"
    owns_client = client is None
    if owns_client:
        client = httpx.Client(
            timeout=httpx.Timeout(10.0, connect=4.0),
            trust_env=False,
            follow_redirects=False,
        )
    try:
        response = client.post(
            url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "dropi-integration-key": token.strip(),
            },
            json={
                "startData": 1,
                "pageSize": limit,
                "order_type": "DESC",
                "order_by": "created_at",
                "keywords": "",
                "active": True,
                "no_count": True,
                "integration": True,
                **({"get_stock": False} if country_code.upper() in {"CO", "PE", "PA"} else {}),
            },
        )
        if response.status_code in (401, 403):
            raise DropiNativeError("DROPI_AUTH_FAILED")
        if response.is_redirect:
            raise DropiNativeError("DROPI_REDIRECT_DENIED")
        if response.status_code >= 400:
            raise DropiNativeError("DROPI_PROVIDER_UNAVAILABLE")
        if len(response.content) > 2_000_000:
            raise DropiNativeError("DROPI_RESPONSE_TOO_LARGE")
        try:
            result = response.json()
        except ValueError as exc:
            raise DropiNativeError("DROPI_INVALID_RESPONSE") from exc
        if not isinstance(result, dict) or result.get("isSuccess") is not True:
            raise DropiNativeError("DROPI_AUTH_OR_PROVIDER_ERROR")
        items = result.get("objects")
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise DropiNativeError("DROPI_INVALID_RESPONSE")
        # No raw provider responses or supplier/private data returned to the UI.
        return [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "sku": item.get("sku"),
                "type": item.get("type"),
                "stock": item.get("stock"),
            }
            for item in items[:limit]
        ]
    except httpx.TimeoutException as exc:
        raise DropiNativeError("DROPI_TIMEOUT") from exc
    except httpx.RequestError as exc:
        raise DropiNativeError("DROPI_NETWORK_ERROR") from exc
    finally:
        if owns_client:
            client.close()
