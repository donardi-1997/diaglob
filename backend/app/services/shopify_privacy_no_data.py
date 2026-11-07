"""Terminal determination for signed Shopify receipts with no tenant data.

A signed ``shop/redact`` receipt can arrive for a shop that completed OAuth but
never selected a DIAGLOB tenant. There is no Store, no CommerceConnection and
no ``ShopifyPrivacyShopIdentity`` for that domain, so there are no tenant-scoped
records attributable to the shop.

This module records that determination explicitly. It never fabricates a
verified shop identity, never sets ``completed_at``, and never claims legal
fulfillment. The receipt and its audit trail remain subject to the reviewed
retention schedule.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from ..models import (
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    ShopifyPrivacyWorkItem,
)
from ..shopify_oauth import normalize_shop_domain
from ..shopify_privacy_operational_audit import (
    REQUIRED_WORK_ITEMS_PER_RECEIPT,
)

NO_DATA_STATUS = "no_data_attributable"
NO_DATA_EVENT = "no_data_attributable_determined"
NO_DATA_REASON = "NO_TENANT_DATA_ATTRIBUTABLE"
NO_DATA_ACTOR = "internal_privacy_operator"

_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")
# The receipt, its audit trail and its task queue are the determination
# itself. A shop identity row is NOT excluded: its presence proves that a
# tenant existed and the case must follow the normal erasure path.
_EXCLUDED_TABLES = {
    "shopify_privacy_requests",
    "shopify_privacy_audit_events",
    "shopify_privacy_work_items",
}
_DIRECT_COLUMNS = ("shop_domain", "shopify_domain", "external_store_url")
_COMPLETION_STATES = {"completed", "fulfilled", "delivered", "deleted", "erased"}


class ShopifyPrivacyNoDataError(ValueError):
    """The no-data determination is not supported by complete evidence."""


def _utc_naive(value: datetime | None) -> datetime:
    reference = value if value is not None else datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        return reference
    return reference.astimezone(timezone.utc).replace(tzinfo=None)


def sweep_direct_shop_references(
    db: Session, *, shop_domain: str, shop_id: str,
) -> dict[str, int]:
    """Count rows that still reference this shop through a direct column.

    Tenant-scoped rows without a shop column cannot be reached because the
    receipt has no organization/store and no Store or CommerceConnection
    exists for the domain. This sweep covers direct identifiers only.
    """
    domain = normalize_shop_domain(shop_domain or "")
    if not domain:
        raise ShopifyPrivacyNoDataError("SHOP_DOMAIN_REQUIRED")

    found: dict[str, int] = {}
    inspector = inspect(db.get_bind())
    for table in inspector.get_table_names():
        if table in _EXCLUDED_TABLES:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        for column in _DIRECT_COLUMNS:
            if column not in columns:
                continue
            count = db.execute(
                text(
                    f'SELECT COUNT(*) FROM "{table}" '
                    f'WHERE lower("{column}") = :domain'
                ),
                {"domain": domain},
            ).scalar()
            if count:
                found[f"{table}.{column}"] = int(count)
        if table.startswith("shopify_") and "shop_id" in columns:
            count = db.execute(
                text(f'SELECT COUNT(*) FROM "{table}" WHERE "shop_id" = :shop_id'),
                {"shop_id": str(shop_id)},
            ).scalar()
            if count:
                found[f"{table}.shop_id"] = int(count)
    return found


def _signed_intake(db: Session, request_id: str) -> bool:
    return db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first() is not None


def _work_items(db: Session, request_id: str) -> list[ShopifyPrivacyWorkItem]:
    return db.query(ShopifyPrivacyWorkItem).filter(
        ShopifyPrivacyWorkItem.request_id == request_id,
    ).all()


def assess_no_data_attributable(
    db: Session, *, request_id: str,
) -> dict | None:
    """Read-only eligibility report. Contains no shop domain or subject data."""
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ShopifyPrivacyNoDataError("INVALID_PRIVACY_REQUEST_ID")
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).first()
    if receipt is None:
        return None

    signed = _signed_intake(db, request_id)
    items = _work_items(db, request_id)
    references = sweep_direct_shop_references(
        db, shop_domain=receipt.shop_domain, shop_id=receipt.shop_id,
    )

    blocking: list[str] = []
    if receipt.topic != "shop/redact":
        blocking.append("TOPIC_NOT_SHOP_REDACT")
    if receipt.organization_id is not None or receipt.store_id is not None:
        blocking.append("TENANT_ALREADY_RESOLVED")
    if not signed:
        blocking.append("SIGNED_INTAKE_EVIDENCE_MISSING")
    if receipt.completed_at is not None or receipt.status == "completed":
        blocking.append("HISTORICAL_COMPLETION_REQUIRES_REVIEW")
    if references:
        blocking.append("SHOP_DATA_PRESENT")
    if len(items) != REQUIRED_WORK_ITEMS_PER_RECEIPT:
        blocking.append("INCOMPLETE_PRIVACY_WORK_ITEM_SET")
    if any(item.status in _COMPLETION_STATES for item in items):
        blocking.append("UNVERIFIED_PRIVACY_COMPLETION")

    return {
        "topic": receipt.topic,
        "receipt_status": receipt.status,
        "tenant_resolved": (
            receipt.organization_id is not None
            or receipt.store_id is not None
        ),
        "signed_intake_verified": signed,
        "direct_reference_counts": references,
        "work_item_count": len(items),
        "eligible": not blocking,
        "blocking_codes": blocking,
        "already_determined": receipt.status == NO_DATA_STATUS,
        "pii_free": True,
    }


def close_shopify_privacy_case_as_no_data(
    db: Session,
    *,
    request_id: str,
    now: datetime | None = None,
    commit: bool = False,
) -> dict | None:
    """Record an evidence-backed no-data determination for one receipt.

    Requires: signed shop/redact receipt, no organization/store, a complete
    work-item set, and zero direct shop references in the sweep. The task
    states become ``not_applicable``, never ``verified``. ``completed_at`` is
    left null because no fulfillment occurred.
    """
    assessment = assess_no_data_attributable(db, request_id=request_id)
    if assessment is None:
        return None
    if assessment["already_determined"]:
        return {**assessment, "determined_now": False}
    if not assessment["eligible"]:
        raise ShopifyPrivacyNoDataError(assessment["blocking_codes"][0])

    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).with_for_update().first()
    if receipt is None:
        return None
    if receipt.status == NO_DATA_STATUS:
        return {**assessment, "determined_now": False}

    reference = _utc_naive(now)
    items = _work_items(db, request_id)
    for item in items:
        item.status = "not_applicable"
        item.blocker_code = None
        item.updated_at = reference

    previous_status = receipt.status
    receipt.status = NO_DATA_STATUS
    receipt.last_error_code = None
    receipt.updated_at = reference
    db.add(ShopifyPrivacyAuditEvent(
        request_id=receipt.request_id,
        event_type=NO_DATA_EVENT,
        from_status=previous_status,
        to_status=NO_DATA_STATUS,
        reason_code=NO_DATA_REASON,
        actor_type=NO_DATA_ACTOR,
        created_at=reference,
    ))
    if commit:
        db.commit()
    return {
        **assessment,
        "receipt_status": NO_DATA_STATUS,
        "determined_now": True,
    }
