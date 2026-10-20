"""Internal authenticated, read-only Shopify privacy operational endpoints."""
from __future__ import annotations

import json
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.shopify_privacy_backlog import summarize_shopify_privacy_backlog
from ..services.shopify_privacy_inventory_report import (
    build_shopify_privacy_field_inventory,
    build_shopify_retention_review_template,
)
from ..services.shopify_privacy_retention_assessment import (
    RetentionPolicyDraft,
    RetentionReviewError,
    assess_shopify_retention_policy_draft,
)
from ..services.shopify_privacy_controls import (
    ShopifyPrivacyControlError,
    inspect_shopify_privacy_closure_controls,
    submit_shopify_privacy_control_evidence,
)
from ..services.shopify_privacy_delivery_readiness import (
    inspect_shopify_privacy_delivery_readiness,
)
from ..services.shopify_privacy_case_queue import list_shopify_privacy_cases
from ..services.shopify_privacy_escalations import list_shopify_privacy_escalations
from ..services.shopify_privacy_case_assessment import (
    ShopifyPrivacyAssessmentError,
    assess_shopify_privacy_case,
)
from ..services.shopify_privacy_suppression import (
    ShopifySuppressionError,
    prepare_shopify_privacy_suppressions,
    inspect_shopify_privacy_suppressions,
)
from ..services.shopify_privacy_local_processor import (
    ShopifyLocalPrivacyError,
    inspect_local_customer_export_counts,
    build_local_redaction_manifest,
)
from ..services.shopify_privacy_processing import (
    ShopifyPrivacyProcessingError,
    get_shopify_privacy_processing_case,
    prepare_shopify_privacy_processing_case,
    prepare_pending_shopify_privacy_processing_cases,
)

router = APIRouter()


def _require_internal_secret(value: str | None) -> None:
    """Authenticate before executing any database query or service call."""
    expected = os.getenv("DIAGLOB_INTERNAL_SECRET")
    if (
        not expected
        or not value
        or not secrets.compare_digest(value, expected)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized internal request")


@router.get("/api/internal/shopify/privacy/inventory")
def get_shopify_privacy_inventory(
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
):
    """Read schema shape only after authenticating; never select user data."""
    _require_internal_secret(x_internal_secret)
    return build_shopify_privacy_field_inventory()


@router.get("/api/internal/shopify/privacy/retention/template")
def get_shopify_privacy_retention_template(
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
):
    """Return blank legal decision requirements, not an approved policy."""
    _require_internal_secret(x_internal_secret)
    return build_shopify_retention_review_template()


@router.post("/api/internal/shopify/privacy/retention/assess")
async def assess_shopify_privacy_retention_draft(
    request: Request,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
):
    """Authenticate before bounded JSON parsing; never echo submitted details."""
    _require_internal_secret(x_internal_secret)
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="JSON_CONTENT_TYPE_REQUIRED")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 16_384:
            raise HTTPException(status_code=413, detail="RETENTION_DRAFT_TOO_LARGE")
    try:
        payload = json.loads(raw)
        draft = RetentionPolicyDraft.model_validate(payload)
    except (ValueError, TypeError, ValidationError) as exc:
        # Returning a framework validation exception can echo unsafe content.
        raise HTTPException(status_code=400, detail="INVALID_RETENTION_DRAFT") from exc
    try:
        return assess_shopify_retention_policy_draft(draft)
    except RetentionReviewError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/internal/shopify/privacy/backlog")
def get_shopify_privacy_backlog(
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Aggregate only, no subject identifiers or fulfillment claims."""
    _require_internal_secret(x_internal_secret)
    return summarize_shopify_privacy_backlog(db).safe_dict()


@router.get("/api/internal/shopify/privacy/cases")
def get_shopify_privacy_cases(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Bounded operational queue; never decrypt or export customer data."""
    _require_internal_secret(x_internal_secret)
    return list_shopify_privacy_cases(db, limit=limit, offset=offset)


@router.get("/api/internal/shopify/privacy/escalations")
def get_shopify_privacy_escalations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Alert operators to privacy obligations; metadata only, no fulfillment."""
    _require_internal_secret(x_internal_secret)
    return list_shopify_privacy_escalations(db, limit=limit, offset=offset)


@router.get("/api/internal/shopify/privacy/cases/{request_id}/assessment")
def get_shopify_privacy_case_assessment(
    request_id: str,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Read signed-intake and store-scoped evidence; never release subject data."""
    _require_internal_secret(x_internal_secret)
    try:
        assessment = assess_shopify_privacy_case(db, request_id=request_id)
    except ShopifyPrivacyAssessmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if assessment is None:
        raise HTTPException(status_code=404, detail="Privacy request not found")
    return assessment.safe_dict()


@router.post("/api/internal/shopify/privacy/cases/{request_id}/prepare")
def prepare_shopify_privacy_case(
    request_id: str,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Persist review tasks after signed intake; no PII export or erasure."""
    _require_internal_secret(x_internal_secret)
    try:
        result = prepare_shopify_privacy_processing_case(db, request_id=request_id)
    except ShopifyPrivacyProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Privacy request not found")
    return result


@router.get("/api/internal/shopify/privacy/cases/{request_id}/processing")
def get_shopify_privacy_case_processing(
    request_id: str,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Inspect per-source blockers without exposing selectors or PII."""
    _require_internal_secret(x_internal_secret)
    try:
        result = get_shopify_privacy_processing_case(db, request_id=request_id)
    except ShopifyPrivacyProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Privacy request not found")
    return result


@router.post("/api/internal/shopify/privacy/prepare-pending")
def prepare_pending_shopify_privacy_cases(
    limit: int = Query(20, ge=1, le=50),
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Create review work items for signed cases, in a bounded batch."""
    _require_internal_secret(x_internal_secret)
    try:
        return prepare_pending_shopify_privacy_processing_cases(db, limit=limit)
    except ShopifyPrivacyProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/internal/shopify/privacy/cases/{request_id}/local-export/inspect")
def inspect_shopify_local_customer_export(
    request_id: str,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Read only scoped record counts without constructing a PII snapshot.

    No message bodies, addresses or customer contact fields are selected.
    This is not merchant delivery or Shopify request fulfillment.
    """
    _require_internal_secret(x_internal_secret)
    try:
        result = inspect_local_customer_export_counts(db, request_id=request_id)
    except ShopifyLocalPrivacyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "request_id": result.request_id,
        "profiles": result.profiles,
        "orders": result.orders,
        "order_items": result.order_items,
        "conversations": result.conversations,
        "messages": result.messages,
        "checkouts": result.checkouts,
        "requested_orders_not_resolved": result.requested_orders_not_resolved,
        "automation": {
            "audience_members": result.automation_audience_members,
            "campaign_recipients": result.automation_campaign_recipients,
            "delivery_attempts": result.automation_delivery_attempts,
            "flow_recipients": result.automation_flow_recipients,
            "flow_node_executions": result.automation_flow_node_executions,
            "attribution": result.automation_attribution,
            "export_included": False,
            "coverage": "linked_records_only",
        },
        "complete": False,
        "merchant_delivery_allowed": False,
    }


@router.get("/api/internal/shopify/privacy/cases/{request_id}/local-redaction/manifest")
def get_shopify_local_redaction_manifest(
    request_id: str,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Describe candidate local fields without deleting customer information."""
    _require_internal_secret(x_internal_secret)
    try:
        result = build_local_redaction_manifest(db, request_id=request_id)
    except ShopifyLocalPrivacyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "request_id": result.request_id,
        "topic": result.topic,
        "fields_by_table": [
            {"table": name, "fields": list(fields), "candidate_rows": count}
            for name, fields, count in result.fields_by_table
        ],
        "shared_customer_records_protected": result.shared_customer_records_protected,
        "complete": False,
        "mutation_allowed": False,
    }


@router.post("/api/internal/shopify/privacy/cases/{request_id}/suppressions/prepare")
def prepare_shopify_privacy_suppression_case(
    request_id: str,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Stage keyed Shopify selectors without activating replay suppression."""
    _require_internal_secret(x_internal_secret)
    try:
        return prepare_shopify_privacy_suppressions(db, request_id=request_id)
    except ShopifySuppressionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/internal/shopify/privacy/cases/{request_id}/suppressions")
def get_shopify_privacy_suppression_case(
    request_id: str,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Return stage/active counts only; never hashed selectors or subject IDs."""
    _require_internal_secret(x_internal_secret)
    try:
        return inspect_shopify_privacy_suppressions(db, request_id=request_id)
    except ShopifySuppressionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class PrivacyEvidenceSubmission(BaseModel):
    artifact_sha256: str


@router.get("/api/internal/shopify/privacy/cases/{request_id}/controls")
def get_shopify_privacy_controls(
    request_id: str,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Return open legal, subprocessor and recovery decisions without PII."""
    _require_internal_secret(x_internal_secret)
    try:
        return inspect_shopify_privacy_closure_controls(db, request_id=request_id)
    except ShopifyPrivacyControlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/internal/shopify/privacy/cases/{request_id}/controls/{control}/evidence")
def submit_shopify_privacy_evidence(
    request_id: str,
    control: str,
    body: PrivacyEvidenceSubmission,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Record only external artifact digest. No approval or completion claim."""
    _require_internal_secret(x_internal_secret)
    try:
        return submit_shopify_privacy_control_evidence(
            db, request_id=request_id,
            control=control, artifact_sha256=body.artifact_sha256,
        )
    except ShopifyPrivacyControlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/internal/shopify/privacy/cases/{request_id}/delivery-readiness")
def get_shopify_privacy_delivery_readiness(
    request_id: str,
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Return only unresolved retention and secure-delivery gates, never PII."""
    _require_internal_secret(x_internal_secret)
    try:
        return inspect_shopify_privacy_delivery_readiness(db, request_id=request_id)
    except ShopifyPrivacyControlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
