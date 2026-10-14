"""Evidence-only legal/processor/backup privacy coverage registry.

A submitted artifact digest is NOT legal approval, provider confirmation,
successful erasure, customer delivery or completed GDPR fulfillment.
All requests remain open unless an independent, audited completion workflow
is developed and approved.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyRequest, ShopifyPrivacyAuditEvent, ShopifyPrivacyControlEvidence

_REQUEST_ID = re.compile(r"^[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Required decision units; no retention duration is inferred from geography.
# Specific legal basis, regional tax obligations, processor contract and
# legal hold must be reviewed per store before an actual mutation.
RETENTION_CONTROLS = (
    ("customer_contact", "privacy_counsel", "delete_or_anonymize_after_review"),
    ("financial_orders", "legal_finance", "minimize_pii_and_retain_required_records"),
    ("shipping_and_returns", "legal_operations", "separate_delivery_from_ledger"),
    ("conversations", "privacy_counsel", "redact_free_text_and_attachments"),
    ("automations_and_ai", "privacy_engineering", "unlink_subject_and_derived_data"),
    ("logs_and_audit", "security_legal", "minimal_access_controlled_retention"),
)
PROCESSOR_CONTROLS = (
    "whatsapp_provider", "instagram_messaging", "email_delivery",
    "cj_supplier", "dropi_supplier", "advertising_meta",
    "aws_bedrock", "files_and_object_storage",
)
RESTORE_CONTROLS = (
    "async_automation_queues", "provider_replay", "database_backups",
    "object_storage_backups", "restore_reconciliation", "tombstone_offsite_ledger",
)
DELIVERY_CONTROLS = ("merchant_identity", "secure_delivery", "closure_audit")

ALL_CONTROLS = frozenset(
    [name for name, _, _ in RETENTION_CONTROLS]
    + list(PROCESSOR_CONTROLS) + list(RESTORE_CONTROLS)
    + list(DELIVERY_CONTROLS)
)


class ShopifyPrivacyControlError(ValueError):
    """PII-free control registry failure."""


def _verified_request(db: Session, request_id: str) -> ShopifyPrivacyRequest:
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise ShopifyPrivacyControlError("INVALID_PRIVACY_REQUEST_ID")
    request = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).first()
    if request is None:
        raise ShopifyPrivacyControlError("PRIVACY_REQUEST_NOT_FOUND")
    received = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first()
    if received is None:
        raise ShopifyPrivacyControlError("SIGNED_INTAKE_REQUIRED")
    return request


def submit_shopify_privacy_control_evidence(
    db: Session, *, request_id: str, control: str, artifact_sha256: str,
) -> dict:
    """Append proof reference for subsequent independent validation.

    Only an opaque digest of an externally controlled evidence artifact is
    stored; the underlying document must not contain raw selectors in logs.
    No claim of verified deletion or legal approval is possible through API.
    """
    request = _verified_request(db, request_id)
    if control not in ALL_CONTROLS:
        raise ShopifyPrivacyControlError("UNKNOWN_PRIVACY_CONTROL")
    if not isinstance(artifact_sha256, str) or not _SHA256.fullmatch(artifact_sha256):
        raise ShopifyPrivacyControlError("INVALID_EVIDENCE_DIGEST")
    existing = db.query(ShopifyPrivacyControlEvidence.id).filter(
        ShopifyPrivacyControlEvidence.request_id == request_id,
        ShopifyPrivacyControlEvidence.control == control,
        ShopifyPrivacyControlEvidence.artifact_sha256 == artifact_sha256,
    ).first()
    if existing is not None:
        return {"request_id": request_id, "control": control,
                "recorded": False, "verified": False}
    db.add(ShopifyPrivacyControlEvidence(
        request_id=request_id, control=control,
        artifact_sha256=artifact_sha256,
        status="submitted_unverified", created_at=datetime.utcnow(),
    ))
    db.add(ShopifyPrivacyAuditEvent(
        request_id=request_id, event_type="control_evidence_submitted",
        from_status=request.status, to_status=request.status,
        reason_code="external_evidence_unverified",
        actor_type="internal_privacy_processor", created_at=datetime.utcnow(),
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ShopifyPrivacyControlError("CONTROL_EVIDENCE_CONFLICT")
    return {"request_id": request_id, "control": control,
            "recorded": True, "verified": False}


def inspect_shopify_privacy_closure_controls(
    db: Session, *, request_id: str,
) -> dict:
    request = _verified_request(db, request_id)
    evidence = db.query(ShopifyPrivacyControlEvidence).filter(
        ShopifyPrivacyControlEvidence.request_id == request_id,
    ).all()
    submitted = {row.control for row in evidence}
    days_remaining = max(0, (request.created_at + timedelta(days=30)
                             - datetime.utcnow()).days)
    return {
        "request_id": request_id,
        "topic": request.topic,
        "days_remaining_for_shopify_response": days_remaining,
        "retention_policy": [{
            "category": name, "review_owner": owner,
            "proposed_handling": action,
            "review_state": "legal_approval_required",
            "evidence_submitted": name in submitted,
            "destruction_authorized": False,
        } for name, owner, action in RETENTION_CONTROLS],
        "external_processors": [{
            "control": name, "state": "verification_required",
            "evidence_submitted": name in submitted,
        } for name in PROCESSOR_CONTROLS],
        "backup_and_replay": [{
            "control": name, "state": "verification_required",
            "evidence_submitted": name in submitted,
        } for name in RESTORE_CONTROLS],
        "secure_delivery": [{
            "control": name, "state": "verification_required",
            "evidence_submitted": name in submitted,
        } for name in DELIVERY_CONTROLS],
        "submitted_artifacts": len(evidence),
        "validated_artifacts": 0,
        "retention_approved": False,
        "external_erasure_verified": False,
        "restore_verified": False,
        "closure_ready": False,
        "fulfillment_complete": False,
    }
