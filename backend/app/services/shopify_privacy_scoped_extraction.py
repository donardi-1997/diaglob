"""Encrypted Shopify customer export extraction, restricted to in-memory fixtures.

This is a proof of the actual ORM joins and record projection, not permission
to read real personal data. Production databases cannot invoke this worker.
No API, storage, delivery, or receipt completion is provided.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from ..models import (
    Conversation,
    CustomerStoreProfile,
    Order,
    ShopifyPrivacyRequest,
)
from ..model_domains.conversational_checkout import ConversationalCheckout
from ..shopify_security import decrypt_shopify_secret
from .shopify_privacy_case_assessment import (
    ShopifyPrivacyAssessmentError,
    assess_shopify_privacy_case,
)

_MAX_ROWS = 1000


class ShopifyPrivacyExtractionError(ValueError):
    """Opaque error codes; never embed customer values in exceptions."""


@dataclass(frozen=True)
class EncryptedShopifyFixtureExtraction:
    ciphertext: bytes
    sha256: str
    source_counts: dict[str, int]
    fixture_only: bool = True
    delivery_authorized: bool = False
    fulfillment_complete: bool = False


def _require_in_memory_fixture(db: Session) -> None:
    bind = db.get_bind()
    if (
        bind is None
        or bind.dialect.name != "sqlite"
        or bind.url.database != ":memory:"
    ):
        raise ShopifyPrivacyExtractionError("LIVE_CUSTOMER_EXTRACTION_DISABLED")


def _bounded_rows(query):
    rows = query.limit(_MAX_ROWS + 1).all()
    if len(rows) > _MAX_ROWS:
        raise ShopifyPrivacyExtractionError("EXPORT_SOURCE_ROW_LIMIT_EXCEEDED")
    return rows


def build_encrypted_shopify_fixture_extraction(
    db: Session, *, request_id: str, encryption_key: bytes,
    fixture_authorized: bool = False,
) -> EncryptedShopifyFixtureExtraction:
    """Exercise source-to-customer joins in a disposable SQLite fixture only.

    The default is deny. Validation precedes all receipt/subject lookups.
    Matching by merchant-provided email alone is forbidden; Shopify's external
    customer ID must resolve uniquely to one per-store profile. Shared
    organization-level Customer fields are excluded by design.
    """
    if fixture_authorized is not True:
        raise ShopifyPrivacyExtractionError("LIVE_CUSTOMER_EXTRACTION_DISABLED")
    _require_in_memory_fixture(db)
    try:
        cipher = Fernet(encryption_key)
    except (TypeError, ValueError) as exc:
        raise ShopifyPrivacyExtractionError("INVALID_EXPORT_ENCRYPTION_KEY") from exc

    try:
        assessment = assess_shopify_privacy_case(db, request_id=request_id)
    except ShopifyPrivacyAssessmentError as exc:
        raise ShopifyPrivacyExtractionError("INVALID_PRIVACY_REQUEST_ID") from exc
    if assessment is None or not assessment.verified_signed_intake:
        raise ShopifyPrivacyExtractionError("SIGNED_RECEIPT_REQUIRED")
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).first()
    if (
        receipt is None
        or receipt.topic != "customers/data_request"
        or receipt.completed_at is not None
        or not assessment.verified_shop_scope
        or receipt.organization_id is None
        or receipt.store_id is None
    ):
        raise ShopifyPrivacyExtractionError("UNVERIFIED_CUSTOMER_EXPORT_SCOPE")
    try:
        selector = json.loads(decrypt_shopify_secret(receipt.selector_encrypted))
        external_id = str(selector["customer"]["id"]).strip()
    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
        raise ShopifyPrivacyExtractionError("CUSTOMER_SELECTOR_UNAVAILABLE") from exc
    if not external_id:
        raise ShopifyPrivacyExtractionError("CUSTOMER_SELECTOR_UNAVAILABLE")

    org, store = receipt.organization_id, receipt.store_id
    profiles = _bounded_rows(db.query(CustomerStoreProfile).filter(
        CustomerStoreProfile.organization_id == org,
        CustomerStoreProfile.store_id == store,
        CustomerStoreProfile.external_customer_id == external_id,
    ).order_by(CustomerStoreProfile.id))
    # Require exactly one per-store profile, not merely one distinct customer
    # behind multiple conflicting mappings. Assessment has already checked
    # that the customer itself belongs to this organization.
    if len(profiles) != 1 or profiles[0].customer_id is None:
        raise ShopifyPrivacyExtractionError("AMBIGUOUS_OR_MISSING_CUSTOMER_LINK")
    customer_id = profiles[0].customer_id

    orders = _bounded_rows(db.query(Order).filter(
        Order.organization_id == org,
        Order.store_id == store,
        Order.customer_id == customer_id,
    ).order_by(Order.id))
    conversations = _bounded_rows(db.query(Conversation).filter(
        Conversation.organization_id == org,
        Conversation.store_id == store,
        Conversation.customer_id == customer_id,
    ).order_by(Conversation.id))
    checkouts = _bounded_rows(db.query(ConversationalCheckout).filter(
        ConversationalCheckout.organization_id == org,
        ConversationalCheckout.store_id == store,
        ConversationalCheckout.customer_id == customer_id,
    ).order_by(ConversationalCheckout.id))

    source_counts = {
        "customer_store_profiles": len(profiles),
        "orders": len(orders),
        "conversations": len(conversations),
        "conversational_checkouts": len(checkouts),
    }
    expected = {
        "customer_store_profiles": assessment.matched_customer_profiles,
        "orders": assessment.matched_store_orders,
        "conversations": assessment.matched_store_conversations,
        "conversational_checkouts": assessment.matched_conversational_checkouts,
    }
    if source_counts != expected:
        raise ShopifyPrivacyExtractionError("EXPORT_SCOPE_CHANGED_DURING_READ")
    payload = {
        "schema_version": 1,
        "fixture_only": True,
        "sources": {
            "customer_store_profiles": [
                {"external_customer_id": p.external_customer_id,
                 "currency": p.currency} for p in profiles
            ],
            "orders": [
                {"order_number": o.order_number, "note": o.note,
                 "shipping_address": o.shipping_address} for o in orders
            ],
            "conversations": [
                {"channel": c.channel, "preview": c.preview} for c in conversations
            ],
            "conversational_checkouts": [
                {"customer_name": c.customer_name, "phone": c.phone,
                 "address_line": c.address_line, "city": c.city}
                for c in checkouts
            ],
        },
    }
    data = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    ciphertext = cipher.encrypt(data)
    return EncryptedShopifyFixtureExtraction(
        ciphertext=ciphertext,
        sha256=hashlib.sha256(ciphertext).hexdigest(),
        source_counts=source_counts,
    )
