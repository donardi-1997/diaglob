"""PII-free, read-only operational audit of Shopify privacy webhook intake.

This report cannot inspect the Shopify Dev Dashboard: app-level webhook
subscriptions must be verified against the *released Shopify app version*.
Do not use a receipt count or HTTP 401 as proof that Shopify is subscribed.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping

from sqlalchemy import func
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import (
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    ShopifyPrivacySuppression,
    ShopifyPrivacyWorkItem,
)

TOPICS = ("customers/data_request", "customers/redact", "shop/redact")
REQUIRED_WORK_ITEMS_PER_RECEIPT = 10


def summarize_shopify_privacy_operations(
    db: Session, *, environment: Mapping[str, str] | None = None,
) -> dict:
    """Read aggregate metadata only; never select subject identifiers or payloads."""
    env = os.environ if environment is None else environment

    topic_counts = {topic: 0 for topic in TOPICS}
    for topic, count in db.query(
        ShopifyPrivacyRequest.topic, func.count(ShopifyPrivacyRequest.id),
    ).group_by(ShopifyPrivacyRequest.topic).all():
        if topic in topic_counts:
            topic_counts[topic] = int(count)

    received = int(db.query(func.count(ShopifyPrivacyRequest.id)).scalar() or 0)
    signed = int(db.query(
        func.count(func.distinct(ShopifyPrivacyAuditEvent.request_id))
    ).filter(
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).scalar() or 0)
    prepared_audit = int(db.query(
        func.count(func.distinct(ShopifyPrivacyAuditEvent.request_id))
    ).filter(
        ShopifyPrivacyAuditEvent.event_type == "processing_prepared",
        ShopifyPrivacyAuditEvent.actor_type == "internal_privacy_processor",
    ).scalar() or 0)

    item_counts = db.query(
        ShopifyPrivacyWorkItem.request_id.label("rid"),
        func.count(ShopifyPrivacyWorkItem.id).label("total"),
    ).group_by(ShopifyPrivacyWorkItem.request_id).subquery()
    incomplete = int(db.query(func.count(ShopifyPrivacyRequest.id)).outerjoin(
        item_counts, ShopifyPrivacyRequest.request_id == item_counts.c.rid,
    ).filter(
        func.coalesce(item_counts.c.total, 0) != REQUIRED_WORK_ITEMS_PER_RECEIPT,
    ).scalar() or 0)

    # A task marked "completed" without a verified fulfillment path is
    # anomalous even if the expected ten task rows are present.
    unauthorized_completion_states = int(db.query(
        func.count(ShopifyPrivacyWorkItem.id),
    ).filter(
        ShopifyPrivacyWorkItem.status.in_(
            ("completed", "fulfilled", "delivered", "deleted", "erased")
        ),
    ).scalar() or 0)

    suppression_counts = {"staged": 0, "active": 0}
    for status, count in db.query(
        ShopifyPrivacySuppression.status, func.count(ShopifyPrivacySuppression.id),
    ).group_by(ShopifyPrivacySuppression.status).all():
        if status in suppression_counts:
            suppression_counts[status] = int(count)

    hmac_configured = bool(env.get("SHOPIFY_CLIENT_SECRET"))
    encrypted_selectors_configured = bool(env.get("SHOPIFY_TOKEN_ENCRYPTION_KEY"))
    partner_access = bool(
        env.get("SHOPIFY_PARTNER_ORG_ID")
        and env.get("SHOPIFY_PARTNER_APP_GID")
        and env.get("SHOPIFY_PARTNER_ACCESS_TOKEN")
    )
    return {
        "audit": "shopify_privacy_operations_read_only",
        "topic_receipts": topic_counts,
        "receipt_total": received,
        "distinct_signed_received_audits": signed,
        "distinct_processing_prepared_audits": prepared_audit,
        "receipts_missing_complete_ten_item_queue": incomplete,
        "work_items_with_unverified_completion_state": unauthorized_completion_states,
        "staged_suppressions": suppression_counts["staged"],
        "active_suppressions": suppression_counts["active"],
        "hmac_secret_present": hmac_configured,
        "selector_encryption_key_present": encrypted_selectors_configured,
        "internal_review_secret_present": bool(env.get("DIAGLOB_INTERNAL_SECRET")),
        "partner_dashboard_access_configured": partner_access,
        "released_shopify_subscription_verified": False,
        "valid_live_shopify_delivery_verified": False,
        "data_export_or_erasure_fulfilled": False,
        # The intake-only "review_required" flag below must never be used
        # as an App Store compliance or production fulfillment verdict.
        # These release controls are deliberately fail-closed until backed by
        # an independently verified, end-to-end workflow.
        "privacy_fulfillment_release_ready": False,
        "privacy_fulfillment_release_blockers": [
            "SHOPIFY_ACTIVE_VERSION_SUBSCRIPTIONS_NOT_VERIFIED_BY_THIS_AUDIT",
            "REAL_SHOPIFY_DELIVERY_NOT_VERIFIED_BY_THIS_AUDIT",
            "LEGAL_RETENTION_AND_HOLDS_NOT_APPROVED",
            "EXTERNAL_PROCESSOR_ERASURE_NOT_VERIFIED",
            "BACKUP_RESTORE_AND_REINGESTION_NOT_VERIFIED",
            "LIVE_CUSTOMER_EXPORT_NOT_ENABLED",
            "LIVE_CUSTOMER_AND_SHOP_REDACTION_NOT_ENABLED",
        ],
        "review_required": (
            not hmac_configured
            or not encrypted_selectors_configured
            or incomplete > 0
            or unauthorized_completion_states > 0
            or signed != received
            or prepared_audit != received
            or suppression_counts["active"] > 0
        ),
    }


def main() -> None:
    with SessionLocal() as db:
        report = summarize_shopify_privacy_operations(db)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
