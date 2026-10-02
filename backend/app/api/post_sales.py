"""Post-sales case API."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..services.post_sales_service import (
    PostSalesNotFoundError,
    PostSalesValidationError,
    add_note,
    create_case,
    get_case,
    get_summary,
    list_cases,
    update_case,
)
from .deps import require_permission


router = APIRouter()


CaseType = Literal[
    "warranty",
    "return",
    "refund",
    "damaged",
    "wrong_product",
    "delivery_issue",
    "other",
]
CaseStatus = Literal[
    "open",
    "waiting_customer",
    "investigating",
    "approved",
    "rejected",
    "resolved",
    "closed",
]
CasePriority = Literal["low", "normal", "high", "urgent"]


class PostSalesCaseCreate(BaseModel):
    case_type: CaseType
    priority: CasePriority = "normal"
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=5000)
    order_id: int | None = Field(default=None, ge=1)
    customer_id: int | None = Field(default=None, ge=1)
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    source_channel: str | None = Field(default=None, max_length=30)


class PostSalesCaseUpdate(BaseModel):
    status: CaseStatus | None = None
    priority: CasePriority | None = None
    resolution: str | None = Field(default=None, max_length=5000)
    assigned_agent_id: int | None = Field(default=None, ge=1)
    note: str | None = Field(default=None, max_length=3000)


class PostSalesNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=3000)


def _raise_post_sales_error(exc: Exception) -> None:
    if isinstance(exc, PostSalesNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, PostSalesValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/api/stores/{store_id}/post-sales/summary")
def post_sales_summary(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("post_sales.read")),
    db: Session = Depends(get_db),
):
    try:
        return get_summary(db, membership.organization_id, store_id)
    except (PostSalesNotFoundError, PostSalesValidationError) as exc:
        _raise_post_sales_error(exc)


@router.get("/api/stores/{store_id}/post-sales/cases")
def post_sales_cases(
    store_id: int,
    status: str | None = None,
    case_type: str | None = None,
    priority: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    membership: OrganizationMembership = Depends(require_permission("post_sales.read")),
    db: Session = Depends(get_db),
):
    try:
        items = list_cases(
            db,
            membership.organization_id,
            store_id,
            status=status,
            case_type=case_type,
            priority=priority,
            limit=limit,
        )
        return {"items": items, "total": len(items)}
    except (PostSalesNotFoundError, PostSalesValidationError) as exc:
        _raise_post_sales_error(exc)


@router.post("/api/stores/{store_id}/post-sales/cases")
def create_post_sales_case(
    store_id: int,
    payload: PostSalesCaseCreate,
    membership: OrganizationMembership = Depends(require_permission("post_sales.write")),
    db: Session = Depends(get_db),
):
    try:
        return create_case(
            db,
            membership.organization_id,
            store_id,
            membership.user_id,
            payload.model_dump(),
        )
    except (PostSalesNotFoundError, PostSalesValidationError) as exc:
        _raise_post_sales_error(exc)


@router.get("/api/stores/{store_id}/post-sales/cases/{case_id}")
def get_post_sales_case(
    store_id: int,
    case_id: int,
    membership: OrganizationMembership = Depends(require_permission("post_sales.read")),
    db: Session = Depends(get_db),
):
    try:
        return get_case(db, membership.organization_id, store_id, case_id)
    except (PostSalesNotFoundError, PostSalesValidationError) as exc:
        _raise_post_sales_error(exc)


@router.patch("/api/stores/{store_id}/post-sales/cases/{case_id}")
def update_post_sales_case(
    store_id: int,
    case_id: int,
    payload: PostSalesCaseUpdate,
    membership: OrganizationMembership = Depends(require_permission("post_sales.write")),
    db: Session = Depends(get_db),
):
    try:
        return update_case(
            db,
            membership.organization_id,
            store_id,
            case_id,
            membership.user_id,
            payload.model_dump(exclude_unset=True),
        )
    except (PostSalesNotFoundError, PostSalesValidationError) as exc:
        _raise_post_sales_error(exc)


@router.post("/api/stores/{store_id}/post-sales/cases/{case_id}/notes")
def add_post_sales_note(
    store_id: int,
    case_id: int,
    payload: PostSalesNoteCreate,
    membership: OrganizationMembership = Depends(require_permission("post_sales.write")),
    db: Session = Depends(get_db),
):
    try:
        return add_note(
            db,
            membership.organization_id,
            store_id,
            case_id,
            membership.user_id,
            payload.note,
        )
    except (PostSalesNotFoundError, PostSalesValidationError) as exc:
        _raise_post_sales_error(exc)
