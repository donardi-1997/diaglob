"""CJdropshipping API V2 client.

Owns HTTP transport, authentication requests, provider error normalization and
CJ timestamp parsing. Business persistence belongs in services.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

CJ_BASE_URL = os.getenv(
    "CJ_API_BASE_URL",
    "https://developers.cjdropshipping.com/api2.0/v1",
).rstrip("/")
CJ_TIMEOUT = 30


class CJError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class CJAuthError(CJError):
    pass


class CJRateLimitError(CJError):
    pass


class CJTemporaryError(CJError):
    pass


def parse_cj_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CJError("CJ returned an invalid token expiry timestamp") from exc

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _raise_cj_error(
    *,
    status_code: int,
    payload: dict[str, Any] | None,
) -> None:
    payload = payload or {}
    code_raw = payload.get("code")
    try:
        code = int(code_raw) if code_raw is not None else None
    except (TypeError, ValueError):
        code = None

    message = str(payload.get("message") or f"CJ API error: HTTP {status_code}")

    if status_code == 401 or code in {1600001, 1600002, 1600003, 1600004, 1600005, 1600006, 1600014}:
        raise CJAuthError(message, code)
    if status_code == 429 or code == 1600200:
        raise CJRateLimitError(message, code)
    if status_code >= 500:
        raise CJTemporaryError(message, code)
    raise CJError(message, code)


def _request(
    method: str,
    path: str,
    *,
    access_token: str | None = None,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: int = CJ_TIMEOUT,
) -> dict[str, Any]:
    url = f"{CJ_BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if access_token:
        headers["CJ-Access-Token"] = access_token

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
            )
    except httpx.TimeoutException as exc:
        raise CJTemporaryError("CJ API request timed out") from exc
    except httpx.RequestError as exc:
        raise CJTemporaryError("Unable to reach CJ API") from exc

    payload: dict[str, Any] | None
    try:
        payload = response.json()
    except ValueError:
        payload = None

    code = payload.get("code") if isinstance(payload, dict) else None
    successful_code = code is None or str(code) == "200"

    if response.status_code != 200 or not successful_code:
        _raise_cj_error(status_code=response.status_code, payload=payload)

    if payload is None:
        raise CJError("CJ returned invalid JSON")

    return payload


def get_access_token(api_key: str) -> dict[str, Any]:
    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("CJ API key is required")

    payload = _request(
        "POST",
        "/authentication/getAccessToken",
        json_body={"apiKey": api_key},
    )
    data = payload.get("data") or {}
    if not data.get("accessToken") or not data.get("refreshToken"):
        raise CJError("CJ authentication response did not include tokens")
    return data


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    refresh_token = (refresh_token or "").strip()
    if not refresh_token:
        raise ValueError("CJ refresh token is required")

    payload = _request(
        "POST",
        "/authentication/refreshAccessToken",
        json_body={"refreshToken": refresh_token},
    )
    data = payload.get("data") or {}
    if not data.get("accessToken") or not data.get("refreshToken"):
        raise CJError("CJ refresh response did not include tokens")
    return data


def get_settings(access_token: str) -> dict[str, Any]:
    payload = _request(
        "GET",
        "/setting/get",
        access_token=access_token,
    )
    return payload.get("data") or {}


def list_products(
    access_token: str,
    *,
    query: str | None = None,
    limit: int = 20,
    page: int = 1,
) -> dict[str, Any]:
    if limit < 1 or limit > 100:
        raise ValueError("CJ product list limit must be between 1 and 100")
    if page < 1 or page > 1000:
        raise ValueError("CJ product list page must be between 1 and 1000")

    params: dict[str, Any] = {
        "page": page,
        "size": limit,
    }
    if query and query.strip():
        params["keyWord"] = query.strip()

    payload = _request(
        "GET",
        "/product/listV2",
        access_token=access_token,
        params=params,
    )
    return payload.get("data") or {}


def get_product(
    access_token: str,
    product_id: str,
) -> dict[str, Any]:
    product_id = (product_id or "").strip()
    if not product_id:
        raise ValueError("CJ product id is required")

    payload = _request(
        "GET",
        "/product/query",
        access_token=access_token,
        params={"pid": product_id},
    )
    return payload.get("data") or {}


def get_variants(
    access_token: str,
    product_id: str,
    *,
    country_code: str | None = None,
) -> list[dict[str, Any]]:
    product_id = (product_id or "").strip()
    if not product_id:
        raise ValueError("CJ product id is required")

    params: dict[str, Any] = {"pid": product_id}
    if country_code:
        normalized_country = country_code.strip().upper()
        if len(normalized_country) != 2 or not normalized_country.isalpha():
            raise ValueError("country_code must be ISO-3166 alpha-2")
        params["countryCode"] = normalized_country

    payload = _request(
        "GET",
        "/product/variant/query",
        access_token=access_token,
        params=params,
    )
    return payload.get("data") or []


def get_stock(
    access_token: str,
    variant_id: str,
) -> list[dict[str, Any]]:
    variant_id = (variant_id or "").strip()
    if not variant_id:
        raise ValueError("CJ variant id is required")

    payload = _request(
        "GET",
        "/product/stock/queryByVid",
        access_token=access_token,
        params={"vid": variant_id},
    )
    return payload.get("data") or []


def calculate_freight(
    access_token: str,
    *,
    start_country_code: str,
    end_country_code: str,
    products: list[dict[str, Any]],
    zip_code: str | None = None,
) -> list[dict[str, Any]]:
    start = (start_country_code or "").strip().upper()
    end = (end_country_code or "").strip().upper()
    if len(start) != 2 or not start.isalpha():
        raise ValueError("start_country_code must be ISO-3166 alpha-2")
    if len(end) != 2 or not end.isalpha():
        raise ValueError("end_country_code must be ISO-3166 alpha-2")
    if not products:
        raise ValueError("At least one product is required for freight calculation")

    normalized_products = []
    for item in products:
        variant_id = str(item.get("variant_id") or item.get("vid") or "").strip()
        quantity = int(item.get("quantity") or 0)
        if not variant_id:
            raise ValueError("Every freight item requires a variant id")
        if quantity <= 0:
            raise ValueError("Every freight item quantity must be greater than zero")
        normalized_products.append({"vid": variant_id, "quantity": quantity})

    body: dict[str, Any] = {
        "startCountryCode": start,
        "endCountryCode": end,
        "products": normalized_products,
    }
    if zip_code and zip_code.strip():
        body["zip"] = zip_code.strip()

    payload = _request(
        "POST",
        "/logistic/freightCalculate",
        access_token=access_token,
        json_body=body,
    )
    return payload.get("data") or []
