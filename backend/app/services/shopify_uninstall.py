"""Shopify app/uninstalled lifecycle: signed, scoped and replay-resistant.

Do not delete any merchant/customer data or settle billing from this webhook.
Shopify privacy webhooks and reviewed retention requirements remain independent.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..model_domains.fulfillment_automation import AutoFulfillmentJob
from ..models import (
    CommerceConnection, Organization, ShopifyOAuthState,
    ShopifyEmbeddedIdentityBinding, ShopifyEmbeddedLinkTicket,
)
from ..shopify_oauth import normalize_shop_domain
from .shopify_privacy_installation_identity import (
    ShopifyPrivacyShopIdentityError,
    record_signed_shopify_uninstall_identity,
)


class ShopifyUninstallError(ValueError):
    """Malformed/untrusted uninstall request; nothing must be changed."""


def _triggered_at(value: str | None, *, now: datetime) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ShopifyUninstallError("SHOPIFY_UNINSTALL_TIMESTAMP_REQUIRED")
    try:
        trigger = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShopifyUninstallError("SHOPIFY_UNINSTALL_TIMESTAMP_INVALID") from exc
    if trigger.tzinfo is None or trigger.utcoffset() is None:
        raise ShopifyUninstallError("SHOPIFY_UNINSTALL_TIMESTAMP_INVALID")
    utc_trigger = trigger.astimezone(timezone.utc).replace(tzinfo=None)
    if utc_trigger > now + timedelta(minutes=5):
        raise ShopifyUninstallError("SHOPIFY_UNINSTALL_TIMESTAMP_INVALID")
    return utc_trigger


def process_shopify_uninstall(
    db: Session,
    *,
    topic: str,
    header_shop_domain: str | None,
    triggered_at: str | None,
    payload: dict,
) -> dict:
    """Invalidate exactly the Shopify installation addressed by the webhook.

    The HTTP route verifies Shopify's HMAC on the ORIGINAL body before calling
    this function. Event time protects a newly reinstalled connection against
    delayed events from the previous installation.
    """
    if topic != "app/uninstalled" or not isinstance(payload, dict):
        raise ShopifyUninstallError("INVALID_SHOPIFY_UNINSTALL")
    try:
        domain = normalize_shop_domain(header_shop_domain or "")
        # Header fields are not part of the raw-body HMAC. Require the
        # canonical myshopify domain INSIDE the signed payload as well, so
        # replaying another shop's delivery with a changed header cannot
        # revoke a different tenant. Missing identity needs manual review.
        payload_domain = payload.get("myshopify_domain")
        if (
            not isinstance(payload_domain, str)
            or not payload_domain
            or normalize_shop_domain(payload_domain) != domain
        ):
            raise ShopifyUninstallError("SHOPIFY_UNINSTALL_DOMAIN_MISMATCH")
    except (ValueError, AttributeError, TypeError) as exc:
        raise ShopifyUninstallError("SHOPIFY_UNINSTALL_DOMAIN_MISMATCH") from exc

    shop_id = payload.get("id")
    if type(shop_id) not in (str, int) or not str(shop_id).isdigit() or int(shop_id) <= 0:
        raise ShopifyUninstallError("SHOPIFY_UNINSTALL_ID_REQUIRED")

    now = datetime.utcnow()
    trigger = _triggered_at(triggered_at, now=now)
    connections = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider == "shopify",
            CommerceConnection.external_store_url == domain,
        )
        .limit(2)
        .all()
    )
    if not connections:
        return {"ok": True, "action": "unknown_shop"}
    if len(connections) != 1:
        raise ShopifyUninstallError("SHOPIFY_UNINSTALL_AMBIGUOUS_SHOP")
    connection = connections[0]

    if connection.status == "revoked":
        return {"ok": True, "action": "already_revoked"}
    if connection.status not in {"connected", "error"}:
        # A previously disconnected store has no current live installation.
        # An API-error connection may still hold a token and must be revoked.
        return {"ok": True, "action": "not_connected"}
    if trigger < connection.connected_at:
        return {"ok": True, "action": "stale_uninstall"}

    # Preserve the authenticated shop ID -> tenant/store relationship BEFORE
    # revoking tokens. This ledger has no store FK, so future Shopify GDPR
    # callbacks can be matched to an original shop after uninstall.
    try:
        record_signed_shopify_uninstall_identity(
            db, shop_id=str(shop_id), shop_domain=domain,
            connection=connection, observed_at=now,
        )
    except ShopifyPrivacyShopIdentityError as exc:
        db.rollback()
        raise ShopifyUninstallError(str(exc)) from exc

    # All mutations remain in a single DB transaction. Do not touch Shopify
    # privacy receipts, order history, global customers, invoices or billing.
    # Invalidate Shopify staff links and outstanding codes on signed uninstall.
    # Reinstall must require a fresh explicit pairing, even if a connection
    # record happens to be reused without changing its connected_at value.
    db.query(ShopifyEmbeddedIdentityBinding).filter(
        ShopifyEmbeddedIdentityBinding.connection_id == connection.id,
        ShopifyEmbeddedIdentityBinding.revoked_at.is_(None),
    ).update({ShopifyEmbeddedIdentityBinding.revoked_at: now}, synchronize_session=False)
    db.query(ShopifyEmbeddedLinkTicket).filter(
        ShopifyEmbeddedLinkTicket.connection_id == connection.id,
        ShopifyEmbeddedLinkTicket.consumed_at.is_(None),
    ).update({ShopifyEmbeddedLinkTicket.consumed_at: now}, synchronize_session=False)

    connection.status = "revoked"
    connection.access_token_encrypted = None
    connection.refresh_token_encrypted = None
    connection.api_key_encrypted = None
    connection.api_secret_encrypted = None
    connection.scopes = ""
    connection.last_error = "SHOPIFY_APP_UNINSTALLED"
    connection.updated_at = now

    # A signed uninstall invalidates Shopify-billed paid access immediately.
    # This does not cancel billing at Shopify or affect Paddle organizations.
    billing_org = (
        db.query(Organization)
        .filter(Organization.id == connection.organization_id)
        .with_for_update()
        .first()
    )
    if (
        billing_org is not None
        and billing_org.billing_provider == "shopify"
        and billing_org.plan in {"starter", "growth", "pro", "scale"}
    ):
        billing_org.subscription_status = "inactive"

    (
        db.query(ShopifyOAuthState)
        .filter(
            ShopifyOAuthState.store_id == connection.store_id,
            ShopifyOAuthState.organization_id == connection.organization_id,
            ShopifyOAuthState.used.is_(False),
        )
        .update({ShopifyOAuthState.used: True}, synchronize_session=False)
    )
    (
        db.query(AutoFulfillmentJob)
        .filter(
            AutoFulfillmentJob.organization_id == connection.organization_id,
            AutoFulfillmentJob.store_id == connection.store_id,
            AutoFulfillmentJob.status.in_(["pending", "retry"]),
        )
        .update(
            {
                AutoFulfillmentJob.status: "waiting_shopify_reconnect",
                AutoFulfillmentJob.last_error: "SHOPIFY_APP_UNINSTALLED",
                AutoFulfillmentJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    return {"ok": True, "action": "revoked"}
