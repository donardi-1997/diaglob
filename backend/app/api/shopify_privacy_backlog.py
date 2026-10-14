"""Internal authenticated, read-only Shopify privacy operational endpoints."""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.shopify_privacy_backlog import summarize_shopify_privacy_backlog
from ..services.shopify_privacy_case_queue import list_shopify_privacy_cases
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
    build_encrypted_local_customer_export,
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
    """Process an encrypted IN-MEMORY snapshot and return counts only.

    Ciphertext and content fingerprints are never returned via the API.
    This is not merchant delivery, archival storage, or request fulfillment.
    """
    _require_internal_secret(x_internal_secret)
    try:
        result = build_encrypted_local_customer_export(db, request_id=request_id)
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
