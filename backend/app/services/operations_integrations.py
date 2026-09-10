"""Dynamic integration summary for the Operations Center."""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar

from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection,
    DropiConnection,
    GoogleConnection,
    MetaAdsConnection,
    PaymentConnection,
    Store,
    WhatsAppConnection,
)
from ..operations import get_operations_summary
from ..payments.registry import get_providers_for_market
from ..telegram_models import TelegramConnection

logger = logging.getLogger(__name__)

T = TypeVar("T")
_FAILED = object()


def _display_provider(provider: str) -> str:
    labels = {
        "shopify": "Shopify",
        "nuvemshop": "Nuvemshop",
        "dropi": "Dropi",
        "meta_ads": "Meta Ads",
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
        "google": "Google",
    }
    return labels.get(
        provider,
        provider.replace("_", " ").title(),
    )


def _item(
    *,
    key: str,
    provider: str,
    name: str,
    category: str,
    connected: bool,
    status: str,
    available: bool = True,
    scope: str = "store",
    payment_methods: list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "key": key,
        "provider": provider,
        "name": name,
        "category": category,
        "connected": connected,
        "status": status,
        "available": available,
        "scope": scope,
    }
    if payment_methods is not None:
        result["payment_methods"] = payment_methods
    return result


def _degraded_item(
    *,
    key: str,
    provider: str,
    name: str,
    category: str,
    scope: str = "store",
    payment_methods: list[str] | None = None,
) -> dict[str, Any]:
    result = _item(
        key=key,
        provider=provider,
        name=name,
        category=category,
        connected=False,
        status="degraded",
        scope=scope,
        payment_methods=payment_methods,
    )
    result["degraded"] = True
    result["error_code"] = "integration_status_unavailable"
    return result


def _isolated_read(
    db: Session,
    integration_key: str,
    reader: Callable[[], T],
) -> T | object:
    """Read one integration behind a savepoint.

    PostgreSQL marks a transaction as failed after a statement error. A nested
    transaction gives every integration its own SAVEPOINT so one broken table
    or query does not poison the rest of the Operations Center aggregation.
    """
    try:
        with db.begin_nested():
            return reader()
    except Exception:
        logger.exception(
            "Operations integration status lookup failed",
            extra={"integration_key": integration_key},
        )
        return _FAILED


def get_operations_integrations(
    db: Session,
    organization_id: int,
    store_id: int,
) -> list[dict[str, Any]]:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if store is None:
        return []

    integrations: list[dict[str, Any]] = []

    whatsapp = _isolated_read(
        db,
        "whatsapp",
        lambda: (
            db.query(WhatsAppConnection)
            .filter(
                WhatsAppConnection.organization_id == organization_id,
                WhatsAppConnection.store_id == store_id,
            )
            .first()
        ),
    )
    if whatsapp is _FAILED:
        integrations.append(
            _degraded_item(
                key="whatsapp",
                provider="whatsapp",
                name="WhatsApp",
                category="messaging",
            )
        )
    else:
        whatsapp_status = whatsapp.status if whatsapp else "disconnected"
        integrations.append(
            _item(
                key="whatsapp",
                provider="whatsapp",
                name="WhatsApp",
                category="messaging",
                connected=whatsapp_status == "connected",
                status=whatsapp_status,
            )
        )

    telegram = _isolated_read(
        db,
        "telegram",
        lambda: (
            db.query(TelegramConnection)
            .filter(
                TelegramConnection.organization_id == organization_id,
                TelegramConnection.store_id == store_id,
            )
            .first()
        ),
    )
    if telegram is _FAILED:
        integrations.append(
            _degraded_item(
                key="telegram",
                provider="telegram",
                name="Telegram",
                category="messaging",
            )
        )
    else:
        telegram_status = telegram.status if telegram else "disconnected"
        integrations.append(
            _item(
                key="telegram",
                provider="telegram",
                name="Telegram",
                category="messaging",
                connected=telegram_status == "connected",
                status=telegram_status,
            )
        )

    commerce = _isolated_read(
        db,
        "commerce",
        lambda: (
            db.query(CommerceConnection)
            .filter(
                CommerceConnection.organization_id == organization_id,
                CommerceConnection.store_id == store_id,
            )
            .first()
        ),
    )
    if commerce is _FAILED:
        if store.shopify_domain:
            integrations.append(
                _degraded_item(
                    key="commerce:shopify",
                    provider="shopify",
                    name="Shopify",
                    category="commerce",
                )
            )
        else:
            integrations.append(
                _degraded_item(
                    key="commerce:unknown",
                    provider="commerce",
                    name="Commerce",
                    category="commerce",
                )
            )
    elif commerce:
        integrations.append(
            _item(
                key=f"commerce:{commerce.provider}",
                provider=commerce.provider,
                name=_display_provider(commerce.provider),
                category="commerce",
                connected=commerce.status == "connected",
                status=commerce.status,
            )
        )
    elif store.shopify_domain:
        integrations.append(
            _item(
                key="commerce:shopify",
                provider="shopify",
                name="Shopify",
                category="commerce",
                connected=True,
                status="connected",
            )
        )

    dropi = _isolated_read(
        db,
        "dropi",
        lambda: (
            db.query(DropiConnection)
            .filter(
                DropiConnection.organization_id == organization_id,
                DropiConnection.store_id == store_id,
            )
            .first()
        ),
    )
    if dropi is _FAILED:
        integrations.append(
            _degraded_item(
                key="dropi",
                provider="dropi",
                name="Dropi",
                category="supplier",
            )
        )
    elif dropi:
        integrations.append(
            _item(
                key="dropi",
                provider="dropi",
                name="Dropi",
                category="supplier",
                connected=dropi.status == "connected",
                status=dropi.status,
            )
        )

    google = _isolated_read(
        db,
        "google",
        lambda: (
            db.query(GoogleConnection)
            .filter(GoogleConnection.organization_id == organization_id)
            .first()
        ),
    )
    if google is _FAILED:
        integrations.append(
            _degraded_item(
                key="google",
                provider="google",
                name="Google",
                category="knowledge",
                scope="organization",
            )
        )
    elif google:
        integrations.append(
            _item(
                key="google",
                provider="google",
                name="Google",
                category="knowledge",
                connected=google.status == "connected",
                status=google.status,
                scope="organization",
            )
        )

    meta_ads = _isolated_read(
        db,
        "meta_ads",
        lambda: (
            db.query(MetaAdsConnection)
            .filter(
                MetaAdsConnection.organization_id == organization_id,
                MetaAdsConnection.store_id == store_id,
            )
            .first()
        ),
    )
    if meta_ads is _FAILED:
        integrations.append(
            _degraded_item(
                key="meta_ads",
                provider="meta_ads",
                name="Meta Ads",
                category="ads",
            )
        )
    elif meta_ads:
        integrations.append(
            _item(
                key="meta_ads",
                provider="meta_ads",
                name="Meta Ads",
                category="ads",
                connected=meta_ads.status == "connected",
                status=meta_ads.status,
            )
        )

    payment_rows = _isolated_read(
        db,
        "payments",
        lambda: (
            db.query(PaymentConnection)
            .filter(
                PaymentConnection.organization_id == organization_id,
                PaymentConnection.store_id == store_id,
            )
            .all()
        ),
    )

    try:
        market_providers = get_providers_for_market(
            store.country_code,
            store.currency,
        )
    except Exception:
        logger.exception(
            "Operations payment provider discovery failed",
            extra={
                "country_code": store.country_code,
                "currency": store.currency,
            },
        )
        integrations.append(
            _degraded_item(
                key="payment:unknown",
                provider="payments",
                name="Payments",
                category="payments",
            )
        )
        return integrations

    if payment_rows is _FAILED:
        for provider in market_providers:
            integrations.append(
                _degraded_item(
                    key=f"payment:{provider.provider_code}",
                    provider=provider.provider_code,
                    name=provider.display_name,
                    category="payments",
                    payment_methods=list(provider.supported_payment_methods),
                )
            )
        return integrations

    payment_connections = {
        connection.provider: connection
        for connection in payment_rows
    }

    for provider in market_providers:
        connection = payment_connections.get(provider.provider_code)
        status = connection.status if connection else "disconnected"
        integrations.append(
            _item(
                key=f"payment:{provider.provider_code}",
                provider=provider.provider_code,
                name=provider.display_name,
                category="payments",
                connected=status == "connected",
                status=status,
                payment_methods=list(provider.supported_payment_methods),
            )
        )

    return integrations


def get_dynamic_operations_summary(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict[str, Any]:
    summary = get_operations_summary(
        db=db,
        organization_id=organization_id,
        store_id=store_id,
    )

    integrations_available = True
    try:
        integrations = get_operations_integrations(
            db=db,
            organization_id=organization_id,
            store_id=store_id,
        )
    except Exception:
        logger.exception(
            "Operations integration aggregation failed",
            extra={
                "organization_id": organization_id,
                "store_id": store_id,
            },
        )
        integrations = []
        integrations_available = False

    summary["integrations"] = integrations

    alerts = [
        alert
        for alert in summary.get("alerts", [])
        if alert.get("type") != "no_shopify"
    ]

    degraded = [item for item in integrations if item.get("degraded")]
    if not integrations_available:
        alerts.append(
            {
                "type": "integration_status_degraded",
                "severity": "warning",
                "message": "Integration statuses are temporarily unavailable",
            }
        )
    elif degraded:
        names = list(dict.fromkeys(item["name"] for item in degraded))
        alerts.append(
            {
                "type": "integration_status_degraded",
                "severity": "warning",
                "message": (
                    "Integration status temporarily unavailable for: "
                    + ", ".join(names)
                ),
            }
        )

    has_commerce = any(
        item["category"] == "commerce" and item["connected"]
        for item in integrations
    )
    commerce_degraded = any(
        item["category"] == "commerce" and item.get("degraded")
        for item in integrations
    )
    if integrations_available and not has_commerce and not commerce_degraded:
        alerts.append(
            {
                "type": "no_commerce",
                "severity": "info",
                "message": "No commerce platform connected for this store",
            }
        )
    summary["alerts"] = alerts

    return summary
