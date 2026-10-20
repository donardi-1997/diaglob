"""Shopify-first OAuth: authenticate merchant before DIAGLOB tenant selection.

This flow is deliberately separate from the legacy organization-bound OAuth.
An unbound token is encrypted, expires quickly, and can be claimed once through
a secure HttpOnly browser cookie by an authenticated authorized member.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from ..models import CommerceConnection, Organization, OrganizationMembership, ShopifyPendingInstall, Store
from ..shopify_client import (ShopifyAPIError, ShopifyAuthError, ShopifyGraphQLClient,
                              ShopifyGraphQLError, ShopifyUserError)
from ..shopify_oauth import (
    SHOPIFY_SCOPES, build_authorization_url, exchange_access_token,
    generate_oauth_state, normalize_shop_domain, verify_shopify_hmac,
)
from ..shopify_security import encrypt_shopify_secret
from ..shopify_sync import SHOPIFY_TEST_QUERY
from ..shopify_webhook_subscriptions import ensure_shopify_order_webhooks
from .billing_onboarding import confirm_shopify_install_billing
from .shopify_service import ShopifyConnectionError, ShopifyOAuthError, ShopifyProviderError

COOKIE_NAME = "__Secure-diaglob-shopify-install"
OAUTH_TTL = timedelta(minutes=10)
CLAIM_TTL = timedelta(minutes=20)
logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.getenv("SHOPIFY_OAUTH_FIRST_ENABLED", "false").lower() == "true"


def _canonical_public_shop(shop: str) -> str:
    try:
        canonical = normalize_shop_domain(shop)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ShopifyOAuthError("INVALID_SHOPIFY_DOMAIN") from exc
    if shop.strip().lower() != canonical:
        raise ShopifyOAuthError("INVALID_SHOPIFY_DOMAIN")
    return canonical


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _frontend_install_url() -> str:
    base = os.getenv("FRONTEND_URL", "https://diaglob.tech").strip()
    parts = urlsplit(base)
    if (
        parts.scheme != "https" or parts.hostname != "diaglob.tech"
        or parts.port not in (None, 443) or parts.username or parts.password
        or parts.path not in ("", "/") or parts.query or parts.fragment
    ):
        raise ShopifyOAuthError("UNSAFE_SHOPIFY_FRONTEND_URL")
    return "https://diaglob.tech/shopify/install?authorized=1"


def begin_public_install(db: Session, shop: str) -> str:
    shop = _canonical_public_shop(shop)
    state = generate_oauth_state()
    url = build_authorization_url(shop, state)
    now = datetime.utcnow()
    db.add(ShopifyPendingInstall(
        state=state, shop_domain=shop, expires_at=now + OAUTH_TTL,
        state_used=False, created_at=now,
    ))
    db.commit()
    return url


def pending_state_exists(db: Session, state: str) -> bool:
    if not state:
        return False
    return db.query(ShopifyPendingInstall.id).filter(
        ShopifyPendingInstall.state == state
    ).first() is not None


def finish_public_install(db: Session, params: dict) -> str:
    """Validate signed callback, consume state, verify provider identity, stage token.

    Returns a random browser secret, NOT a Shopify access token.
    """
    if not verify_shopify_hmac(params):
        raise ShopifyOAuthError("Invalid Shopify HMAC")
    state, code = params.get("state", ""), params.get("code", "")
    try:
        shop = _canonical_public_shop(params.get("shop", ""))
    except ShopifyOAuthError as exc:
        raise ShopifyOAuthError("Invalid shop domain") from exc
    if not state or not code:
        raise ShopifyOAuthError("Missing required Shopify OAuth parameters")
    grant = db.query(ShopifyPendingInstall).filter(
        ShopifyPendingInstall.state == state,
        ShopifyPendingInstall.state_used.is_(False),
    ).first()
    if grant is None:
        raise ShopifyOAuthError("Invalid or already used OAuth state")
    if grant.expires_at <= datetime.utcnow() or grant.shop_domain != shop:
        raise ShopifyOAuthError("Invalid or already used OAuth state")

    # Atomic one-use claim, committed BEFORE any external token exchange.
    claimed = db.query(ShopifyPendingInstall).filter(
        ShopifyPendingInstall.id == grant.id,
        ShopifyPendingInstall.state_used.is_(False),
        ShopifyPendingInstall.expires_at > datetime.utcnow(),
        ShopifyPendingInstall.shop_domain == shop,
    ).update({ShopifyPendingInstall.state_used: True}, synchronize_session=False)
    if claimed != 1:
        db.rollback()
        raise ShopifyOAuthError("Invalid or already used OAuth state")
    db.commit()

    try:
        token = exchange_access_token(shop, code)
        identity = ShopifyGraphQLClient(shop_domain=shop, access_token=token).query(
            SHOPIFY_TEST_QUERY
        )
        provider_shop = (identity or {}).get("shop")
        if not isinstance(provider_shop, dict):
            raise ShopifyAPIError("SHOPIFY_SHOP_IDENTITY_UNVERIFIED")
        provider_domain = provider_shop.get("myshopifyDomain")
        if not isinstance(provider_domain, str) or normalize_shop_domain(provider_domain) != shop:
            raise ShopifyAuthError("SHOPIFY_SHOP_IDENTITY_MISMATCH")
        ciphertext = encrypt_shopify_secret(token)
    except (RuntimeError, ShopifyAPIError, ShopifyAuthError, ValueError, TypeError) as exc:
        raise ShopifyProviderError("SHOPIFY_INSTALL_VERIFICATION_FAILED") from exc

    secret = secrets.token_urlsafe(32)
    grant.token_encrypted = ciphertext
    grant.claim_hash = _digest(secret)
    grant.claim_expires_at = datetime.utcnow() + CLAIM_TTL
    db.commit()
    return secret


def _pending_for_cookie(db: Session, secret: str | None):
    if not isinstance(secret, str) or len(secret) < 32 or len(secret) > 255:
        return None
    return db.query(ShopifyPendingInstall).filter(
        ShopifyPendingInstall.claim_hash == _digest(secret),
        ShopifyPendingInstall.claimed_at.is_(None),
        ShopifyPendingInstall.claim_expires_at > datetime.utcnow(),
        ShopifyPendingInstall.token_encrypted.isnot(None),
    ).with_for_update().first()


def pending_install_status(db: Session, secret: str | None) -> dict:
    grant = _pending_for_cookie(db, secret)
    return {
        "pending": grant is not None,
        "shop_domain": grant.shop_domain if grant else None,
    }


def _eligible_shopify_claim_billing(organization: Organization | None) -> bool:
    """Only pending Shopify onboarding or already Shopify-billed tenants.

    The channel is a registration hint, not proof of Shopify billing. A paid
    contract or legacy billing references require manual review before any
    OAuth token can be attached to the organization.
    """
    if organization is None or not organization.active:
        return False
    if any((
        organization.billing_customer_id,
        organization.billing_subscription_id,
        organization.billing_price_id,
    )):
        return False

    provider = (organization.billing_provider or "").strip().lower()
    if provider == "shopify":
        # Existing verified Shopify tenants can reauthorize/reinstall without
        # losing their legitimate plan or creating a new trial.
        return True
    if provider:
        return False

    return (
        organization.billing_onboarding_channel == "shopify_install"
        and (organization.plan or "none").strip().lower() in {"none", "trial"}
        and not organization.pending_plan
    )


def claim_install(
    db: Session, *, secret: str | None,
    membership: OrganizationMembership, store: Store,
) -> dict:
    grant = _pending_for_cookie(db, secret)
    if grant is None:
        raise ShopifyOAuthError("SHOPIFY_INSTALL_GRANT_EXPIRED")
    if grant.grant_method == "managed":
        # A managed token must not be installed close to expiry. A refresh
        # credential is mandatory for background operations.
        if (
            not grant.refresh_token_encrypted
            or not grant.access_token_expires_at
            or grant.access_token_expires_at <= datetime.utcnow() + timedelta(minutes=2)
            or not grant.refresh_token_expires_at
            or grant.refresh_token_expires_at <= datetime.utcnow() + timedelta(minutes=2)
        ):
            raise ShopifyOAuthError("SHOPIFY_MANAGED_INSTALL_EXPIRED")
    if (
        store.organization_id != membership.organization_id
        or store.deleted or not store.active
    ):
        raise ShopifyOAuthError("SHOPIFY_INSTALL_STORE_INVALID")

    organization = db.query(Organization).filter(
        Organization.id == membership.organization_id,
        Organization.active.is_(True),
    ).with_for_update().first()
    existing = db.query(CommerceConnection).filter(
        CommerceConnection.store_id == store.id
    ).first()
    same_store = (
        existing is not None and existing.provider == "shopify"
        and existing.external_store_url == grant.shop_domain
        and existing.organization_id == membership.organization_id
    )
    if store.shopify_domain and store.shopify_domain.strip().lower() != grant.shop_domain:
        raise ShopifyConnectionError("SHOPIFY_STORE_DOMAIN_MISMATCH")
    if existing is not None and not same_store:
        raise ShopifyConnectionError("COMMERCE_ALREADY_CONNECTED")
    conflicting = db.query(CommerceConnection).filter(
        CommerceConnection.provider == "shopify",
        CommerceConnection.external_store_url == grant.shop_domain,
    ).first()
    if conflicting is not None and (existing is None or conflicting.id != existing.id):
        raise ShopifyConnectionError("SHOPIFY_STORE_ALREADY_CONNECTED")

    # A fresh, Shopify-verified managed installation grant can rotate the
    # credentials of the *same* tenant/store connection, including for an
    # existing Paddle/direct-billed organization. This is a credential
    # recovery, not a new Shopify subscription, plan migration, or tenant
    # claim. Never let legacy/unbound OAuth bypass the billing guard.
    same_store_managed_recovery = (
        same_store
        and grant.grant_method == "managed"
        and existing.status in ("connected", "error")
    )
    if not same_store_managed_recovery and not _eligible_shopify_claim_billing(organization):
        raise ShopifyConnectionError("SHOPIFY_BILLING_ORGANIZATION_REQUIRED")

    # A grant is not a subscription. Never assign billing entitlements here.
    now = datetime.utcnow()
    if same_store:
        connection = existing
        connection.access_token_encrypted = grant.token_encrypted
        connection.refresh_token_encrypted = grant.refresh_token_encrypted
        connection.access_token_expires_at = grant.access_token_expires_at
        connection.refresh_token_expires_at = grant.refresh_token_expires_at
        connection.status = "connected"
        connection.last_error = None
        connection.updated_at = now
        connection.connected_at = now
        connection.scopes = SHOPIFY_SCOPES
    else:
        connection = CommerceConnection(
            organization_id=membership.organization_id, store_id=store.id,
            provider="shopify", external_store_url=grant.shop_domain,
            access_token_encrypted=grant.token_encrypted,
            refresh_token_encrypted=grant.refresh_token_encrypted,
            access_token_expires_at=grant.access_token_expires_at,
            refresh_token_expires_at=grant.refresh_token_expires_at,
            scopes=SHOPIFY_SCOPES, status="connected", connected_at=now,
        )
        db.add(connection)
    # Exactly-once claim; do not retain an unused token after binding.
    updated = db.query(ShopifyPendingInstall).filter(
        ShopifyPendingInstall.id == grant.id,
        ShopifyPendingInstall.claimed_at.is_(None),
        ShopifyPendingInstall.claim_expires_at > now,
    ).update({
        ShopifyPendingInstall.claimed_at: now,
        ShopifyPendingInstall.claim_hash: None,
        ShopifyPendingInstall.token_encrypted: None,
        ShopifyPendingInstall.refresh_token_encrypted: None,
    }, synchronize_session=False)
    if updated != 1:
        db.rollback()
        raise ShopifyOAuthError("SHOPIFY_INSTALL_GRANT_EXPIRED")
    db.commit()
    if not same_store:
        # Only brand-new, eligibility-checked Shopify-onboarded installs can
        # update billing provenance. Reauth of an existing store MUST NOT.
        confirm_shopify_install_billing(
            db, organization_id=membership.organization_id, connection_id=connection.id
        )

    # Match legacy OAuth: register order lifecycle and uninstall hooks after
    # binding a verified shop. An API failure must not lose the saved grant;
    # merchant administrators can retry the existing ensure-webhooks endpoint.
    webhooks_ready = False
    try:
        ensure_shopify_order_webhooks(connection)
        connection.last_error = None
        db.commit()
        webhooks_ready = True
    except (ShopifyAPIError, ShopifyGraphQLError, ShopifyUserError) as exc:
        connection.last_error = "WEBHOOK_SUBSCRIPTION_FAILED: " + str(exc)[:400]
        db.commit()
        logger.warning(
            "Shopify webhook registration failed for store %s: %s",
            store.id,
            exc,
        )
    return {
        "connected": True,
        "store_id": store.id,
        "shop_domain": grant.shop_domain,
        "webhooks_ready": webhooks_ready,
    }
