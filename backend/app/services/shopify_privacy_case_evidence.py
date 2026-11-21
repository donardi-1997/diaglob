"""Read-only, PII-free evidence summary across all Shopify privacy topics.

One receipt => ten mandatory work items. This module reports only cryptographic
intake provenance, local-step evidence and missing closure controls; it cannot
authorize export, delete data or certify global Shopify fulfillment.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..models import (
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyControlEvidence,
    ShopifyPrivacyDeliveryArtifact,
    ShopifyPrivacyRequest,
    ShopifyPrivacySuppression,
    ShopifyPrivacyWorkItem,
)
from .shopify_privacy_no_data import NO_DATA_STATUS, NO_DATA_EVENT
from .shopify_privacy_processing import _COMMON_AREAS

TOPICS = frozenset(("customers/data_request", "customers/redact", "shop/redact"))
_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_COMPLETION_STATES = frozenset(
    ("completed", "fulfilled", "delivered", "deleted", "erased")
)
_ACCEPTED_TASK_STATES = frozenset(
    ("blocked", "review_required", "verified", "not_applicable")
)


class ShopifyPrivacyCaseEvidenceError(ValueError):
    """Only stable errors without PII are surfaced."""


def expected_areas(topic: str) -> tuple[str, ...]:
    if topic not in TOPICS:
        raise ShopifyPrivacyCaseEvidenceError("UNSUPPORTED_PRIVACY_TOPIC")
    return (*_COMMON_AREAS, (
        "merchant_delivery" if topic == "customers/data_request"
        else "reimport_suppression"
    ))


def summarize_shopify_privacy_case_evidence(
    db: Session, *, request_id: str,
) -> dict | None:
    """Read-only report. Never decrypts selectors or includes merchant identities.

    An audit event is evidence a *local step was recorded*, not independent
    proof of coverage, Shopify fulfillment, or provider deletion.
    """
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ShopifyPrivacyCaseEvidenceError("INVALID_PRIVACY_REQUEST_ID")
    receipt = db.query(ShopifyPrivacyRequest).filter_by(
        request_id=request_id,
    ).first()
    if receipt is None:
        return None
    required = expected_areas(receipt.topic)
    tasks = db.query(ShopifyPrivacyWorkItem).filter_by(
        request_id=request_id,
    ).all()
    seen: dict[str, ShopifyPrivacyWorkItem] = {}
    duplicates: set[str] = set()
    for task in tasks:
        if task.area in seen:
            duplicates.add(task.area)
        seen[task.area] = task
    missing = sorted(set(required) - set(seen))
    unexpected = sorted(set(seen) - set(required))

    signed = db.query(ShopifyPrivacyAuditEvent.id).filter_by(
        request_id=request_id, event_type="received",
        actor_type="shopify_hmac_verified",
    ).first() is not None
    # Filter to fixed, non-sensitive event names. Do not return arbitrary
    # reason codes or event metadata controlled by other integrations.
    expected_events = (
        "processing_prepared", NO_DATA_EVENT, "local_export_prepared",
        "local_export_downloaded", "local_redaction_executed",
        "automation_redaction_executed", "knowledge_erasure_started",
        "knowledge_erasure_executed",
    )
    observed = {name: db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == name,
    ).first() is not None for name in expected_events}

    no_data_recorded = (
        receipt.topic == "shop/redact"
        and receipt.status == NO_DATA_STATUS
        and receipt.organization_id is None
        and receipt.store_id is None
        and receipt.completed_at is None
        and signed and observed[NO_DATA_EVENT]
        and len(tasks) == len(required)
        and not missing and not unexpected and not duplicates
        and all(task.status == "not_applicable" for task in tasks)
    )

    manual_completion_anomaly = (
        receipt.completed_at is not None or receipt.status == "completed"
        or any(
            task.status in _FORBIDDEN_COMPLETION_STATES
            or task.status not in _ACCEPTED_TASK_STATES
            for task in tasks
        )
    )
    controls_submitted = int(db.query(ShopifyPrivacyControlEvidence.id).filter_by(
        request_id=request_id,
    ).count())
    partial_artifacts = int(db.query(ShopifyPrivacyDeliveryArtifact.id).filter(
        ShopifyPrivacyDeliveryArtifact.request_id == request_id,
        ShopifyPrivacyDeliveryArtifact.synthetic_only.is_(False),
    ).count())
    staged_tombstones = int(db.query(ShopifyPrivacySuppression.id).filter(
        ShopifyPrivacySuppression.request_id == request_id,
        ShopifyPrivacySuppression.status == "staged",
    ).count())
    active_tombstones = int(db.query(ShopifyPrivacySuppression.id).filter(
        ShopifyPrivacySuppression.request_id == request_id,
        ShopifyPrivacySuppression.status == "active",
    ).count())

    # A mutable work-item row is not independent validation. The program has
    # no reviewed closure event yet; all unresolved areas stay non-certified.
    areas = []
    for area in required:
        item = seen.get(area)
        status = item.status if item is not None and item.status in _ACCEPTED_TASK_STATES else "missing_or_invalid"
        areas.append({
            "area": area,
            "recorded_status": status,
            "independently_verified_for_closure": False,
        })
    blockers = []
    if not signed:
        blockers.append("SIGNED_INTAKE_EVIDENCE_MISSING")
    if not observed["processing_prepared"]:
        blockers.append("PREPARATION_AUDIT_MISSING")
    if missing or unexpected or duplicates or len(tasks) != len(required):
        blockers.append("TEN_WORK_ITEM_INTEGRITY_FAILURE")
    if manual_completion_anomaly:
        blockers.append("UNAUTHORIZED_COMPLETION_STATE")
    if not no_data_recorded:
        blockers.extend(("INDEPENDENT_CASE_CLOSURE_NOT_IMPLEMENTED",
                         "EXTERNAL_SURFACES_NOT_INDEPENDENTLY_VERIFIED"))
    if receipt.topic == "customers/data_request":
        blockers.append("FULL_CONSOLIDATED_EXPORT_AND_MERCHANT_DELIVERY_UNVERIFIED")
    else:
        blockers.append("BACKUP_REPLAY_AND_EXTERNAL_ERASURE_UNVERIFIED")
        if observed["local_redaction_executed"] and not observed["automation_redaction_executed"]:
            blockers.append("AUTOMATION_REDACTION_EVIDENCE_MISSING")
        if observed["knowledge_erasure_started"] and not observed["knowledge_erasure_executed"]:
            blockers.append("KNOWLEDGE_ERASURE_INTERRUPTED_RECONCILIATION_REQUIRED")
    if receipt.topic == "shop/redact" and not no_data_recorded:
        if observed["local_redaction_executed"] and not observed["knowledge_erasure_executed"]:
            blockers.append("KNOWLEDGE_ERASURE_REQUIRED_AFTER_SQL")
        elif not observed["local_redaction_executed"]:
            blockers.append("LOCAL_SQL_REDACTION_NOT_RECORDED")

    return {
        "request_id": request_id, "topic": receipt.topic,
        "signed_intake_recorded": signed,
        "ten_item_queue_integrity": not missing and not unexpected
        and not duplicates and len(tasks) == len(required),
        "work_item_count": len(tasks), "areas": areas,
        "no_data_determination_recorded": no_data_recorded,
        "no_data_is_not_erasure": True,
        "local_export_partial_only": receipt.topic == "customers/data_request",
        "partial_export_artifact_count": partial_artifacts,
        "local_redaction_recorded": observed["local_redaction_executed"],
        "automation_redaction_recorded": observed["automation_redaction_executed"],
        "shop_knowledge_erasure_started": observed["knowledge_erasure_started"],
        "shop_knowledge_erasure_recorded": observed["knowledge_erasure_executed"],
        "staged_suppressions": staged_tombstones,
        "active_suppressions": active_tombstones,
        "submitted_control_evidence_count": controls_submitted,
        "independently_validated_control_evidence": False,
        "blockers": sorted(set(blockers)),
        "fulfillment_complete": False,
        "privacy_compliance_certified": False,
        "mutations_performed": False,
    }
