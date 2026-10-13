"""Small, read-only WooCommerce REST v3 transport for the Dropi bridge.

The Dropi token belongs in the WooCommerce Dropify plugin. These are separate
WooCommerce consumer credentials. No undocumented Dropi API is called.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx


class WooCommerceError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def normalize_woocommerce_url(raw_url: str) -> str:
    """Only accept publicly routable HTTPS storefronts on port 443."""
    try:
        parsed = urlsplit((raw_url or "").strip())
        port = parsed.port
    except ValueError as exc:
        raise WooCommerceError("WOO_INVALID_URL") from exc

    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in (None, 443)
    ):
        raise WooCommerceError("WOO_INVALID_URL")

    hostname = parsed.hostname.rstrip(".").lower()
    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise WooCommerceError("WOO_INVALID_URL") from exc

    if (
        len(hostname) > 253
        or "." not in hostname
        or hostname.endswith((".local", ".internal", ".localhost", ".test", ".invalid"))
        or any(not label or len(label) > 63 for label in hostname.split("."))
    ):
        raise WooCommerceError("WOO_INVALID_URL")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise WooCommerceError("WOO_INVALID_URL")

    path = parsed.path.rstrip("/")
    if "\\" in path or ".." in path.split("/") or path.startswith("//"):
        raise WooCommerceError("WOO_INVALID_URL")
    return f"https://{hostname}{path}"


def assert_public_dns(base_url: str) -> None:
    """Deny private/loopback/reserved DNS answers on every outbound request.

    DNS re-binding remains a reason to deploy this connector behind an
    outbound egress policy that blocks private destinations at network level.
    """
    hostname = urlsplit(base_url).hostname
    if not hostname:
        raise WooCommerceError("WOO_INVALID_URL")
    try:
        resolved = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise WooCommerceError("WOO_DNS_UNAVAILABLE") from exc
    if not resolved:
        raise WooCommerceError("WOO_DNS_UNAVAILABLE")
    for item in resolved:
        try:
            address = ipaddress.ip_address(item[4][0])
        except ValueError as exc:
            raise WooCommerceError("WOO_DNS_UNAVAILABLE") from exc
        if not address.is_global:
            raise WooCommerceError("WOO_UNSAFE_DESTINATION")


def list_woocommerce(
    base_url: str,
    consumer_key: str,
    consumer_secret: str,
    resource: str,
    *,
    limit: int = 5,
    client: httpx.Client | None = None,
) -> list[dict]:
    """Fetch a bounded, authenticated WooCommerce resource; never mutate."""
    if resource not in {"products", "orders"}:
        raise WooCommerceError("WOO_UNSUPPORTED_RESOURCE")
    if not (1 <= limit <= 20):
        raise WooCommerceError("WOO_INVALID_LIMIT")
    url = normalize_woocommerce_url(base_url)
    if not consumer_key or not consumer_secret:
        raise WooCommerceError("WOO_CREDENTIALS_REQUIRED")
    assert_public_dns(url)
    endpoint = f"{url}/wp-json/wc/v3/{resource}"
    own_client = client is None
    if own_client:
        client = httpx.Client(
            timeout=httpx.Timeout(10.0, connect=4.0),
            follow_redirects=False,
            trust_env=False,
        )
    try:
        response = client.get(
            endpoint,
            params={"per_page": limit, "page": 1},
            auth=httpx.BasicAuth(consumer_key, consumer_secret),
            headers={"Accept": "application/json"},
        )
        if response.status_code in (401, 403):
            raise WooCommerceError("WOO_AUTH_FAILED")
        if response.status_code == 404:
            raise WooCommerceError("WOO_API_NOT_FOUND")
        if response.is_redirect:
            raise WooCommerceError("WOO_REDIRECT_DENIED")
        if response.status_code >= 400:
            raise WooCommerceError("WOO_PROVIDER_ERROR")
        if len(response.content) > 2_000_000:
            raise WooCommerceError("WOO_RESPONSE_TOO_LARGE")
        try:
            data = response.json()
        except ValueError as exc:
            raise WooCommerceError("WOO_INVALID_RESPONSE") from exc
        if not isinstance(data, list) or any(not isinstance(p, dict) for p in data):
            raise WooCommerceError("WOO_INVALID_RESPONSE")
        return data
    except httpx.TimeoutException as exc:
        raise WooCommerceError("WOO_TIMEOUT") from exc
    except httpx.RequestError as exc:
        raise WooCommerceError("WOO_UNREACHABLE") from exc
    finally:
        if own_client:
            client.close()


def preview_woocommerce_products(rows: list[dict]) -> list[dict]:
    """Expose only catalog metadata; no arbitrary plugin-specific fields."""
    return [
        {
            "id": row.get("id"),
            "name": row.get("name"),
            "sku": row.get("sku"),
            "type": row.get("type"),
            "status": row.get("status"),
            "stock_status": row.get("stock_status"),
            "stock_quantity": row.get("stock_quantity"),
        }
        for row in rows
    ]


def preview_woocommerce_orders(rows: list[dict]) -> list[dict]:
    """Do not return customer addresses, phone numbers, or raw order payloads."""
    return [
        {
            "id": row.get("id"),
            "number": row.get("number"),
            "status": row.get("status"),
            "currency": row.get("currency"),
            "total": row.get("total"),
            "line_items_count": len(row.get("line_items") or []),
        }
        for row in rows
    ]
