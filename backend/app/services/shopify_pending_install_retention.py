"""Retention for unclaimed Shopify OAuth grants that never reached a tenant.

A ``ShopifyPendingInstall`` holds encrypted access/refresh tokens for an
installation that has not yet been claimed by a DIAGLOB organization. Once the
grant expires, or once Shopify delivers a signed ``app/uninstalled`` for that
shop, the grant can never be claimed and its tokens must not remain at rest.

This module never decrypts a token, never logs a shop domain, and never touches
claimed grants, live connections, or privacy receipts.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection,
    ShopifyPendingInstall,
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
)
from ..shopify_oauth import normalize_shop_domain

DEFAULT_EXPIRED_GRACE = timedelta(hours=24)
PURGE_AUDIT_EVENT = "pending_install_purged"
PURGE_ACTOR = "internal_privacy_operator"


class ShopifyPendingInstallRetentionError(ValueError):
    """Purge refused: the grant may still belong to a live installation."""


def _utc_naive(value: datetime | None) -> datetime:
    reference = value if value is not None else datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        return reference
    return reference.astimezone(timezone.utc).replace(tzinfo=None)


def _domain(value: str) -> str:
    try:
        domain = normalize_shop_domain(value or "")
    except (ValueError, AttributeError, TypeError) as exc:
        raise ShopifyPendingInstallRetentionError("SHOP_DOMAIN_INVALID") from exc
    if not domain:
        raise ShopifyPendingInstallRetentionError("SHOP_DOMAIN_REQUIRED")
    return domain


def _has_live_connection(db: Session, domain: str) -> bool:
    return db.query(CommerceConnection.id).filter(
        CommerceConnection.provider == "shopify",
        func.lower(CommerceConnection.external_store_url) == domain,
        CommerceConnection.status == "connected",
        CommerceConnection.access_token_encrypted.isnot(None),
    ).first() is not None


def _pending_query(
    db: Session,
    domain: str,
    *,
    not_after: datetime | None,
    only_expired: bool,
    reference: datetime,
):
    query = db.query(ShopifyPendingInstall).filter(
        func.lower(ShopifyPendingInstall.shop_domain) == domain,
        ShopifyPendingInstall.claimed_at.is_(None),
    )
    if not_after is not None:
        # Signed uninstall: anything created before the event belongs to the
        # installation that was just removed. A later reinstall is untouched.
        query = query.filter(
            ShopifyPendingInstall.created_at <= _utc_naive(not_after),
        )
    elif only_expired:
        query = query.filter(
            ShopifyPendingInstall.expires_at <= reference,
        )
    return query


def count_unclaimed_pending_installs(
    db: Session,
    *,
    shop_domain: str,
    not_after: datetime | None = None,
    only_expired: bool = True,
    now: datetime | None = None,
) -> int:
    domain = _domain(shop_domain)
    reference = _utc_naive(now)
    return int(
        _pending_query(
            db, domain, not_after=not_after,
            only_expired=only_expired, reference=reference,
        ).count()
    )


def purge_unclaimed_pending_installs(
    db: Session,
    *,
    shop_domain: str,
    not_after: datetime | None = None,
    only_expired: bool = True,
    now: datetime | None = None,
) -> int:
    """Delete unclaimed grants for one domain. Does not commit by itself."""
    domain = _domain(shop_domain)
    reference = _utc_naive(now)
    ids = [
        row[0]
        for row in _pending_query(
            db, domain, not_after=not_after,
            only_expired=only_expired, reference=reference,
        ).with_entities(ShopifyPendingInstall.id).all()
    ]
    if not ids:
        return 0
    return int(
        db.query(ShopifyPendingInstall)
        .filter(
            ShopifyPendingInstall.id.in_(ids),
            ShopifyPendingInstall.claimed_at.is_(None),
        )
        .delete(synchronize_session=False)
    )


def _receipt(db: Session, request_id: str, *, lock: bool = False):
    query = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    )
    if lock:
        query = query.with_for_update()
    receipt = query.first()
    if receipt is None:
        raise ShopifyPendingInstallRetentionError("PRIVACY_RECEIPT_NOT_FOUND")
    return receipt


def _validate_receipt_for_purge(db: Session, receipt) -> str:
    if receipt.topic != "shop/redact":
        raise ShopifyPendingInstallRetentionError("NOT_A_SHOP_REDACT_RECEIPT")
    if receipt.organization_id is not None or receipt.store_id is not None:
        # A resolved tenant has a live-ish connection and a different flow.
        raise ShopifyPendingInstallRetentionError("TENANT_ALREADY_RESOLVED")
    signed = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == receipt.request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first() is not None
    if not signed:
        raise ShopifyPendingInstallRetentionError("SIGNED_INTAKE_EVIDENCE_MISSING")
    domain = _domain(receipt.shop_domain)
    if _has_live_connection(db, domain):
        # Never invalidate a grant that may belong to the current install.
        raise ShopifyPendingInstallRetentionError("LIVE_SHOPIFY_CONNECTION_PRESENT")
    return domain


def preview_pending_installs_for_privacy_receipt(
    db: Session, *, request_id: str, now: datetime | None = None,
) -> dict:
    """Read-only plan. The shop domain is deliberately not returned."""
    receipt = _receipt(db, request_id)
    domain = _validate_receipt_for_purge(db, receipt)
    return {
        "topic": receipt.topic,
        "receipt_status": receipt.status,
        "pending_unclaimed": count_unclaimed_pending_installs(
            db, shop_domain=domain, only_expired=False, now=now,
        ),
        # Only expired grants are purged by default: an unexpired grant can
        # belong to a legitimate reinstall that happened after the old
        # installation was removed. It is reported, not silently deleted.
        "pending_purgeable": count_unclaimed_pending_installs(
            db, shop_domain=domain, only_expired=True, now=now,
        ),
        "purge_eligible": True,
    }


def purge_pending_installs_for_privacy_receipt(
    db: Session,
    *,
    request_id: str,
    include_unexpired: bool = False,
    now: datetime | None = None,
    commit: bool = False,
) -> dict:
    """Purge unclaimed grants for one signed shop/redact receipt.

    Only expired grants are removed by default. An unexpired grant can belong
    to a legitimate reinstall that happened after the old installation was
    removed, so it is reported but not deleted. The receipt, its work items and
    its audit trail are preserved.
    """
    receipt = _receipt(db, request_id, lock=True)
    domain = _validate_receipt_for_purge(db, receipt)
    before = count_unclaimed_pending_installs(
        db, shop_domain=domain, only_expired=False, now=now,
    )
    purged = purge_unclaimed_pending_installs(
        db,
        shop_domain=domain,
        only_expired=not include_unexpired,
        now=now,
    )
    if purged:
        db.add(ShopifyPrivacyAuditEvent(
            request_id=receipt.request_id,
            event_type=PURGE_AUDIT_EVENT,
            from_status=receipt.status,
            to_status=receipt.status,
            reason_code="shop_redact_unclaimed_oauth_grants_purged",
            actor_type=PURGE_ACTOR,
            created_at=_utc_naive(now),
        ))
    if commit:
        db.commit()
    return {
        "pending_before": before,
        "pending_purged": purged,
        "pending_after": count_unclaimed_pending_installs(
            db, shop_domain=domain, only_expired=False, now=now,
        ),
    }


def preview_expired_unclaimed_pending_installs(
    db: Session,
    *,
    now: datetime | None = None,
    grace: timedelta = DEFAULT_EXPIRED_GRACE,
) -> dict:
    reference = _utc_naive(now)
    cutoff = reference - grace
    total = int(
        db.query(ShopifyPendingInstall)
        .filter(
            ShopifyPendingInstall.claimed_at.is_(None),
            ShopifyPendingInstall.expires_at <= cutoff,
        )
        .count()
    )
    return {
        "expired_before": cutoff.isoformat(timespec="seconds"),
        "pending_purged_candidate": total,
    }


def purge_expired_unclaimed_pending_installs(
    db: Session,
    *,
    now: datetime | None = None,
    grace: timedelta = DEFAULT_EXPIRED_GRACE,
    commit: bool = False,
) -> dict:
    """Scheduled cleanup; safe to run repeatedly and safe to run while live."""
    reference = _utc_naive(now)
    cutoff = reference - grace
    ids = [
        row[0]
        for row in db.query(ShopifyPendingInstall.id)
        .filter(
            ShopifyPendingInstall.claimed_at.is_(None),
            ShopifyPendingInstall.expires_at <= cutoff,
        )
        .all()
    ]
    purged = 0
    if ids:
        purged = int(
            db.query(ShopifyPendingInstall)
            .filter(
                ShopifyPendingInstall.id.in_(ids),
                ShopifyPendingInstall.claimed_at.is_(None),
            )
            .delete(synchronize_session=False)
        )
    if commit:
        db.commit()
    return {
        "expired_before": cutoff.isoformat(timespec="seconds"),
        "pending_purged": purged,
    }
