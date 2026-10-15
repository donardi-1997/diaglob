"""Non-destructive impact preview for signed Shopify privacy requests.

This module deliberately never reads arbitrary customer PII, exports content,
deletes records, or mutates database state. Only reviewed synthetic fixtures
may be used until the legal retention schedule is approved for real data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection,
    Conversation,
    CustomerStoreProfile,
    Order,
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    Store,
)
from ..shopify_oauth import normalize_shop_domain
from ..model_domains.conversational_checkout import ConversationalCheckout
from ..shopify_security import decrypt_shopify_secret


class ShopifyPrivacyScopeError(ValueError):
    """Review required before determining any affected data scope."""


@dataclass(frozen=True)
class ShopifyPrivacyScopePreview:
    topic: str
    request_id: str
    matched_customer_profiles: int
    matched_store_orders: int
    matched_store_conversations: int
    matched_conversational_checkouts: int
    shared_customers_protected: int
    scope_status: str
    # Deliberately excludes customer names, emails, phone, address and row IDs.


def _reject_conflicting_signed_shop_history(
    db: Session, receipt: ShopifyPrivacyRequest, canonical_domain: str,
) -> None:
    """Deny historical Shopify shop-ID/tenant drift without touching buyer data.

    Past receipts are only considered evidence when accompanied by a verified
    intake event. Shopify's signed shop ID must not silently move to another
    domain or tenant, nor may one domain silently move to another Shopify ID.
    This is a negative integrity check, *not* independent Shopify Admin shop-ID
    attestation or permission for customer disclosure and deletion.
    """
    if not isinstance(receipt.shop_id, str) or not receipt.shop_id.strip():
        raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_SHOP_ID_MISSING")
    conflict = db.query(ShopifyPrivacyRequest.id).join(
        ShopifyPrivacyAuditEvent,
        ShopifyPrivacyAuditEvent.request_id == ShopifyPrivacyRequest.request_id,
    ).filter(
        ShopifyPrivacyRequest.request_id != receipt.request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
        or_(
            and_(
                ShopifyPrivacyRequest.shop_domain == canonical_domain,
                ShopifyPrivacyRequest.shop_id != receipt.shop_id,
            ),
            and_(
                ShopifyPrivacyRequest.shop_id == receipt.shop_id,
                ShopifyPrivacyRequest.shop_domain != canonical_domain,
            ),
            and_(
                ShopifyPrivacyRequest.shop_id == receipt.shop_id,
                ShopifyPrivacyRequest.shop_domain == canonical_domain,
                ShopifyPrivacyRequest.organization_id.is_not(None),
                ShopifyPrivacyRequest.store_id.is_not(None),
                or_(
                    ShopifyPrivacyRequest.organization_id != receipt.organization_id,
                    ShopifyPrivacyRequest.store_id != receipt.store_id,
                ),
            ),
        ),
    ).first()
    if conflict is not None:
        raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_SIGNED_SHOP_HISTORY_CONFLICT")


def preview_shopify_privacy_scope(
    db: Session,
    receipt: ShopifyPrivacyRequest,
) -> ShopifyPrivacyScopePreview:
    """Return counts within the request's original tenant/store only.

    A stored receipt is **not** execution approval. Request mapping must have
    been established at authenticated intake, and the current store identity
    must still match the originally signed Shopify shop domain.
    """
    if receipt.topic not in {
        "customers/data_request",
        "customers/redact",
        "shop/redact",
    }:
        raise ShopifyPrivacyScopeError("UNSUPPORTED_PRIVACY_TOPIC")
    if receipt.organization_id is None or receipt.store_id is None:
        raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_TENANT_UNRESOLVED")
    store = db.query(Store).filter(
        Store.id == receipt.store_id,
        Store.organization_id == receipt.organization_id,
    ).first()
    if store is None:
        raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_STORE_NOT_FOUND")
    try:
        expected_domain = normalize_shop_domain(receipt.shop_domain)
        stored_domain = (
            normalize_shop_domain(store.shopify_domain)
            if store.shopify_domain else None
        )
    except (ValueError, AttributeError) as exc:
        raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_STORE_UNVERIFIED") from exc
    if stored_domain and stored_domain != expected_domain:
        raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_STORE_MISMATCH")
    _reject_conflicting_signed_shop_history(db, receipt, expected_domain)
    trusted_connection = db.query(CommerceConnection).filter(
        CommerceConnection.organization_id == receipt.organization_id,
        CommerceConnection.store_id == receipt.store_id,
        CommerceConnection.provider == "shopify",
        CommerceConnection.external_store_url == expected_domain,
    ).first()
    if not trusted_connection and stored_domain != expected_domain:
        raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_STORE_UNVERIFIED")

    if receipt.topic == "shop/redact":
        profiles = db.query(CustomerStoreProfile.customer_id).filter(
            CustomerStoreProfile.organization_id == receipt.organization_id,
            CustomerStoreProfile.store_id == receipt.store_id,
        ).distinct().all()
        customer_ids = [row[0] for row in profiles]
        scope = "shop_scope_preview_only"
    else:
        try:
            selectors = json.loads(decrypt_shopify_secret(receipt.selector_encrypted))
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_SELECTORS_UNAVAILABLE") from exc
        if not isinstance(selectors, dict):
            raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_SELECTORS_INVALID")
        customer = selectors.get("customer")
        if not isinstance(customer, dict) or customer.get("id") is None:
            raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_CUSTOMER_ID_REQUIRED")
        external_id = str(customer["id"]).strip()
        if not external_id:
            raise ShopifyPrivacyScopeError("SHOPIFY_PRIVACY_CUSTOMER_ID_REQUIRED")
        # Never treat duplicate Shopify -> Diaglob customer mappings as
        # proof of identity, even if all duplicates point at the same buyer.
        # Two rows are sufficient to detect ambiguity without scanning PII.
        profiles = db.query(CustomerStoreProfile.customer_id).filter(
            CustomerStoreProfile.organization_id == receipt.organization_id,
            CustomerStoreProfile.store_id == receipt.store_id,
            CustomerStoreProfile.external_customer_id == external_id,
        ).limit(2).all()
        if len(profiles) == 1 and profiles[0][0] is not None:
            customer_ids = [profiles[0][0]]
            scope = "customer_scope_preview_only"
        else:
            customer_ids = []
            scope = "subject_unresolved"

    profile_count = len(customer_ids)
    if customer_ids:
        other_store_profile_count = db.query(
            func.count(func.distinct(CustomerStoreProfile.customer_id))
        ).filter(
            CustomerStoreProfile.organization_id == receipt.organization_id,
            CustomerStoreProfile.store_id != receipt.store_id,
            CustomerStoreProfile.customer_id.in_(customer_ids),
        ).scalar() or 0
    else:
        other_store_profile_count = 0

    if receipt.topic == "shop/redact":
        orders = db.query(func.count(Order.id)).filter(
            Order.organization_id == receipt.organization_id,
            Order.store_id == receipt.store_id,
        ).scalar() or 0
        conversations = db.query(func.count(Conversation.id)).filter(
            Conversation.organization_id == receipt.organization_id,
            Conversation.store_id == receipt.store_id,
        ).scalar() or 0
        checkouts = db.query(func.count(ConversationalCheckout.id)).filter(
            ConversationalCheckout.organization_id == receipt.organization_id,
            ConversationalCheckout.store_id == receipt.store_id,
        ).scalar() or 0
    elif customer_ids:
        orders = db.query(func.count(Order.id)).filter(
            Order.organization_id == receipt.organization_id,
            Order.store_id == receipt.store_id,
            Order.customer_id.in_(customer_ids),
        ).scalar() or 0
        conversations = db.query(func.count(Conversation.id)).filter(
            Conversation.organization_id == receipt.organization_id,
            Conversation.store_id == receipt.store_id,
            Conversation.customer_id.in_(customer_ids),
        ).scalar() or 0
        checkouts = db.query(func.count(ConversationalCheckout.id)).filter(
            ConversationalCheckout.organization_id == receipt.organization_id,
            ConversationalCheckout.store_id == receipt.store_id,
            ConversationalCheckout.customer_id.in_(customer_ids),
        ).scalar() or 0
    else:
        orders = 0
        conversations = 0
        checkouts = 0

    return ShopifyPrivacyScopePreview(
        topic=receipt.topic,
        request_id=receipt.request_id,
        matched_customer_profiles=profile_count,
        matched_store_orders=int(orders),
        matched_store_conversations=int(conversations),
        matched_conversational_checkouts=int(checkouts),
        shared_customers_protected=int(other_store_profile_count),
        scope_status=scope,
    )
