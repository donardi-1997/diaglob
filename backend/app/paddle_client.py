"""Paddle HTTP provider module.

Owns base URL resolution, authentication headers, and raw httpx calls.
Business logic about WHEN to call Paddle lives in services.
"""
import os

import httpx


class PaddleConfigError(Exception):
    """Raised when Paddle configuration is missing."""


class PaddleProviderError(Exception):
    """Raised when Paddle API returns an error."""

    def __init__(self, status_code: int, detail: dict):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def get_paddle_base_url() -> str:
    environment = (
        os.getenv("PADDLE_ENVIRONMENT", "sandbox")
        .strip()
        .lower()
    )

    if environment == "production":
        return "https://api.paddle.com"

    return "https://sandbox-api.paddle.com"


def get_paddle_headers() -> dict:
    api_key = os.getenv("PADDLE_API_KEY")

    if not api_key:
        raise PaddleConfigError("Paddle API key not configured")

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def get_subscription(subscription_id: str) -> dict:
    url = f"{get_paddle_base_url()}/subscriptions/{subscription_id}"

    try:
        response = httpx.get(
            url,
            headers=get_paddle_headers(),
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise PaddleProviderError(
            status_code=502,
            detail={"message": "No fue posible consultar Paddle.", "error": str(exc)},
        ) from exc

    if response.status_code >= 400:
        raise PaddleProviderError(
            status_code=502,
            detail={
                "message": "Paddle rechazó la consulta de la suscripción.",
                "paddle_status": response.status_code,
                "paddle_response": response.text,
            },
        )

    return response.json().get("data") or {}


def preview_subscription_update(
    subscription_id: str,
    items: list[dict],
    proration_billing_mode: str,
    on_payment_failure: str = "prevent_change",
) -> dict:
    url = f"{get_paddle_base_url()}/subscriptions/{subscription_id}/preview"

    body = {
        "items": items,
        "proration_billing_mode": proration_billing_mode,
        "on_payment_failure": on_payment_failure,
    }

    try:
        response = httpx.patch(
            url,
            headers=get_paddle_headers(),
            json=body,
            timeout=30,
        )
    except httpx.RequestError:
        return {}

    if response.status_code >= 400:
        return {}

    return response.json().get("data") or {}


def update_subscription(
    subscription_id: str,
    items: list[dict],
    proration_billing_mode: str,
    on_payment_failure: str = "prevent_change",
    custom_data: dict | None = None,
    timeout: int = 45,
) -> dict:
    url = f"{get_paddle_base_url()}/subscriptions/{subscription_id}"

    body: dict = {
        "items": items,
        "proration_billing_mode": proration_billing_mode,
        "on_payment_failure": on_payment_failure,
    }

    if custom_data is not None:
        body["custom_data"] = custom_data

    try:
        response = httpx.patch(
            url,
            headers=get_paddle_headers(),
            json=body,
            timeout=timeout,
        )
    except httpx.RequestError as exc:
        raise PaddleProviderError(
            status_code=502,
            detail={"message": "Unable to contact Paddle", "error": str(exc)},
        ) from exc

    if response.status_code >= 400:
        raise PaddleProviderError(
            status_code=502,
            detail={
                "message": "Unable to upgrade Paddle subscription",
                "paddle_status": response.status_code,
                "paddle_response": response.text,
            },
        )

    return response.json().get("data") or {}


def cancel_subscription(subscription_id: str) -> dict:
    url = f"{get_paddle_base_url()}/subscriptions/{subscription_id}/cancel"

    try:
        response = httpx.post(
            url,
            headers=get_paddle_headers(),
            json={"effective_from": "next_billing_period"},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise PaddleProviderError(
            status_code=502,
            detail={"message": "No fue posible programar la cancelación en Paddle.", "error": str(exc)},
        ) from exc

    if response.status_code >= 400:
        raise PaddleProviderError(
            status_code=502,
            detail={
                "message": "Paddle rechazó la cancelación programada.",
                "paddle_status": response.status_code,
                "paddle_response": response.text,
            },
        )

    return response.json().get("data") or {}


def resume_subscription(subscription_id: str) -> dict:
    url = f"{get_paddle_base_url()}/subscriptions/{subscription_id}"

    try:
        response = httpx.patch(
            url,
            headers=get_paddle_headers(),
            json={"scheduled_change": None},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise PaddleProviderError(
            status_code=502,
            detail={"message": "No fue posible reactivar la renovación en Paddle.", "error": str(exc)},
        ) from exc

    if response.status_code >= 400:
        raise PaddleProviderError(
            status_code=502,
            detail={
                "message": "Paddle rechazó la reactivación de la renovación.",
                "paddle_status": response.status_code,
                "paddle_response": response.text,
            },
        )

    return response.json().get("data") or {}


def create_ai_package_transaction(
    price_id: str,
    organization_id: int,
    package_key: str,
    responses: int,
) -> dict:
    body = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "collection_mode": "automatic",
        "custom_data": {
            "purchase_type": "ai_usage_package",
            "organization_id": str(organization_id),
            "package_key": package_key,
            "responses": int(responses),
        },
    }

    try:
        response = httpx.post(
            f"{get_paddle_base_url()}/transactions",
            headers=get_paddle_headers(),
            json=body,
            timeout=20,
        )
    except httpx.RequestError as exc:
        raise PaddleProviderError(
            status_code=502,
            detail={"message": "No fue posible conectar con Paddle", "error": str(exc)},
        ) from exc

    if response.status_code >= 400:
        raise PaddleProviderError(
            status_code=502,
            detail={
                "message": "Paddle rechazó la compra del paquete de IA",
                "paddle_status": response.status_code,
                "paddle_response": response.text,
            },
        )

    return response.json().get("data") or {}


def create_transaction(
    price_id: str,
    organization_id: int,
    plan_key: str,
    billing_period_months: int,
) -> dict:
    body = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "collection_mode": "automatic",
        "custom_data": {
            "organization_id": str(organization_id),
            "plan": plan_key,
            "billing_period_months": billing_period_months,
        },
    }

    try:
        response = httpx.post(
            f"{get_paddle_base_url()}/transactions",
            headers=get_paddle_headers(),
            json=body,
            timeout=20,
        )
    except httpx.RequestError as exc:
        raise PaddleProviderError(
            status_code=502,
            detail={"message": "No fue posible conectar con Paddle", "error": str(exc)},
        ) from exc

    if response.status_code >= 400:
        raise PaddleProviderError(
            status_code=502,
            detail={
                "message": "Paddle rechazó la transacción",
                "provider_response": response.json(),
            },
        )

    return response.json().get("data") or {}
