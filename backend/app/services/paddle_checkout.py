"""Safely prepare Paddle.js direct checkout data."""

import hashlib
import hmac
import re
from collections.abc import Mapping


_VALID_PLANS = {"starter", "growth", "pro", "scale"}
_VALID_PERIODS = {1, 12}
_NON_COUNTRY_VALUES = {"XX", "ZZ", "EU", "UN", "T1", "A1", "A2", "O1"}
_COUNTRY_HEADERS = (
    "x-vercel-ip-country",
    "cloudfront-viewer-country",
    "cf-ipcountry",
)


def paddle_country_code(
    headers: Mapping[str, str],
    *,
    trusted_header: str | None = None,
) -> str | None:
    """Return a country code only from an explicitly trusted edge header."""
    selected_header = (trusted_header or "").strip().lower()
    if selected_header not in _COUNTRY_HEADERS:
        return None
    normalized_headers = {key.lower(): value for key, value in headers.items()}
    raw_country = normalized_headers.get(selected_header)
    if not raw_country:
        return None
    country = raw_country.strip().upper()
    if (
        re.fullmatch(r"[A-Z]{2}", country)
        and country not in _NON_COUNTRY_VALUES
    ):
        return country
    return None


def _checkout_signature_payload(
    organization_id: int,
    plan: str,
    billing_period_months: int,
    price_id: str,
) -> bytes:
    return (
        f"diaglob-paddle-checkout-v1\n{organization_id}\n{plan}\n"
        f"{billing_period_months}\n{price_id}"
    ).encode("utf-8")


def create_signed_checkout_custom_data(
    *,
    organization_id: int,
    plan: str,
    billing_period_months: int,
    price_id: str,
    secret: str,
) -> dict[str, str | int]:
    normalized_plan = plan.strip().lower()
    if organization_id < 1:
        raise ValueError("Invalid organization")
    if normalized_plan not in _VALID_PLANS:
        raise ValueError("Invalid Paddle plan")
    if billing_period_months not in _VALID_PERIODS:
        raise ValueError("Invalid Paddle billing period")
    if not price_id.strip():
        raise ValueError("Invalid Paddle price")
    if not secret:
        raise ValueError("Paddle checkout signing secret is not configured")

    payload = _checkout_signature_payload(
        organization_id,
        normalized_plan,
        billing_period_months,
        price_id,
    )
    signature = hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256,
    ).hexdigest()
    return {
        "organization_id": str(organization_id),
        "plan": normalized_plan,
        "billing_period_months": billing_period_months,
        "price_id": price_id,
        "checkout_signature": signature,
    }


def verify_signed_checkout_custom_data(
    custom_data: Mapping[str, object],
    *,
    actual_price_id: str | None,
    expected_price_id: str | None,
    secret: str,
) -> bool:
    try:
        organization_id = int(str(custom_data.get("organization_id", "")))
        plan = str(custom_data.get("plan", "")).strip().lower()
        billing_period_months = int(custom_data.get("billing_period_months", 0))
        price_id = str(custom_data.get("price_id", ""))
        signature = str(custom_data.get("checkout_signature", ""))
        if (
            organization_id < 1
            or plan not in _VALID_PLANS
            or billing_period_months not in _VALID_PERIODS
            or not secret
            or not signature
            or not actual_price_id
            or not expected_price_id
            or price_id != actual_price_id
            or price_id != expected_price_id
        ):
            return False
        payload = _checkout_signature_payload(
            organization_id, plan, billing_period_months, price_id,
        )
        expected_signature = hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(signature, expected_signature)
    except (TypeError, ValueError):
        return False
