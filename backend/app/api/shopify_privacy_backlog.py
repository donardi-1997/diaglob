"""Internal authenticated, read-only Shopify privacy operational endpoints."""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.shopify_privacy_backlog import summarize_shopify_privacy_backlog
from ..services.shopify_privacy_case_queue import list_shopify_privacy_cases

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
