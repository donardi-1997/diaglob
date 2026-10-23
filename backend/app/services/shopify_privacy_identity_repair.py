"""Operator-controlled, evidence-bound recovery for historical GDPR shop identity.

Only mutates the tenant/store binding of an HMAC-audited receipt, never
customer data or merchant orders. No domain-only guesses are allowed.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Session

from ..models import (
    ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest,
    ShopifyPrivacyShopIdentity, ShopifyPrivacyWorkItem, Store,
)
from ..shopify_oauth import normalize_shop_domain
from .shopify_privacy_installation_identity import (
    ShopifyPrivacyShopIdentityError, bind_signed_shopify_privacy_identity,
)

_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_HISTORY = frozenset({"hmac_uninstall", "hmac_compliance"})
_DENIED_ERROR_CODES = frozenset({
    "SIGNED_SHOP_IDENTITY_CONFLICT",
    "SIGNED_SHOP_TENANT_REBOUND",
    "SHOPIFY_CONNECTION_IDENTITY_INVALID",
})


class ShopifyPrivacyIdentityRepairError(ValueError):
    """Safe error codes only: never include shop IDs/domains or selectors."""


def repair_signed_shopify_privacy_receipt_identity(
    db: Session, *, request_id: str,
) -> dict:
    """Bind ONLY to the exact pre-existing, signed Shopify identity history.

    Requires authenticated internal operator gate at the caller. The signed
    historical record must predate the GDPR receipt. A Shopify shop/redact also
    requires signed uninstall evidence. No automatic deletion follows.
    """
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ShopifyPrivacyIdentityRepairError("INVALID_PRIVACY_REQUEST_ID")
    receipt = (
        db.query(ShopifyPrivacyRequest)
        .filter(ShopifyPrivacyRequest.request_id == request_id)
        .with_for_update()
        .first()
    )
    if receipt is None:
        raise ShopifyPrivacyIdentityRepairError("PRIVACY_REQUEST_NOT_FOUND")
    if receipt.status == "completed" or receipt.completed_at is not None:
        raise ShopifyPrivacyIdentityRepairError("HISTORICAL_COMPLETION_REQUIRES_REVIEW")
    if receipt.last_error_code in _DENIED_ERROR_CODES:
        raise ShopifyPrivacyIdentityRepairError("SIGNED_SHOP_HISTORY_CONFLICT")

    signed = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first()
    if signed is None:
        raise ShopifyPrivacyIdentityRepairError("SIGNED_INTAKE_EVIDENCE_MISSING")

    prepared = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "processing_prepared",
        ShopifyPrivacyAuditEvent.actor_type == "internal_privacy_processor",
    ).first()
    work_items = db.query(ShopifyPrivacyWorkItem.id).filter(
        ShopifyPrivacyWorkItem.request_id == request_id,
    ).count()
    if prepared is None or work_items != 10:
        raise ShopifyPrivacyIdentityRepairError("PRIVACY_PROCESSING_QUEUE_UNVERIFIED")

    if (receipt.organization_id is None) != (receipt.store_id is None):
        raise ShopifyPrivacyIdentityRepairError("PARTIAL_TENANT_BINDING_UNSAFE")

    try:
        candidate = bind_signed_shopify_privacy_identity(
            db, shop_id=receipt.shop_id, shop_domain=receipt.shop_domain,
            connection=None,
        )
        domain = normalize_shop_domain(receipt.shop_domain)
    except (ShopifyPrivacyShopIdentityError, ValueError, TypeError) as exc:
        raise ShopifyPrivacyIdentityRepairError("SIGNED_SHOP_HISTORY_UNVERIFIED") from exc
    if candidate is None:
        raise ShopifyPrivacyIdentityRepairError("SIGNED_SHOP_HISTORY_MISSING")

    history = db.query(ShopifyPrivacyShopIdentity).filter(
        ShopifyPrivacyShopIdentity.shop_id == str(int(receipt.shop_id)),
        ShopifyPrivacyShopIdentity.shop_domain == domain,
        ShopifyPrivacyShopIdentity.organization_id == candidate.organization_id,
        ShopifyPrivacyShopIdentity.store_id == candidate.store_id,
    ).one_or_none()
    if (
        history is None
        or history.provenance not in _ALLOWED_HISTORY
        or history.first_seen_at > receipt.created_at
        or (
            receipt.topic == "shop/redact"
            and (
                history.uninstalled_at is None
                or history.uninstalled_at > receipt.created_at
            )
        )
    ):
        raise ShopifyPrivacyIdentityRepairError("SIGNED_SHOP_HISTORY_UNVERIFIED")

    # The existing store must still belong to the historical tenant. Soft-
    # deleted stores can be reviewed; a missing/repurposed store cannot.
    store = db.query(Store).filter(
        Store.id == candidate.store_id,
        Store.organization_id == candidate.organization_id,
    ).first()
    if store is None:
        raise ShopifyPrivacyIdentityRepairError("HISTORICAL_STORE_UNVERIFIED")
    if store.shopify_domain:
        try:
            stored_domain = normalize_shop_domain(store.shopify_domain)
        except (ValueError, AttributeError, TypeError) as exc:
            raise ShopifyPrivacyIdentityRepairError(
                "HISTORICAL_STORE_UNVERIFIED"
            ) from exc
        if stored_domain != domain:
            raise ShopifyPrivacyIdentityRepairError("HISTORICAL_STORE_UNVERIFIED")

    # A separately HMAC-audited receipt cannot move the same Shopify shop
    # ID/domain to another tenant. Missing bindings do not count as approval.
    others = (
        db.query(ShopifyPrivacyRequest.id)
        .filter(
            ShopifyPrivacyRequest.request_id != request_id,
            exists().where(
                ShopifyPrivacyAuditEvent.request_id ==
                ShopifyPrivacyRequest.request_id
            ).where(
                ShopifyPrivacyAuditEvent.event_type == "received"
            ).where(
                ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified"
            ),
            or_(
                and_(
                    ShopifyPrivacyRequest.shop_id == receipt.shop_id,
                    ShopifyPrivacyRequest.shop_domain != domain,
                ),
                and_(
                    ShopifyPrivacyRequest.shop_domain == domain,
                    ShopifyPrivacyRequest.shop_id != receipt.shop_id,
                ),
                and_(
                    ShopifyPrivacyRequest.shop_id == receipt.shop_id,
                    ShopifyPrivacyRequest.shop_domain == domain,
                    ShopifyPrivacyRequest.organization_id.is_not(None),
                    ShopifyPrivacyRequest.store_id.is_not(None),
                    or_(
                        ShopifyPrivacyRequest.organization_id !=
                        candidate.organization_id,
                        ShopifyPrivacyRequest.store_id != candidate.store_id,
                    ),
                ),
            ),
        )
        .first()
    )
    if others is not None:
        raise ShopifyPrivacyIdentityRepairError("SIGNED_SHOP_HISTORY_CONFLICT")

    if receipt.organization_id is not None:
        if (receipt.organization_id, receipt.store_id) != (
            candidate.organization_id, candidate.store_id,
        ):
            raise ShopifyPrivacyIdentityRepairError("TENANT_REBIND_FORBIDDEN")
        return {
            "scope_recovered": True, "repaired": False,
            "fulfillment_authorized": False, "fulfillment_complete": False,
        }

    receipt.organization_id = candidate.organization_id
    receipt.store_id = candidate.store_id
    receipt.last_error_code = None
    receipt.updated_at = datetime.utcnow()
    db.add(ShopifyPrivacyAuditEvent(
        request_id=request_id,
        event_type="shop_identity_recovered",
        from_status=receipt.status, to_status=receipt.status,
        reason_code="exact_signed_install_history",
        actor_type="internal_privacy_processor",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {
        "scope_recovered": True, "repaired": True,
        "fulfillment_authorized": False, "fulfillment_complete": False,
    }
