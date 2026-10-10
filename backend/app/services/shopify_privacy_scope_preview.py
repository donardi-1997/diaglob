"""Non-destructive impact preview for signed Shopify privacy requests.

This module deliberately never reads arbitrary customer PII, exports content,
deletes records, or mutates database state. Only reviewed synthetic fixtures
may be used until the legal retention schedule is approved for real data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import (
    CommerceConnection,
    Conversation,
    ConversationalCheckout,
    CustomerStoreProfile,
    Order,
    ShopifyPrivacyRequest,
    Store,
)
from ..shopify_oauth import normalize_shop_domain
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
        profiles = db.query(CustomerStoreProfile.customer_id).filter(
            CustomerStoreProfile.organization_id == receipt.organization_id,
            CustomerStoreProfile.store_id == receipt.store_id,
            CustomerStoreProfile.external_customer_id == external_id,
        ).all()
        customer_ids = sorted({row[0] for row in profiles})
        scope = "customer_scope_preview_only" if customer_ids else "subject_unresolved"

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
