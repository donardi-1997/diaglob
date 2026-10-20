"""Fail-closed assessment of proposed Shopify privacy retention decisions.

The inputs are constrained, non-PII decision metadata. Nothing is persisted,
signed, accepted as legal approval, or used to trigger export or deletion.
An artifact SHA-256 is merely a submitted reference, not verified evidence.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .shopify_privacy_controls import RETENTION_CONTROLS

_SHA256 = r"^[0-9a-f]{64}$"
_CATEGORY = r"^[a-z_]{1,48}$"
_JURISDICTION = r"^[A-Z]{2}(?:-[A-Z0-9]{1,8})?$"


class RetentionDecisionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: str = Field(pattern=_CATEGORY, max_length=48)
    jurisdiction: str | None = Field(default=None, pattern=_JURISDICTION, max_length=11)
    purpose_evidence_sha256: str | None = Field(default=None, pattern=_SHA256)
    legal_basis_evidence_sha256: str | None = Field(default=None, pattern=_SHA256)
    retention_days: int | None = Field(default=None, ge=0, le=36500)
    start_event_evidence_sha256: str | None = Field(default=None, pattern=_SHA256)
    retention_start_event: Literal[
        "not_defined", "collection", "last_interaction", "order_completed",
        "contract_ended", "request_received", "other_documented",
    ] = "not_defined"
    statutory_exception: Literal["not_reviewed", "none", "documented"] = "not_reviewed"
    statutory_exception_evidence_sha256: str | None = Field(default=None, pattern=_SHA256)
    legal_hold: Literal["not_reviewed", "none", "active"] = "not_reviewed"
    legal_hold_evidence_sha256: str | None = Field(default=None, pattern=_SHA256)
    disposition: Literal[
        "undecided", "erase", "anonymize", "minimize_and_restrict",
        "retain_required_minimum",
    ] = "undecided"
    minimum_data_evidence_sha256: str | None = Field(default=None, pattern=_SHA256)
    processors_evidence_sha256: str | None = Field(default=None, pattern=_SHA256)
    backups_evidence_sha256: str | None = Field(default=None, pattern=_SHA256)
    independent_signoff_sha256: str | None = Field(default=None, pattern=_SHA256)


class RetentionPolicyDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    categories: list[RetentionDecisionDraft] = Field(
        default_factory=list, max_length=len(RETENTION_CONTROLS),
    )


class RetentionReviewError(ValueError):
    """Error codes without caller-supplied values or personal information."""


def _category_gaps(item: RetentionDecisionDraft) -> list[str]:
    gaps = []
    if item.jurisdiction is None:
        gaps.append("JURISDICTION_NOT_SPECIFIED")
    if item.purpose_evidence_sha256 is None:
        gaps.append("PROCESSING_PURPOSE_EVIDENCE_MISSING")
    if item.legal_basis_evidence_sha256 is None:
        gaps.append("LEGAL_BASIS_EVIDENCE_MISSING")
    if item.retention_days is None:
        gaps.append("RETENTION_PERIOD_NOT_SPECIFIED")
    if item.retention_start_event == "not_defined":
        gaps.append("RETENTION_START_EVENT_NOT_SPECIFIED")
    if item.retention_start_event == "other_documented" and item.start_event_evidence_sha256 is None:
        gaps.append("CUSTOM_START_EVENT_EVIDENCE_MISSING")
    if item.statutory_exception == "not_reviewed":
        gaps.append("STATUTORY_EXCEPTION_NOT_REVIEWED")
    elif item.statutory_exception == "documented" and item.statutory_exception_evidence_sha256 is None:
        gaps.append("STATUTORY_EXCEPTION_EVIDENCE_MISSING")
    if item.legal_hold == "not_reviewed":
        gaps.append("LEGAL_HOLD_NOT_REVIEWED")
    elif item.legal_hold == "active":
        gaps.append("LEGAL_HOLD_ACTIVE_NO_ERASURE_AUTHORIZATION")
        if item.legal_hold_evidence_sha256 is None:
            gaps.append("LEGAL_HOLD_EVIDENCE_MISSING")
    if item.disposition == "undecided":
        gaps.append("DISPOSITION_NOT_SPECIFIED")
    if item.minimum_data_evidence_sha256 is None:
        gaps.append("MINIMUM_DATA_EVIDENCE_MISSING")
    if item.processors_evidence_sha256 is None:
        gaps.append("PROCESSOR_EVIDENCE_MISSING")
    if item.backups_evidence_sha256 is None:
        gaps.append("BACKUP_RECONCILIATION_EVIDENCE_MISSING")
    if item.independent_signoff_sha256 is None:
        gaps.append("INDEPENDENT_SIGNOFF_REFERENCE_MISSING")
    # Deliberate release gate: a submitted digest is NOT an independently
    # checked signature or legal assessment. Never auto-approve such a draft.
    gaps.append("INDEPENDENT_LEGAL_APPROVAL_NOT_VERIFIED")
    gaps.append("LIVE_ERASURE_WORKFLOW_NOT_AUTHORIZED")
    return gaps


def assess_shopify_retention_policy_draft(draft: RetentionPolicyDraft) -> dict:
    """Return stable gap codes only. Do not echo metadata or evidence hashes."""
    declared = {name: owner for name, owner, _ in RETENTION_CONTROLS}
    seen: dict[str, RetentionDecisionDraft] = {}
    for item in draft.categories:
        if item.category not in declared:
            raise RetentionReviewError("UNKNOWN_RETENTION_CATEGORY")
        if item.category in seen:
            raise RetentionReviewError("DUPLICATE_RETENTION_CATEGORY")
        seen[item.category] = item
    evaluations = []
    for category, owner, _ in RETENTION_CONTROLS:
        item = seen.get(category)
        evaluations.append({
            "category": category,
            "review_owner": owner,
            "provided": item is not None,
            "gap_codes": (
                _category_gaps(item) if item is not None
                else ["RETENTION_CATEGORY_DRAFT_MISSING"]
            ),
            "independently_approved": False,
            "destruction_authorized": False,
        })
    return {
        "assessment_type": "shopify_retention_policy_draft_review_only",
        "schema_version": 1,
        "category_count": len(evaluations),
        "submitted_category_count": len(seen),
        "categories": evaluations,
        "evidence_independently_verified": False,
        "policy_approved": False,
        "live_export_authorized": False,
        "live_erasure_authorized": False,
        "fulfillment_complete": False,
    }
