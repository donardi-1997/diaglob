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
from .services.shopify_privacy_attestations import (
    evaluate_privacy_program_attestations,
    live_execution_configured,
    privacy_release_blockers,
)
from .models import (
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    ShopifyPrivacySuppression,
    ShopifyPrivacyWorkItem,
)

TOPICS = ("customers/data_request", "customers/redact", "shop/redact")
REQUIRED_WORK_ITEMS_PER_RECEIPT = 10
_ACTIVE_STATES = frozenset({"connected", "present_unverified"})


def _register_all_model_domains() -> None:
    import importlib
    import pkgutil

    from . import model_domains

    for module in pkgutil.iter_modules(model_domains.__path__):
        importlib.import_module(f"{model_domains.__name__}.{module.name}")


def _active_processor_controls(db: Session) -> set[str]:
    """Processor controls any live store activates; counts only, no identifiers.

    On any detection failure every processor is treated as active, so a
    ``not_in_use`` attestation can never pass on missing evidence.
    """
    from .models import Store
    from .services.shopify_privacy_controls import PROCESSOR_CONTROLS

    # Standalone `python -m` runs do not import the full app; register every
    # model domain so string relationships (e.g. Shipment -> SupplierOrder)
    # resolve. Otherwise detection fails closed and contradicts valid
    # not_in_use attestations.
    _register_all_model_domains()
    from .services.shopify_privacy_subprocessors import inspect_shopify_privacy_subprocessors

    try:
        with db.begin_nested():
            active: set[str] = set()
            for store_id, organization_id in db.query(
                Store.id, Store.organization_id,
            ).filter(Store.deleted.is_(False)).all():
                report = inspect_shopify_privacy_subprocessors(
                    db, organization_id=organization_id, store_id=store_id,
                )
                active.update(
                    item["control"] for item in report["subprocessors"]
                    if item["activation"] in _ACTIVE_STATES
                )
            return active
    except Exception:
        return set(PROCESSOR_CONTROLS)


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
    attestations = evaluate_privacy_program_attestations(
        environment=env, active_processor_controls=_active_processor_controls(db),
    )
    execution = live_execution_configured(env, attestations["policy_sha256"])
    blockers = privacy_release_blockers(
        attestations=attestations, execution=execution, signed_receipts=signed,
    )
    intake_integrity_ok = (
        hmac_configured
        and encrypted_selectors_configured
        and incomplete == 0
        and unauthorized_completion_states == 0
        and signed == received
        and prepared_audit == received
    )
    # Active tombstones are expected after a real redaction; they still ask
    # for review but do not by themselves revoke program release readiness.
    review_required = not intake_integrity_ok or suppression_counts["active"] > 0
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
        "released_shopify_subscription_verified": attestations["subscriptions_verified"],
        "valid_live_shopify_delivery_verified": (
            "REAL_SHOPIFY_DELIVERY_NOT_VERIFIED_BY_THIS_AUDIT" not in blockers
        ),
        # Program-level readiness only: an individual request is fulfilled
        # solely through its own permitted, audited execution.
        "data_export_or_erasure_fulfilled": False,
        "attestation_public_key_configured": attestations["public_key_configured"],
        "attestation_states": {
            name: value["state"] for name, value in attestations["controls"].items()
        },
        # Blockers clear only through signed, unexpired, policy-bound
        # attestations made outside the app plus live execution configuration.
        "privacy_fulfillment_release_ready": not blockers and intake_integrity_ok,
        "privacy_fulfillment_release_blockers": blockers,
        "review_required": review_required,
    }


def main() -> None:
    with SessionLocal() as db:
        report = summarize_shopify_privacy_operations(db)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
