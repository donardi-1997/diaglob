"""Synthetic-only Shopify privacy export and redaction planning.

No HTTP routes, scheduled tasks, deletion queries, external delivery, or
production execution are provided. A Shopify GDPR webhook receipt alone does
not authorize data release or erasure.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import (
    Conversation,
    CustomerStoreProfile,
    Message,
    Order,
    OrderItem,
    ShopifyPrivacyRequest,
)
from ..shopify_security import decrypt_shopify_secret, encrypt_shopify_secret
from .shopify_privacy_scope_preview import (
    ShopifyPrivacyScopeError,
    preview_shopify_privacy_scope,
)

# Defense in depth: the processor cannot run against the PostgreSQL production
# database, even if someone accidentally imports the functions into a job.
MAX_ROWS_PER_TABLE = 250
MAX_ENCRYPTED_PAYLOAD_BYTES = 1_000_000

UNCOVERED_DATA_SOURCES = (
    "global_customer_fields",
    "automations_and_ai_derived_data",
    "external_integrations_and_processors",
    "file_attachments_and_object_storage",
    "operational_logs_and_backups",
    "retention_and_legal_holds",
)


class ShopifyPrivacySyntheticError(ValueError):
    """The synthetic scenario needs more evidence or is not authorized."""


@dataclass(frozen=True)
class SyntheticExport:
    request_id: str
    encrypted_payload: str
    profile_count: int
    order_count: int
    conversation_count: int
    message_count: int
    completeness: str = "partial_requires_review"
    # Export never contains another store's records, even within one tenant.


@dataclass(frozen=True)
class SyntheticRedactionPlan:
    request_id: str
    topic: str
    profile_candidates: int
    order_candidates: int
    conversation_candidates: int
    global_customer_records_protected: int
    action: str = "review_only_no_mutations"
    legal_hold_clearance: bool = False
    external_data_coverage_complete: bool = False


def _ensure_synthetic_sqlite(db: Session) -> None:
    """Fail closed unless invoked by an explicitly opted-in pytest SQLite test."""
    if (
        os.getenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS") != "1"
        or not os.getenv("PYTEST_CURRENT_TEST")
        or db.get_bind().dialect.name != "sqlite"
    ):
        raise ShopifyPrivacySyntheticError("SYNTHETIC_TEST_ONLY")


def _limited(query, *, kind: str):
    rows = query.limit(MAX_ROWS_PER_TABLE + 1).all()
    if len(rows) > MAX_ROWS_PER_TABLE:
        raise ShopifyPrivacySyntheticError(f"{kind.upper()}_TOO_MANY_RECORDS")
    return rows


def _subject_customer_ids(db: Session, receipt: ShopifyPrivacyRequest) -> list[int]:
    """Read the exact store-local Shopify customer selector, never email/phone."""
    try:
        selectors = json.loads(decrypt_shopify_secret(receipt.selector_encrypted))
    except (RuntimeError, ValueError, TypeError) as exc:
        raise ShopifyPrivacySyntheticError("SUBJECT_SELECTOR_UNAVAILABLE") from exc
    if not isinstance(selectors, dict) or not isinstance(
        selectors.get("customer"), dict
    ):
        raise ShopifyPrivacySyntheticError("SUBJECT_SELECTOR_INVALID")
    external_id = selectors["customer"].get("id")
    if external_id is None or not str(external_id).strip():
        raise ShopifyPrivacySyntheticError("EXTERNAL_CUSTOMER_ID_REQUIRED")
    profiles = _limited(
        db.query(CustomerStoreProfile.customer_id).filter(
            CustomerStoreProfile.organization_id == receipt.organization_id,
            CustomerStoreProfile.store_id == receipt.store_id,
            CustomerStoreProfile.external_customer_id == str(external_id).strip(),
        ),
        kind="customer",
    )
    return sorted({row[0] for row in profiles})


def build_synthetic_customer_export(
    db: Session,
    receipt: ShopifyPrivacyRequest,
) -> SyntheticExport:
    """Build an encrypted, *partial* customer export for one verified store.

    Does not include shared/global Customer fields, and must not be delivered
    to a merchant as a complete Shopify GDPR export.
    """
    _ensure_synthetic_sqlite(db)
    if receipt.topic != "customers/data_request":
        raise ShopifyPrivacySyntheticError("TOPIC_NOT_CUSTOMER_DATA_REQUEST")
    # Includes trusted shop domain, store and organization verification.
    preview_shopify_privacy_scope(db, receipt)
    customer_ids = _subject_customer_ids(db, receipt)
    profiles = []
    orders = []
    conversations = []
    item_count = 0
    message_count = 0

    if customer_ids:
        profile_rows = _limited(
            db.query(CustomerStoreProfile).filter(
                CustomerStoreProfile.organization_id == receipt.organization_id,
                CustomerStoreProfile.store_id == receipt.store_id,
                CustomerStoreProfile.customer_id.in_(customer_ids),
            ).order_by(CustomerStoreProfile.id),
            kind="profiles",
        )
        profiles = [
            {
                "external_customer_id": p.external_customer_id,
                "orders_count": p.orders_count,
                "total_spent": str(p.total_spent),
                "currency": p.currency,
                "last_order_ref": p.last_order_ref,
            }
            for p in profile_rows
        ]
        order_rows = _limited(
            db.query(Order).filter(
                Order.organization_id == receipt.organization_id,
                Order.store_id == receipt.store_id,
                Order.customer_id.in_(customer_ids),
            ).order_by(Order.id),
            kind="orders",
        )
        order_ids = [o.id for o in order_rows]
        items_by_order: dict[int, list[dict]] = {oid: [] for oid in order_ids}
        if order_ids:
            item_rows = _limited(
                db.query(OrderItem).filter(
                    OrderItem.organization_id == receipt.organization_id,
                    OrderItem.store_id == receipt.store_id,
                    OrderItem.order_id.in_(order_ids),
                ).order_by(OrderItem.id),
                kind="items",
            )
            item_count = len(item_rows)
            for item in item_rows:
                items_by_order[item.order_id].append({
                    "title": item.title,
                    "sku": item.sku,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "shopify_line_item_id": item.shopify_line_item_id,
                })
        orders = [
            {
                "shopify_order_id": o.shopify_order_id,
                "order_number": o.order_number,
                "financial_status": o.financial_status,
                "total_amount": str(o.total_amount),
                "currency": o.currency,
                "shipping_address": o.shipping_address,
                "note": o.note,
                "items": items_by_order[o.id],
            }
            for o in order_rows
        ]

        conversation_rows = _limited(
            db.query(Conversation).filter(
                Conversation.organization_id == receipt.organization_id,
                Conversation.store_id == receipt.store_id,
                Conversation.customer_id.in_(customer_ids),
            ).order_by(Conversation.id),
            kind="conversations",
        )
        message_map: dict[int, list[dict]] = {
            conversation.id: [] for conversation in conversation_rows
        }
        if message_map:
            messages = _limited(
                db.query(Message).filter(
                    Message.conversation_id.in_(list(message_map)),
                ).order_by(Message.id),
                kind="messages",
            )
            message_count = len(messages)
            for message in messages:
                message_map[message.conversation_id].append({
                    "sender": message.sender,
                    "text": message.text,
                    "created_at": (
                        message.created_at.isoformat() if message.created_at else None
                    ),
                })
        conversations = [
            {
                "channel": convo.channel,
                "preview": convo.preview,
                "messages": message_map[convo.id],
            }
            for convo in conversation_rows
        ]

    document = {
        "schema": "diaglob.shopify.synthetic_export.v1",
        "request_id": receipt.request_id,
        "scope": "single_verified_shop",
        "complete": False,
        "uncovered_sources": UNCOVERED_DATA_SOURCES,
        "profiles": profiles,
        "orders": orders,
        "conversations": conversations,
    }
    plaintext = json.dumps(
        document, ensure_ascii=False, separators=(",", ":")
    )
    if len(plaintext.encode("utf-8")) > MAX_ENCRYPTED_PAYLOAD_BYTES:
        raise ShopifyPrivacySyntheticError("EXPORT_TOO_LARGE")
    return SyntheticExport(
        request_id=receipt.request_id,
        encrypted_payload=encrypt_shopify_secret(plaintext),
        profile_count=len(profiles),
        order_count=len(orders),
        conversation_count=len(conversations),
        message_count=message_count,
    )


def plan_synthetic_redaction(
    db: Session,
    receipt: ShopifyPrivacyRequest,
) -> SyntheticRedactionPlan:
    """Aggregate prospective scope without exposing subjects or issuing DML."""
    _ensure_synthetic_sqlite(db)
    if receipt.topic not in {"customers/redact", "shop/redact"}:
        raise ShopifyPrivacySyntheticError("TOPIC_NOT_REDACTION")
    try:
        preview = preview_shopify_privacy_scope(db, receipt)
    except ShopifyPrivacyScopeError as exc:
        raise ShopifyPrivacySyntheticError(str(exc)) from exc
    return SyntheticRedactionPlan(
        request_id=receipt.request_id,
        topic=receipt.topic,
        profile_candidates=preview.matched_customer_profiles,
        order_candidates=preview.matched_store_orders,
        conversation_candidates=preview.matched_store_conversations,
        global_customer_records_protected=preview.shared_customers_protected,
    )
