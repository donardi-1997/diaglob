"""Shopify local privacy processing: encrypted, incomplete customer export and field manifest.

This service can read verified local records and produce an IN-MEMORY encrypted
export for future authorized delivery. No API serves the ciphertext, no export
is stored, no external data is consulted, and no personal data is modified.
A produced snapshot is ALWAYS partial and does not fulfill a Shopify webhook.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import (
    Conversation, CustomerStoreProfile, Message, Order, OrderItem,
    ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest,
)
from ..model_domains.conversational_checkout import ConversationalCheckout
from ..shopify_security import decrypt_shopify_secret, encrypt_shopify_secret
from .shopify_privacy_scope_preview import (
    ShopifyPrivacyScopeError, preview_shopify_privacy_scope,
)

_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")
_MAX_ROWS = 250
_MAX_BYTES = 1_000_000
_UNCOVERED = (
    "shared_customer_identity",
    "unstructured_agent_and_automation_records",
    "external_processors_and_files",
    "legal_retention_and_backups",
)


class ShopifyLocalPrivacyError(ValueError):
    """Non-PII error codes only."""


@dataclass(frozen=True)
class LocalCustomerExport:
    request_id: str
    encrypted_payload: str
    payload_sha256: str
    profiles: int
    orders: int
    order_items: int
    conversations: int
    messages: int
    checkouts: int
    requested_orders_not_resolved: int
    complete: bool = False
    merchant_delivery_allowed: bool = False


@dataclass(frozen=True)
class LocalRedactionManifest:
    request_id: str
    topic: str
    fields_by_table: tuple[tuple[str, tuple[str, ...], int], ...]
    shared_customer_records_protected: int
    complete: bool = False
    mutation_allowed: bool = False


def _receipt(db: Session, request_id: str) -> ShopifyPrivacyRequest:
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ShopifyLocalPrivacyError("INVALID_PRIVACY_REQUEST_ID")
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).first()
    if receipt is None:
        raise ShopifyLocalPrivacyError("PRIVACY_REQUEST_NOT_FOUND")
    signed = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first()
    if signed is None:
        raise ShopifyLocalPrivacyError("SIGNED_INTAKE_REQUIRED")
    try:
        scope = preview_shopify_privacy_scope(db, receipt)
    except (ShopifyPrivacyScopeError, ValueError) as exc:
        raise ShopifyLocalPrivacyError("SHOP_SCOPE_UNVERIFIED") from exc
    if scope.scope_status == "subject_unresolved":
        raise ShopifyLocalPrivacyError("SHOPIFY_SUBJECT_UNRESOLVED")
    return receipt


def _limited(query, table: str):
    rows = query.limit(_MAX_ROWS + 1).all()
    if len(rows) > _MAX_ROWS:
        raise ShopifyLocalPrivacyError(f"{table.upper()}_ROW_LIMIT")
    return rows


def _selectors(receipt: ShopifyPrivacyRequest) -> dict:
    try:
        value = json.loads(decrypt_shopify_secret(receipt.selector_encrypted))
    except (ValueError, TypeError, RuntimeError) as exc:
        raise ShopifyLocalPrivacyError("SELECTOR_UNAVAILABLE") from exc
    if not isinstance(value, dict):
        raise ShopifyLocalPrivacyError("INVALID_SELECTOR")
    return value


def _canonical_order_ids(value) -> set[str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 500:
        raise ShopifyLocalPrivacyError("INVALID_ORDER_SELECTORS")
    ids: set[str] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise ShopifyLocalPrivacyError("INVALID_ORDER_SELECTORS")
        raw = str(item)
        if not raw.isascii() or not raw.isdecimal() or len(raw) > 30:
            raise ShopifyLocalPrivacyError("INVALID_ORDER_SELECTORS")
        ids.add(str(int(raw)))
    return ids


def build_encrypted_local_customer_export(
    db: Session, *, request_id: str,
) -> LocalCustomerExport:
    """Read only exact Shopify-ID-linked records for one signed customer request.

    The ciphertext is returned to a trusted Python caller only. It must NEVER
    be exposed through the current X-Internal-Secret API or written to logs.
    Missing/mismatching requested Shopify order IDs are reported as counts and
    left for manual review; we NEVER search by email, phone or order number.
    """
    receipt = _receipt(db, request_id)
    if receipt.topic != "customers/data_request":
        raise ShopifyLocalPrivacyError("DATA_REQUEST_TOPIC_REQUIRED")
    selector = _selectors(receipt)
    subject = selector.get("customer")
    if not isinstance(subject, dict) or subject.get("id") is None:
        raise ShopifyLocalPrivacyError("EXACT_CUSTOMER_ID_REQUIRED")
    external_id = str(subject["id"]).strip()
    if not external_id:
        raise ShopifyLocalPrivacyError("EXACT_CUSTOMER_ID_REQUIRED")

    profiles = _limited(db.query(CustomerStoreProfile).filter(
        CustomerStoreProfile.organization_id == receipt.organization_id,
        CustomerStoreProfile.store_id == receipt.store_id,
        CustomerStoreProfile.external_customer_id == external_id,
    ).order_by(CustomerStoreProfile.id), "profiles")
    if len(profiles) != 1:
        # Multiple locally linked identities for one remote ID are ambiguous;
        # an absent identity is NOT permission to link via email or phone.
        raise ShopifyLocalPrivacyError("SHOPIFY_SUBJECT_UNRESOLVED_OR_AMBIGUOUS")
    customer_id = profiles[0].customer_id
    requested = _canonical_order_ids(selector.get("orders_requested"))

    orders = _limited(db.query(Order).filter(
        Order.organization_id == receipt.organization_id,
        Order.store_id == receipt.store_id,
        Order.customer_id == customer_id,
    ).order_by(Order.id), "orders")
    if requested is not None:
        selected = [x for x in orders if x.shopify_order_id in requested]
        found = {x.shopify_order_id for x in selected}
        missing_orders = len(requested - found)
        orders = selected
    else:
        missing_orders = 0
    order_ids = [row.id for row in orders]
    items = _limited(db.query(OrderItem).filter(
        OrderItem.organization_id == receipt.organization_id,
        OrderItem.store_id == receipt.store_id,
        OrderItem.order_id.in_(order_ids),
    ).order_by(OrderItem.id), "order_items") if order_ids else []
    item_map = {oid: [] for oid in order_ids}
    for item in items:
        item_map[item.order_id].append({
            "title": item.title, "sku": item.sku,
            "quantity": item.quantity, "unit_price": str(item.unit_price),
        })

    conversations = _limited(db.query(Conversation).filter(
        Conversation.organization_id == receipt.organization_id,
        Conversation.store_id == receipt.store_id,
        Conversation.customer_id == customer_id,
    ).order_by(Conversation.id), "conversations")
    convo_ids = [x.id for x in conversations]
    messages = _limited(db.query(Message).filter(
        Message.conversation_id.in_(convo_ids),
    ).order_by(Message.id), "messages") if convo_ids else []
    message_map = {cid: [] for cid in convo_ids}
    for msg in messages:
        message_map[msg.conversation_id].append({
            "sender": msg.sender, "text": msg.text,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })

    checkouts = _limited(db.query(ConversationalCheckout).filter(
        ConversationalCheckout.organization_id == receipt.organization_id,
        ConversationalCheckout.store_id == receipt.store_id,
        ConversationalCheckout.customer_id == customer_id,
    ).order_by(ConversationalCheckout.id), "checkouts")

    payload = {
        "schema": "diaglob.shopify.local_customer_export.v1",
        "request_id": receipt.request_id,
        "complete": False,
        "uncovered": list(_UNCOVERED),
        "unresolved_requested_order_count": missing_orders,
        "profiles": [{
            "external_customer_id": p.external_customer_id,
            "orders_count": p.orders_count, "total_spent": str(p.total_spent),
            "currency": p.currency, "last_order_ref": p.last_order_ref,
        } for p in profiles],
        "orders": [{
            "shopify_order_id": o.shopify_order_id,
            "order_number": o.order_number, "financial_status": o.financial_status,
            "total_amount": str(o.total_amount), "currency": o.currency,
            "shipping_address": o.shipping_address, "note": o.note,
            "items": item_map[o.id],
        } for o in orders],
        "conversations": [{
            "channel": c.channel, "preview": c.preview,
            "messages": message_map[c.id],
        } for c in conversations],
        "checkouts": [{
            "status": c.status, "customer_name": c.customer_name,
            "phone": c.phone, "address_raw": c.address_raw,
            "address_line": c.address_line, "address_complement": c.address_complement,
            "neighborhood": c.neighborhood, "city": c.city, "region": c.region,
            "country_code": c.country_code, "postal_code": c.postal_code,
            "delivery_reference": c.delivery_reference, "failure_reason": c.failure_reason,
        } for c in checkouts],
    }
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(plaintext.encode("utf-8")) > _MAX_BYTES:
        raise ShopifyLocalPrivacyError("EXPORT_PAYLOAD_LIMIT")
    return LocalCustomerExport(
        request_id=request_id,
        encrypted_payload=encrypt_shopify_secret(plaintext),
        payload_sha256=hashlib.sha256(plaintext.encode("utf-8")).hexdigest(),
        profiles=len(profiles), orders=len(orders), order_items=len(items),
        conversations=len(conversations), messages=len(messages),
        checkouts=len(checkouts), requested_orders_not_resolved=missing_orders,
    )


def build_local_redaction_manifest(
    db: Session, *, request_id: str,
) -> LocalRedactionManifest:
    """Identify redactable local fields; never run mutations or claim completion."""
    receipt = _receipt(db, request_id)
    if receipt.topic not in {"customers/redact", "shop/redact"}:
        raise ShopifyLocalPrivacyError("REDACTION_TOPIC_REQUIRED")
    preview = preview_shopify_privacy_scope(db, receipt)
    # The manifest describes field-level operations only. Retention/legal holds,
    # external processors, shared identities and backups are unresolved.
    return LocalRedactionManifest(
        request_id=request_id, topic=receipt.topic,
        fields_by_table=(
            ("customer_store_profiles", ("external_customer_id", "last_order_ref"),
             preview.matched_customer_profiles),
            ("orders", ("note", "shipping_address", "invoice_url", "external_last_error"),
             preview.matched_store_orders),
            ("conversations", ("preview", "tags"), preview.matched_store_conversations),
            ("messages", ("text", "external_message_id"), -1),
            ("conversational_checkouts", (
                "customer_name", "phone", "address_raw", "address_line",
                "address_complement", "neighborhood", "city", "region",
                "postal_code", "delivery_reference", "failure_reason",
            ), preview.matched_conversational_checkouts),
        ),
        shared_customer_records_protected=preview.shared_customers_protected,
    )
