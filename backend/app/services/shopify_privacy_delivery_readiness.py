"""Fail-closed privacy retention and delivery readiness assessment.

This module returns only control identifiers and approval gaps. A submitted
artifact (even one incorrectly marked verified) does not authorize delivery.
There is no recipient-token generation, artifact storage, download endpoint,
approval transition, or fulfillment completion in this module.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyControlEvidence
from .shopify_privacy_case_assessment import (
    ShopifyPrivacyAssessmentError, assess_shopify_privacy_case,
)
from .shopify_privacy_controls import (
    DELIVERY_CONTROLS, PROCESSOR_CONTROLS, RESTORE_CONTROLS,
    RETENTION_CONTROLS, ShopifyPrivacyControlError, _verified_request,
)

# Each safeguard must be implemented and independently verified before a
# production delivery path can be designed. No self-attestation is accepted.
DELIVERY_SAFEGUARDS = (
    "authenticated_merchant_recipient",
    "recipient_tenant_and_shop_binding",
    "encrypted_artifact_at_rest",
    "short_lived_single_use_download",
    "authenticated_access_and_revocation",
    "minimal_audit_without_personal_data",
    "scheduled_artifact_purge",
    "independent_delivery_confirmation",
)


def inspect_shopify_privacy_delivery_readiness(
    db: Session, *, request_id: str,
) -> dict:
    """Inspect signed Shopify access request and unresolved release gates.

    Evidence is diagnostic only. The result cannot contain ciphertext,
    customer selectors, merchant email, an artifact URL, or a delivery token.
    """
    receipt = _verified_request(db, request_id)
    if receipt.topic != "customers/data_request":
        raise ShopifyPrivacyControlError("CUSTOMER_EXPORT_TOPIC_REQUIRED")
    try:
        assessment = assess_shopify_privacy_case(db, request_id=request_id)
    except ShopifyPrivacyAssessmentError as exc:
        raise ShopifyPrivacyControlError("INVALID_PRIVACY_REQUEST_ID") from exc
    if assessment is None or not assessment.verified_signed_intake:
        raise ShopifyPrivacyControlError("SIGNED_INTAKE_REQUIRED")

    evidence = db.query(ShopifyPrivacyControlEvidence.control).filter(
        ShopifyPrivacyControlEvidence.request_id == request_id,
    ).distinct().all()
    submitted = {row[0] for row in evidence}
    retention_names = tuple(name for name, _, _ in RETENTION_CONTROLS)
    requested = (
        retention_names + PROCESSOR_CONTROLS
        + RESTORE_CONTROLS + DELIVERY_CONTROLS
    )
    # A digest submission or an arbitrary DB status is not independent
    # sign-off. Until an audited approval transition exists, every control
    # is unverified, even when a digest has been submitted.
    controls = [
        {
            "control": name,
            "evidence_submitted": name in submitted,
            "independently_verified": False,
        }
        for name in requested
    ]
    blockers = list(assessment.blockers)
    blockers.extend([
        "RETENTION_SCHEDULE_AND_LEGAL_HOLDS_UNAPPROVED",
        "SUBPROCESSOR_AND_BACKUP_COVERAGE_UNVERIFIED",
        "MERCHANT_RECIPIENT_IDENTITY_UNVERIFIED",
        "SECURE_DELIVERY_TRANSPORT_NOT_IMPLEMENTED",
        "EXPORT_EXPIRY_PURGE_AND_REVOCATION_UNVERIFIED",
        "INDEPENDENT_EVIDENCE_SIGNOFF_NOT_IMPLEMENTED",
    ])
    if not assessment.verified_shop_scope:
        blockers.append("SHOPIFY_SUBJECT_OR_SHOP_NOT_VERIFIED")
    if receipt.completed_at is not None or receipt.status == "completed":
        blockers.append("HISTORICAL_COMPLETION_REQUIRES_REVIEW")
    return {
        "request_id": request_id,
        "topic": receipt.topic,
        "signed_intake_verified": assessment.verified_signed_intake,
        "shop_scope_verified": assessment.verified_shop_scope,
        "retention_controls": controls[:len(retention_names)],
        "processor_controls": controls[
            len(retention_names):len(retention_names) + len(PROCESSOR_CONTROLS)
        ],
        "backup_controls": controls[
            len(retention_names) + len(PROCESSOR_CONTROLS):
            len(retention_names) + len(PROCESSOR_CONTROLS) + len(RESTORE_CONTROLS)
        ],
        "delivery_controls": controls[-len(DELIVERY_CONTROLS):],
        "required_delivery_safeguards": [
            {"name": name, "independently_verified": False}
            for name in DELIVERY_SAFEGUARDS
        ],
        "blockers": sorted(set(blockers)),
        "retention_approved": False,
        "secure_delivery_enabled": False,
        "delivery_authorized": False,
        "fulfillment_complete": False,
    }
