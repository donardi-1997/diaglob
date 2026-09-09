"""Dynamic integration summary for the Operations Center."""

from __future__ import annotations

from typing import Any

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
from ..payments.registry import get_providers_for_market


def _display_provider(provider: str) -> str:
    labels = {
        "shopify": "Shopify",
        "nuvemshop": "Nuvemshop",
        "dropi": "Dropi",
        "meta_ads": "Meta Ads",
        "whatsapp": "WhatsApp",
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


def get_operations_integrations(
    db: Session,
    organization_id: int,
    store_id: int,
) -> list[dict[str, Any]]:
    """Return real integration state for one store.

    Store-scoped integrations are tenant-filtered. Google is intentionally
    organization-scoped because the existing OAuth connection is shared by
    the organization's knowledge sources. Payment availability comes from
    the payment-provider registry for the store market.
    """
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

    whatsapp = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.organization_id == organization_id,
            WhatsAppConnection.store_id == store_id,
        )
        .first()
    )
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

    commerce = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == store_id,
        )
        .first()
    )
    if commerce:
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
        # Backward-compatible visibility for stores created before
        # CommerceConnection became the canonical integration record.
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

    dropi = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.organization_id == organization_id,
            DropiConnection.store_id == store_id,
        )
        .first()
    )
    if dropi:
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

    google = (
        db.query(GoogleConnection)
        .filter(GoogleConnection.organization_id == organization_id)
        .first()
    )
    if google:
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

    meta_ads = (
        db.query(MetaAdsConnection)
        .filter(
            MetaAdsConnection.organization_id == organization_id,
            MetaAdsConnection.store_id == store_id,
        )
        .first()
    )
    if meta_ads:
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

    payment_connections = {
        connection.provider: connection
        for connection in (
            db.query(PaymentConnection)
            .filter(
                PaymentConnection.organization_id == organization_id,
                PaymentConnection.store_id == store_id,
            )
            .all()
        )
    }

    for provider in get_providers_for_market(
        store.country_code,
        store.currency,
    ):
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
