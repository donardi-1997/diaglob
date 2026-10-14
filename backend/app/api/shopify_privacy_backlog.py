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
