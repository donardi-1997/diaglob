"""Analytics and Operations HTTP router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..analytics import (
    get_commerce_analytics,
    get_conversations_analytics,
    get_date_range,
    get_summary,
    get_timeseries,
)
from ..db import get_db
from ..models import OrganizationMembership, Store
from ..services.operations_integrations import get_dynamic_operations_summary
from .deps import require_permission

router = APIRouter()


@router.get(
    "/api/stores/{store_id}"
    "/analytics/summary"
)
def get_analytics_summary(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_summary(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


@router.get(
    "/api/stores/{store_id}"
    "/analytics/timeseries"
)
def get_analytics_timeseries(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_timeseries(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


@router.get(
    "/api/stores/{store_id}"
    "/analytics/conversations"
)
def get_analytics_conversations(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_conversations_analytics(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


@router.get(
    "/api/stores/{store_id}"
    "/analytics/commerce"
)
def get_analytics_commerce(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_commerce_analytics(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


@router.get(
    "/api/stores/{store_id}/operations/summary"
)
def get_operations_center_summary(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    return get_dynamic_operations_summary(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
    )
