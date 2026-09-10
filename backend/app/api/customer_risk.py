"""Customer-risk HTTP endpoints.

Cross-account responses expose only aggregate caution signals. Reporter identity,
private notes, and evidence from other organizations are never returned.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..services.customer_risk_service import (
    CustomerRiskAccessError,
    CustomerRiskConfigurationError,
    CustomerRiskNotFoundError,
    CustomerRiskValidationError,
    dismiss_current_organization_report,
    get_customer_risk_summary,
    report_customer,
)
from .deps import get_allowed_store_ids, require_permission


router = APIRouter()


class CustomerRiskReportCreate(BaseModel):
    reason: Literal[
        "suspected_fraud",
        "payment_abuse",
        "delivery_claim",
        "identity_mismatch",
        "abusive_behavior",
        "other",
    ]
    notes: str | None = Field(default=None, max_length=2000)
    evidence_reference: str | None = Field(default=None, max_length=1000)
    store_id: int | None = None


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, CustomerRiskNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, CustomerRiskAccessError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, CustomerRiskConfigurationError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, CustomerRiskValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/api/customers/{customer_id}/risk")
def get_customer_risk(
    customer_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("customers.read")
    ),
    db: Session = Depends(get_db),
):
    try:
        return get_customer_risk_summary(
            db=db,
            organization_id=membership.organization_id,
            customer_id=customer_id,
            allowed_store_ids=get_allowed_store_ids(membership),
        )
    except (
        CustomerRiskNotFoundError,
        CustomerRiskAccessError,
        CustomerRiskConfigurationError,
        CustomerRiskValidationError,
    ) as exc:
        _raise_service_error(exc)


@router.post("/api/customers/{customer_id}/risk/reports")
def create_customer_risk_report(
    customer_id: int,
    payload: CustomerRiskReportCreate,
    membership: OrganizationMembership = Depends(
        require_permission("customers.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return report_customer(
            db=db,
            organization_id=membership.organization_id,
            reporter_user_id=membership.user_id,
            customer_id=customer_id,
            reason=payload.reason,
            notes=payload.notes,
            evidence_reference=payload.evidence_reference,
            reporter_store_id=payload.store_id,
            allowed_store_ids=get_allowed_store_ids(membership),
        )
    except (
        CustomerRiskNotFoundError,
        CustomerRiskAccessError,
        CustomerRiskConfigurationError,
        CustomerRiskValidationError,
    ) as exc:
        _raise_service_error(exc)


@router.delete("/api/customers/{customer_id}/risk/reports/mine")
def dismiss_customer_risk_report(
    customer_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("customers.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        return dismiss_current_organization_report(
            db=db,
            organization_id=membership.organization_id,
            reporter_user_id=membership.user_id,
            customer_id=customer_id,
            allowed_store_ids=get_allowed_store_ids(membership),
        )
    except (
        CustomerRiskNotFoundError,
        CustomerRiskAccessError,
        CustomerRiskConfigurationError,
        CustomerRiskValidationError,
    ) as exc:
        _raise_service_error(exc)
