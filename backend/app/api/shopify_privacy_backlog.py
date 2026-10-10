"""Internal-only, read-only operational summary for Shopify privacy receipts."""
from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.shopify_privacy_backlog import summarize_shopify_privacy_backlog

router = APIRouter()


@router.get("/api/internal/shopify/privacy/backlog")
def get_shopify_privacy_backlog(
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    """Reject calls without the configured internal secret before querying DB."""
    expected = os.getenv("DIAGLOB_INTERNAL_SECRET")
    if (
        not expected
        or not x_internal_secret
        or not secrets.compare_digest(x_internal_secret, expected)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized internal request")
    return summarize_shopify_privacy_backlog(db).safe_dict()
