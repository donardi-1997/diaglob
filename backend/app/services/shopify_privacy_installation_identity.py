"""Signed Shopify shop identity history for privacy requests after uninstall.

No customer selectors, merchant tokens, export data or destructive actions.
The HTTP routes MUST verify Shopify's raw-body HMAC before using these helpers.
The historical mapping is useful to triage a request, not independent proof
of authority to export/delete data or of legal retention clearance.
"""
from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import CommerceConnection, ShopifyPrivacyShopIdentity
from ..shopify_oauth import normalize_shop_domain


class ShopifyPrivacyShopIdentityError(ValueError):
    """Non-PII reason code for ambiguous or conflicting signed shop identity."""


@dataclass(frozen=True)
class PrivacyShopIdentityBinding:
    organization_id: int
    store_id: int
    recovered_after_uninstall: bool


def _signed_identity(shop_id: str, shop_domain: str) -> tuple[str, str]:
    if (
        not isinstance(shop_id, str)
        or not shop_id.isascii()
        or not shop_id.isdecimal()
        or not 1 <= len(shop_id) <= 80
        or int(shop_id) <= 0
    ):
        raise ShopifyPrivacyShopIdentityError("INVALID_SIGNED_SHOP_ID")
    try:
        canonical = normalize_shop_domain(shop_domain)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ShopifyPrivacyShopIdentityError("INVALID_SIGNED_SHOP_DOMAIN") from exc
    return str(int(shop_id)), canonical


def _historical_mapping(
    db: Session, shop_id: str, domain: str,
) -> ShopifyPrivacyShopIdentity | None:
    # Examine collisions across both identifiers; DO NOT fall back to a
    # domain-only match when a shop ID differs (or vice versa).
    identities = db.query(ShopifyPrivacyShopIdentity).filter(
        (ShopifyPrivacyShopIdentity.shop_id == shop_id)
        | (ShopifyPrivacyShopIdentity.shop_domain == domain),
    ).limit(3).all()
    if len(identities) > 1:
        raise ShopifyPrivacyShopIdentityError("SIGNED_SHOP_IDENTITY_CONFLICT")
    if not identities:
        return None
    identity = identities[0]
    if identity.shop_id != shop_id or identity.shop_domain != domain:
        raise ShopifyPrivacyShopIdentityError("SIGNED_SHOP_IDENTITY_CONFLICT")
    return identity


def bind_signed_shopify_privacy_identity(
    db: Session, *, shop_id: str, shop_domain: str,
    connection: CommerceConnection | None,
) -> PrivacyShopIdentityBinding | None:
    """Return exact historic tenant/store after uninstall; stage new link only
    when a currently-connected Shopify integration is already verified.

    A new row is flushed by the caller's SAME transaction as the HMAC-audited
    receipt. Never create a tenant link from an unbound incoming webhook.
    """
    shop_id, domain = _signed_identity(shop_id, shop_domain)
    historical = _historical_mapping(db, shop_id, domain)
    if connection is not None:
        if (
            connection.provider != "shopify"
            or connection.status != "connected"
            or connection.external_store_url != domain
            or connection.organization_id is None
            or connection.store_id is None
        ):
            raise ShopifyPrivacyShopIdentityError("SHOPIFY_CONNECTION_IDENTITY_INVALID")
        organization_id, store_id = connection.organization_id, connection.store_id
        if historical is not None and (
            historical.organization_id != organization_id
            or historical.store_id != store_id
        ):
            raise ShopifyPrivacyShopIdentityError("SIGNED_SHOP_TENANT_REBOUND")
        if historical is None:
            now = datetime.utcnow()
            historical = ShopifyPrivacyShopIdentity(
                shop_id=shop_id, shop_domain=domain,
                organization_id=organization_id, store_id=store_id,
                provenance="hmac_compliance", first_seen_at=now,
                last_seen_at=now,
            )
            db.add(historical)
        else:
            historical.last_seen_at = datetime.utcnow()
        return PrivacyShopIdentityBinding(
            organization_id=organization_id, store_id=store_id,
            recovered_after_uninstall=False,
        )
    if historical is None:
        return None
    return PrivacyShopIdentityBinding(
        organization_id=historical.organization_id,
        store_id=historical.store_id,
        recovered_after_uninstall=True,
    )


def record_signed_shopify_uninstall_identity(
    db: Session, *, shop_id: str, shop_domain: str,
    connection: CommerceConnection,
    observed_at: datetime,
) -> None:
    """Stage signed uninstall identity in the revocation transaction.

    The signed app/uninstalled webhook must already have been validated by
    the route, including matching shop ID/domain from its payload. A stale
    uninstall must be rejected by the caller BEFORE invoking this method.
    """
    shop_id, domain = _signed_identity(shop_id, shop_domain)
    if (
        connection.provider != "shopify"
        or connection.external_store_url != domain
        or connection.organization_id is None
        or connection.store_id is None
    ):
        raise ShopifyPrivacyShopIdentityError("SHOPIFY_CONNECTION_IDENTITY_INVALID")
    existing = _historical_mapping(db, shop_id, domain)
    if existing is not None and (
        existing.organization_id != connection.organization_id
        or existing.store_id != connection.store_id
    ):
        raise ShopifyPrivacyShopIdentityError("SIGNED_SHOP_TENANT_REBOUND")
    if existing is None:
        db.add(ShopifyPrivacyShopIdentity(
            shop_id=shop_id, shop_domain=domain,
            organization_id=connection.organization_id,
            store_id=connection.store_id, provenance="hmac_uninstall",
            first_seen_at=observed_at, last_seen_at=observed_at,
            uninstalled_at=observed_at,
        ))
    else:
        existing.last_seen_at = observed_at
        existing.uninstalled_at = observed_at
