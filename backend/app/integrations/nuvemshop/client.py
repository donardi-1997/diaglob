"""Nuvemshop/Tiendanube provider client.

Handles Nuvemshop API HTTP requests.
Owns: base URL, auth, pagination, timeouts, provider error normalization.
Does NOT own: business logic, analytics formulas, billing.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

NUVEMSHOP_API_VERSION = os.getenv("NUVEMSHOP_API_VERSION", "2025-03-01")
NUVEMSHOP_BASE_URL = os.getenv("NUVEMSHOP_BASE_URL", "https://api.tiendanube.com/v1")


class NuvemshopError(Exception):
    """Base Nuvemshop error."""
    def __init__(self, message: str, code: str = "NUVEMSHOP_UNKNOWN_ERROR"):
        super().__init__(message)
        self.code = code


class NuvemshopAuthError(NuvemshopError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, "NUVEMSHOP_AUTH_REQUIRED")


class NuvemshopPermissionError(NuvemshopError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, "NUVEMSHOP_PERMISSION_DENIED")


class NuvemshopRateLimitError(NuvemshopError):
    def __init__(self, message: str = "Rate limited"):
        super().__init__(message, "NUVEMSHOP_RATE_LIMITED")


class NuvemshopTemporaryError(NuvemshopError):
    def __init__(self, message: str = "Temporary error"):
        super().__init__(message, "NUVEMSHOP_TEMPORARY_ERROR")


def _handle_nuvemshop_error(response: httpx.Response):
    """Normalize Nuvemshop API errors."""
    try:
        data = response.json()
        message = data.get("message", "Unknown Nuvemshop API error")
    except Exception:
        message = f"Nuvemshop API error: {response.status_code}"

    if response.status_code == 401:
        raise NuvemshopAuthError(message)
    elif response.status_code == 403:
        raise NuvemshopPermissionError(message)
    elif response.status_code == 429:
        raise NuvemshopRateLimitError(message)
    elif response.status_code >= 500:
        raise NuvemshopTemporaryError(message)
    else:
        raise NuvemshopError(message, "NUVEMSHOP_INVALID_REQUEST")


def _request(
    method: str,
    path: str,
    access_token: str,
    store_id: str,
    params: dict | None = None,
    json_body: dict | None = None,
    timeout: int = 30,
) -> dict:
    """Make a Nuvemshop API request."""
    url = f"{NUVEMSHOP_BASE_URL}/{store_id}{path}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method, url, headers=headers, params=params, json=json_body
            )
    except httpx.TimeoutException:
        raise NuvemshopTemporaryError("Nuvemshop API request timed out")
    except httpx.RequestError as exc:
        raise NuvemshopTemporaryError(f"Nuvemshop API request failed: {exc}")

    if response.status_code >= 400:
        _handle_nuvemshop_error(response)

    return response.json()


def get_store_info(access_token: str, store_id: str) -> dict:
    """Get store information."""
    return _request("GET", "/store", access_token, store_id)


def list_products(
    access_token: str,
    store_id: str,
    page: int = 1,
    per_page: int = 50,
) -> dict:
    """List products with pagination."""
    params = {"page": page, "per_page": per_page}
    return _request("GET", "/products", access_token, store_id, params=params)


def get_product(access_token: str, store_id: str, product_id: str) -> dict:
    """Get a single product."""
    return _request("GET", f"/products/{product_id}", access_token, store_id)


def list_customers(
    access_token: str,
    store_id: str,
    page: int = 1,
    per_page: int = 50,
) -> dict:
    """List customers with pagination."""
    params = {"page": page, "per_page": per_page}
    return _request("GET", "/customers", access_token, store_id, params=params)


def list_orders(
    access_token: str,
    store_id: str,
    page: int = 1,
    per_page: int = 50,
    status: str | None = None,
) -> dict:
    """List orders with pagination."""
    params = {"page": page, "per_page": per_page}
    if status:
        params["status"] = status
    return _request("GET", "/orders", access_token, store_id, params=params)


def get_order(access_token: str, store_id: str, order_id: str) -> dict:
    """Get a single order."""
    return _request("GET", f"/orders/{order_id}", access_token, store_id)


def parse_product(product: dict) -> dict:
    """Parse a Nuvemshop product into safe canonical form."""
    images = product.get("images") or []
    image_url = images[0].get("src") if images else None

    variants = []
    for v in product.get("variants") or []:
        variants.append({
            "external_id": str(v.get("id", "")),
            "title": v.get("name") or "",
            "sku": v.get("sku"),
            "price": Decimal(str(v.get("price") or 0)),
            "compare_at_price": Decimal(str(v.get("compare_at_price") or 0)) if v.get("compare_at_price") else None,
            "inventory_quantity": int(v.get("stock") or 0),
            "available": bool(v.get("published")),
        })

    return {
        "external_id": str(product.get("id", "")),
        "title": product.get("name") or "",
        "handle": product.get("slug"),
        "description": product.get("description") or "",
        "image_url": image_url,
        "active": bool(product.get("published")),
        "variants": variants,
        "created_at": product.get("created_at"),
        "updated_at": product.get("updated_at"),
    }


def parse_customer(customer: dict) -> dict:
    """Parse a Nuvemshop customer into safe canonical form."""
    return {
        "external_id": str(customer.get("id", "")),
        "name": f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
        "email": customer.get("email"),
        "phone": customer.get("phone"),
        "created_at": customer.get("created_at"),
        "updated_at": customer.get("updated_at"),
    }


def parse_order(order: dict) -> dict:
    """Parse a Nuvemshop order into safe canonical form."""
    payment_method = None
    payment_status = None

    # Nuvemshop exposes payment info in gateway fields
    gateway = order.get("gateway") or ""
    payment_details = order.get("payment_details") or {}

    if "pix" in gateway.lower() or "pix" in str(payment_details).lower():
        payment_method = "PIX"
    elif "boleto" in gateway.lower():
        payment_method = "BOLETO"
    elif "credit" in gateway.lower() or "card" in gateway.lower():
        payment_method = "CREDIT_CARD"
    else:
        payment_method = "OTHER" if gateway else "UNKNOWN"

    # Map Nuvemshop payment status
    financial_status = order.get("financial_status") or ""
    if financial_status == "paid":
        payment_status = "PAID"
    elif financial_status == "pending":
        payment_status = "PENDING"
    elif financial_status == "refunded":
        payment_status = "REFUNDED"
    elif financial_status == "voided":
        payment_status = "CANCELLED"
    else:
        payment_status = "UNKNOWN"

    # Fulfillment status
    fulfillment_status = order.get("fulfillment_status") or ""
    if fulfillment_status == "fulfilled":
        fulfillment = "fulfilled"
    elif fulfillment_status == "partial":
        fulfillment = "partial"
    elif fulfillment_status == "unfulfilled":
        fulfillment = "unfulfilled"
    else:
        fulfillment = None

    return {
        "external_order_id": str(order.get("id", "")),
        "order_number": order.get("order_number") or str(order.get("id", "")),
        "total_amount": Decimal(str(order.get("total") or 0)),
        "currency": order.get("currency") or "BRL",
        "financial_status": financial_status,
        "payment_method": payment_method,
        "payment_status": payment_status,
        "fulfillment_status": fulfillment,
        "note": order.get("note"),
        "source": "nuvemshop",
        "created_at": order.get("created_at"),
        "updated_at": order.get("updated_at"),
    }
