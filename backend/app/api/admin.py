"""Admin API router.

Platform-level internal dashboard for Diaglob founders/operators.
Requires platform_admin authorization.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
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

router = APIRouter(prefix="/api/admin")


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
