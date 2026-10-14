"""Durable, PII-free processing work queue for Shopify privacy requests.

This is the operational handoff after signed webhook intake, NOT customer-data
export, erasure, delivery, legal clearance, or Shopify fulfillment. All unverified
processors remain blocked; no endpoint in this module can mark a case complete.
"""
from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    ShopifyPrivacyAuditEvent,
    ShopifyPrivacyRequest,
    ShopifyPrivacyWorkItem,
)
from .shopify_privacy_case_assessment import (
    ShopifyPrivacyAssessmentError,
    assess_shopify_privacy_case,
)

_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")
_COMMON_AREAS = (
    "signed_receipt",
    "shop_identity",
    "subject_linkage",
    "local_structured_records",
    "ai_and_unstructured_content",
    "automation_and_queues",
    "external_processors",
    "retention_and_legal_holds",
    "backups_and_reingestion",
)


class ShopifyPrivacyProcessingError(ValueError):
    """Operational failure expressed as a non-sensitive machine-readable code."""


def _validate_id(request_id: str) -> None:
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ShopifyPrivacyProcessingError("INVALID_PRIVACY_REQUEST_ID")


def _serialize(receipt: ShopifyPrivacyRequest, items: list[ShopifyPrivacyWorkItem],
               *, created: bool) -> dict:
    return {
        "request_id": receipt.request_id,
        "topic": receipt.topic,
        "created": created,
        "work_items": [
            {
                "area": item.area,
                "action": item.action,
                "status": item.status,
                "blocker_code": item.blocker_code,
            }
            for item in sorted(items, key=lambda x: x.area)
        ],
        "fulfillment_authorized": False,
        "fulfillment_complete": False,
        "requires_manual_review": True,
    }


def get_shopify_privacy_processing_case(
    db: Session, *, request_id: str,
) -> dict | None:
    """Read processing status without decrypting selectors or returning PII."""
    _validate_id(request_id)
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).first()
    if receipt is None:
        return None
    items = db.query(ShopifyPrivacyWorkItem).filter(
        ShopifyPrivacyWorkItem.request_id == request_id,
    ).all()
    return _serialize(receipt, items, created=False)


def _task_specs(topic: str, *, verified_scope: bool, signed: bool):
    action = "export" if topic == "customers/data_request" else "redact"
    specs = {
        "signed_receipt": ("verify", "verified" if signed else "blocked",
                           None if signed else "SIGNED_INTAKE_EVIDENCE_MISSING"),
        "shop_identity": ("verify", "verified" if verified_scope else "blocked",
                          None if verified_scope else "SHOP_SCOPE_NOT_VERIFIED"),
        "subject_linkage": (action,
                            "review_required" if verified_scope else "blocked",
                            "FIELD_LEVEL_SUBJECT_LINKAGE_REQUIRED" if verified_scope
                            else "SUBJECT_OR_STORE_UNRESOLVED"),
        "local_structured_records": (action, "blocked", "RECORD_PROVENANCE_INCOMPLETE"),
        "ai_and_unstructured_content": (action, "blocked", "UNSTRUCTURED_SUBJECT_LINKAGE_UNVERIFIED"),
        "automation_and_queues": (action, "blocked", "QUEUED_PAYLOAD_COVERAGE_UNVERIFIED"),
        "external_processors": (action, "blocked", "EXTERNAL_PROCESSOR_COVERAGE_UNVERIFIED"),
        "retention_and_legal_holds": ("review", "blocked", "LEGAL_RETENTION_POLICY_NOT_APPROVED"),
        "backups_and_reingestion": (action, "blocked", "BACKUP_RESTORE_COVERAGE_UNVERIFIED"),
    }
    if topic == "customers/data_request":
        specs["merchant_delivery"] = ("deliver", "blocked", "SECURE_DELIVERY_NOT_AUTHORIZED")
    else:
        specs["reimport_suppression"] = ("suppress", "blocked", "SUPPRESSION_LEDGER_NOT_VERIFIED")
    return specs



def stage_shopify_privacy_receipt_work_items(
    db: Session, receipt: ShopifyPrivacyRequest,
) -> None:
    """Stage review-only work in the *same transaction* as signed webhook intake.

    This makes no customer/store lookups and does not call any provider:
    Shopify must receive an HTTP acknowledgement within five seconds.
    The signed receipt, audit and ten blocked tasks commit atomically.
    """
    if receipt.topic not in {
        "customers/data_request", "customers/redact", "shop/redact",
    }:
        raise ShopifyPrivacyProcessingError("UNSUPPORTED_PRIVACY_TOPIC")
    specs = _task_specs(receipt.topic, verified_scope=False, signed=True)
    now = datetime.utcnow()
    for area, (action, status, blocker) in specs.items():
        db.add(ShopifyPrivacyWorkItem(
            request_id=receipt.request_id,
            area=area,
            action=action,
            status=status,
            blocker_code=blocker,
            created_at=now,
            updated_at=now,
        ))
    db.add(ShopifyPrivacyAuditEvent(
        request_id=receipt.request_id,
        event_type="processing_prepared",
        from_status=receipt.status,
        to_status=receipt.status,
        reason_code="signed_receipt_tasks_staged_without_data_access",
        actor_type="internal_privacy_processor",
        created_at=now,
    ))


def ensure_shopify_privacy_receipt_work_items(
    db: Session, receipt: ShopifyPrivacyRequest,
) -> None:
    """Repair a committed legacy receipt on retry, without duplicate tasks.

    A partially populated queue is not accepted as ready: return an error so
    operators can investigate rather than acknowledging a broken GDPR case.
    """
    specs = _task_specs(receipt.topic, verified_scope=False, signed=True)
    existing = db.query(ShopifyPrivacyWorkItem).filter(
        ShopifyPrivacyWorkItem.request_id == receipt.request_id,
    ).all()
    if existing:
        if len(existing) != len(specs) or {x.area for x in existing} != set(specs):
            raise ShopifyPrivacyProcessingError("INCOMPLETE_PRIVACY_WORK_ITEM_SET")
        return
    signed = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == receipt.request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first()
    if signed is None:
        raise ShopifyPrivacyProcessingError("SIGNED_INTAKE_EVIDENCE_MISSING")
    stage_shopify_privacy_receipt_work_items(db, receipt)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        saved = db.query(ShopifyPrivacyWorkItem).filter(
            ShopifyPrivacyWorkItem.request_id == receipt.request_id,
        ).all()
        if len(saved) != len(specs) or {x.area for x in saved} != set(specs):
            raise ShopifyPrivacyProcessingError("PRIVACY_WORK_ITEM_CONFLICT")




def prepare_shopify_privacy_processing_case(
    db: Session, *, request_id: str,
) -> dict | None:
    """Create one durable task per data surface, atomically and idempotently.

    Only signed requests are eligible. A resolved store identity is marked
    verified, but *never* interpreted as fulfillment permission. An unresolved
    store/subject becomes an explicit blocker, not a guessed identity. Retries
    return the same tasks and do not create a second audit event.
    """
    _validate_id(request_id)
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).with_for_update().first()
    if receipt is None:
        return None

    try:
        assessment = assess_shopify_privacy_case(db, request_id=request_id)
    except ShopifyPrivacyAssessmentError as exc:
        raise ShopifyPrivacyProcessingError("CASE_ASSESSMENT_REJECTED") from exc
    if assessment is None or not assessment.verified_signed_intake:
        raise ShopifyPrivacyProcessingError("SIGNED_INTAKE_EVIDENCE_MISSING")
    if receipt.topic not in {
        "customers/data_request", "customers/redact", "shop/redact",
    }:
        raise ShopifyPrivacyProcessingError("UNSUPPORTED_PRIVACY_TOPIC")

    if receipt.completed_at is not None or receipt.status == "completed":
        raise ShopifyPrivacyProcessingError("HISTORICAL_COMPLETION_REQUIRES_REVIEW")

    specs = _task_specs(
        receipt.topic, verified_scope=assessment.verified_shop_scope,
        signed=assessment.verified_signed_intake,
    )
    existing = db.query(ShopifyPrivacyWorkItem).filter(
        ShopifyPrivacyWorkItem.request_id == request_id,
    ).all()
    if existing:
        if len(existing) != len(specs) or {x.area for x in existing} != set(specs):
            raise ShopifyPrivacyProcessingError("INCOMPLETE_PRIVACY_WORK_ITEM_SET")
        # Lightweight webhook intake intentionally avoids tenant queries.
        # After an independent, signed scope assessment, promote only
        # identity evidence (not export/redaction/legal clearance).
        if assessment.verified_shop_scope:
            current = {item.area: item for item in existing}
            updates = (
                ("shop_identity", "blocked", "SHOP_SCOPE_NOT_VERIFIED",
                 "verified", None),
                ("subject_linkage", "blocked", "SUBJECT_OR_STORE_UNRESOLVED",
                 "review_required", "FIELD_LEVEL_SUBJECT_LINKAGE_REQUIRED"),
            )
            changed = False
            for area, old_status, old_blocker, new_status, new_blocker in updates:
                item = current[area]
                if item.status == old_status and item.blocker_code == old_blocker:
                    item.status = new_status
                    item.blocker_code = new_blocker
                    item.updated_at = datetime.utcnow()
                    changed = True
            if changed:
                db.commit()
        return _serialize(receipt, existing, created=False)
    now = datetime.utcnow()
    items = [
        ShopifyPrivacyWorkItem(
            request_id=request_id,
            area=area,
            action=specs[area][0],
            status=specs[area][1],
            blocker_code=specs[area][2],
            created_at=now,
            updated_at=now,
        )
        for area in (*_COMMON_AREAS, "merchant_delivery" if
                     receipt.topic == "customers/data_request" else "reimport_suppression")
    ]
    db.add_all(items)
    db.add(ShopifyPrivacyAuditEvent(
        request_id=request_id,
        event_type="processing_prepared",
        from_status=receipt.status,
        to_status=receipt.status,
        reason_code="source_tasks_initialized",
        actor_type="internal_privacy_processor",
        created_at=now,
    ))
    try:
        db.commit()
    except IntegrityError:
        # Parallel operators cannot produce duplicate tasks; only accept an
        # idempotent retry after the other transaction committed a full set.
        db.rollback()
        saved = db.query(ShopifyPrivacyWorkItem).filter(
            ShopifyPrivacyWorkItem.request_id == request_id,
        ).all()
        if len(saved) != len(specs):
            raise ShopifyPrivacyProcessingError("PRIVACY_WORK_ITEM_CONFLICT")
        return _serialize(receipt, saved, created=False)
    return _serialize(receipt, items, created=True)


def prepare_pending_shopify_privacy_processing_cases(
    db: Session, *, limit: int = 20,
) -> dict:
    """Create bounded work queues for signed requests not yet prepared."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ShopifyPrivacyProcessingError("INVALID_PRIVACY_BATCH_LIMIT")
    signed = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == ShopifyPrivacyRequest.request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).exists()
    prepared = db.query(ShopifyPrivacyWorkItem.id).filter(
        ShopifyPrivacyWorkItem.request_id == ShopifyPrivacyRequest.request_id,
    ).exists()
    candidates = db.query(ShopifyPrivacyRequest.request_id).filter(
        signed, ~prepared,
    ).order_by(
        ShopifyPrivacyRequest.created_at, ShopifyPrivacyRequest.id,
    ).limit(limit).all()

    created = 0
    errors = []
    for (opaque_id,) in candidates:
        try:
            result = prepare_shopify_privacy_processing_case(
                db, request_id=opaque_id,
            )
            if result and result["created"]:
                created += 1
        except ShopifyPrivacyProcessingError as exc:
            errors.append({"request_id": opaque_id, "code": str(exc)})
    return {
        "examined": len(candidates),
        "created": created,
        "errors": errors,
        "fulfillment_complete": False,
    }
