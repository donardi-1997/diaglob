"""Admin API router.

Platform-level internal dashboard for Diaglob founders/operators.
Requires platform_admin authorization.
"""
from __future__ import annotations

import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from .deps import get_current_user
from ..services.admin_dashboard_service import (
    get_admin_overview,
    get_attention_list,
    get_organization_detail,
    get_organization_list,
)
from ..services.admin_growth_service import get_admin_growth_metrics
from ..services.customer_risk_moderation_analytics_service import (
    get_customer_risk_moderation_analytics,
)
from ..services.customer_risk_moderation_service import (
    CustomerRiskModerationNotFoundError,
    CustomerRiskModerationValidationError,
    get_customer_risk_dispute_detail,
    get_customer_risk_moderation_report,
    get_customer_risk_moderation_stats,
    list_customer_risk_disputes,
    list_customer_risk_moderation_reports,
    moderate_customer_risk_report,
    resolve_customer_risk_dispute,
)

router = APIRouter(prefix="/api/admin")


class RiskReportModerationRequest(BaseModel):
    action: Literal["confirm", "dismiss", "mark_disputed", "reset_pending"]
    note: str = Field(min_length=5, max_length=2000)


class RiskDisputeResolutionRequest(BaseModel):
    outcome: Literal["accepted", "rejected"]
    note: str = Field(min_length=5, max_length=2000)


def _require_platform_admin(
    user: User = Depends(get_current_user),
) -> User:
    """Verify user is a platform admin."""
    admin_emails = {
        email.strip().lower()
        for email in os.getenv("PLATFORM_ADMIN_EMAILS", "").split(",")
        if email.strip()
    }

    if not user.email or user.email.lower() not in admin_emails:
        raise HTTPException(
            status_code=403,
            detail="Platform admin access required",
        )

    return user


def _raise_risk_moderation_error(exc: Exception) -> None:
    if isinstance(exc, CustomerRiskModerationNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, CustomerRiskModerationValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/overview")
def admin_overview(
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    """Platform-wide overview metrics with recent growth analytics."""
    overview = get_admin_overview(db)
    overview["growth"] = get_admin_growth_metrics(db)
    return overview


@router.get("/organizations")
def admin_organizations(
    page: int = 1,
    page_size: int = 25,
    plan: str | None = None,
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    """List all organizations with metrics."""
    return get_organization_list(db, page=page, page_size=page_size, plan_filter=plan)


@router.get("/organizations/{org_id}")
def admin_organization_detail(
    org_id: int,
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    """Get detailed organization info."""
    result = get_organization_detail(db, org_id)
    if not result:
        raise HTTPException(status_code=404, detail="Organization not found")
    return result


@router.get("/attention")
def admin_attention(
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    """Organizations needing attention."""
    return get_attention_list(db)


@router.get("/customer-risk/stats")
def admin_customer_risk_stats(
    analytics_days: int | None = None,
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    """Moderation workload, limits and optional read-only analytics."""
    payload = get_customer_risk_moderation_stats(db)
    if analytics_days is not None:
        payload["analytics"] = get_customer_risk_moderation_analytics(
            db,
            days=analytics_days,
        )
    return payload


@router.get("/customer-risk/reports")
def admin_customer_risk_reports(
    page: int = 1,
    page_size: int = 25,
    status: str | None = None,
    reason: str | None = None,
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    return list_customer_risk_moderation_reports(
        db,
        page=page,
        page_size=page_size,
        status=status,
        reason=reason,
    )


@router.get("/customer-risk/reports/{report_id}")
def admin_customer_risk_report_detail(
    report_id: int,
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    try:
        return get_customer_risk_moderation_report(db, report_id)
    except (
        CustomerRiskModerationNotFoundError,
        CustomerRiskModerationValidationError,
    ) as exc:
        _raise_risk_moderation_error(exc)


@router.patch("/customer-risk/reports/{report_id}/moderation")
def admin_moderate_customer_risk_report(
    report_id: int,
    payload: RiskReportModerationRequest,
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    try:
        return moderate_customer_risk_report(
            db,
            report_id=report_id,
            admin_user_id=user.id,
            action=payload.action,
            note=payload.note,
        )
    except (
        CustomerRiskModerationNotFoundError,
        CustomerRiskModerationValidationError,
    ) as exc:
        _raise_risk_moderation_error(exc)


@router.get("/customer-risk/disputes")
def admin_customer_risk_disputes(
    page: int = 1,
    page_size: int = 25,
    status: str | None = "open",
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    return list_customer_risk_disputes(
        db,
        page=page,
        page_size=page_size,
        status=status,
    )


@router.get("/customer-risk/disputes/{dispute_id}")
def admin_customer_risk_dispute_detail(
    dispute_id: int,
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    try:
        return get_customer_risk_dispute_detail(db, dispute_id)
    except (
        CustomerRiskModerationNotFoundError,
        CustomerRiskModerationValidationError,
    ) as exc:
        _raise_risk_moderation_error(exc)


@router.patch("/customer-risk/disputes/{dispute_id}/resolution")
def admin_resolve_customer_risk_dispute(
    dispute_id: int,
    payload: RiskDisputeResolutionRequest,
    user: User = Depends(_require_platform_admin),
    db: Session = Depends(get_db),
):
    try:
        return resolve_customer_risk_dispute(
            db,
            dispute_id=dispute_id,
            admin_user_id=user.id,
            outcome=payload.outcome,
            note=payload.note,
        )
    except (
        CustomerRiskModerationNotFoundError,
        CustomerRiskModerationValidationError,
    ) as exc:
        _raise_risk_moderation_error(exc)
