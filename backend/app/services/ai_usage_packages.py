"""AI usage package catalog, checkout, and Paddle fulfillment."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..model_domains.ai_usage import AiUsageCreditGrant
from ..paddle_client import PaddleProviderError, create_ai_package_transaction


AI_USAGE_PACKAGES = {
    "ai_1000": {
        "responses": 1_000,
        "price_usd": Decimal("5.00"),
        "price_env": "PADDLE_PRICE_AI_1000",
    },
    "ai_5000": {
        "responses": 5_000,
        "price_usd": Decimal("25.00"),
        "price_env": "PADDLE_PRICE_AI_5000",
    },
    "ai_10000": {
        "responses": 10_000,
        "price_usd": Decimal("50.00"),
        "price_env": "PADDLE_PRICE_AI_10000",
    },
}


class InvalidAiUsagePackageError(Exception):
    pass


class AiUsagePackageUnavailableError(Exception):
    pass


def get_ai_usage_package(package_key: str) -> dict:
    normalized = (package_key or "").strip().lower()
    package = AI_USAGE_PACKAGES.get(normalized)
    if not package:
        raise InvalidAiUsagePackageError("Paquete de IA inválido")
    return {"key": normalized, **package}


def serialize_ai_usage_packages() -> list[dict]:
    items = []
    for key, package in AI_USAGE_PACKAGES.items():
        price_id = os.getenv(package["price_env"], "").strip()
        items.append(
            {
                "key": key,
                "responses": package["responses"],
                "price_usd": str(package["price_usd"]),
                "currency": "USD",
                "configured": bool(price_id),
            }
        )
    return items


def create_ai_usage_package_checkout(
    organization_id: int,
    package_key: str,
) -> dict:
    package = get_ai_usage_package(package_key)
    price_id = os.getenv(package["price_env"], "").strip()
    if not price_id:
        raise AiUsagePackageUnavailableError(
            "Este paquete de IA todavía no está configurado en Paddle"
        )

    data = create_ai_package_transaction(
        price_id=price_id,
        organization_id=organization_id,
        package_key=package["key"],
        responses=package["responses"],
    )

    checkout = data.get("checkout") or {}
    checkout_url = checkout.get("url")
    transaction_id = data.get("id")

    if not checkout_url or not transaction_id:
        raise PaddleProviderError(
            status_code=502,
            detail={"message": "Paddle no devolvió un checkout válido"},
        )

    return {
        "package_key": package["key"],
        "responses": package["responses"],
        "price_usd": str(package["price_usd"]),
        "currency": "USD",
        "transaction_id": transaction_id,
        "checkout_url": checkout_url,
    }


def _transaction_total(data: dict) -> tuple[int | None, str | None]:
    details = data.get("details") or {}
    totals = details.get("totals") or {}

    raw_amount = totals.get("grand_total")
    if raw_amount is None:
        raw_amount = totals.get("total")

    amount_minor = None
    if raw_amount is not None:
        try:
            amount_minor = int(raw_amount)
        except (TypeError, ValueError):
            amount_minor = None

    currency = data.get("currency_code") or totals.get("currency_code") or None
    if currency:
        currency = str(currency).upper()[:3]

    return amount_minor, currency


def _transaction_matches_package_price(data: dict, expected_price_id: str) -> bool:
    """Require the exact one-item transaction shape created by our checkout."""
    items = data.get("items") or []
    if len(items) != 1:
        return False

    item = items[0] or {}
    try:
        quantity = int(item.get("quantity", 0))
    except (TypeError, ValueError):
        return False
    if quantity != 1:
        return False

    price = item.get("price") or {}
    actual_price_id = price.get("id") or item.get("price_id")
    return str(actual_price_id or "") == expected_price_id


def fulfill_ai_usage_package_transaction(
    db: Session,
    organization_id: int,
    data: dict,
    occurred_at: datetime | None = None,
) -> dict:
    """Grant a paid package exactly once for a Paddle transaction."""
    transaction_id = str(data.get("id") or "").strip()
    custom_data = data.get("custom_data") or {}
    package_key = str(custom_data.get("package_key") or "").strip().lower()

    if not transaction_id:
        return {"ok": True, "ignored": True, "reason": "missing_transaction_id"}

    try:
        package = get_ai_usage_package(package_key)
    except InvalidAiUsagePackageError:
        return {"ok": True, "ignored": True, "reason": "invalid_package_key"}

    expected_price_id = os.getenv(package["price_env"], "").strip()
    if not expected_price_id:
        raise AiUsagePackageUnavailableError(
            "No se puede validar el paquete porque su precio Paddle no está configurado"
        )

    if not _transaction_matches_package_price(data, expected_price_id):
        return {
            "ok": True,
            "ignored": True,
            "reason": "package_price_mismatch",
            "package_key": package["key"],
        }

    existing = (
        db.query(AiUsageCreditGrant)
        .filter(
            AiUsageCreditGrant.provider == "paddle",
            AiUsageCreditGrant.provider_transaction_id == transaction_id,
        )
        .first()
    )
    if existing:
        return {
            "ok": True,
            "duplicate": True,
            "organization_id": organization_id,
            "package_key": existing.package_key,
            "responses": existing.responses_total,
            "grant_id": existing.id,
        }

    amount_minor, currency = _transaction_total(data)
    grant = AiUsageCreditGrant(
        organization_id=organization_id,
        package_key=package["key"],
        responses_total=package["responses"],
        responses_remaining=package["responses"],
        provider="paddle",
        provider_transaction_id=transaction_id,
        amount_minor=amount_minor,
        currency=currency or "USD",
        status="active",
        purchased_at=occurred_at or datetime.utcnow(),
    )
    db.add(grant)

    try:
        db.commit()
        db.refresh(grant)
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(AiUsageCreditGrant)
            .filter(
                AiUsageCreditGrant.provider == "paddle",
                AiUsageCreditGrant.provider_transaction_id == transaction_id,
            )
            .first()
        )
        if existing:
            return {
                "ok": True,
                "duplicate": True,
                "organization_id": organization_id,
                "package_key": existing.package_key,
                "responses": existing.responses_total,
                "grant_id": existing.id,
            }
        raise

    return {
        "ok": True,
        "credited": True,
        "organization_id": organization_id,
        "package_key": grant.package_key,
        "responses": grant.responses_total,
        "remaining": grant.responses_remaining,
        "grant_id": grant.id,
        "transaction_id": transaction_id,
    }
