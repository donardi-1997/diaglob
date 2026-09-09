"""Dropshipping analytics API endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..api.deps import (
    get_current_membership,
    get_db,
    require_permission,
)
from ..models import Store
from ..services.dropshipping_analytics import (
    get_dropshipping_overview,
    get_profitability,
    get_product_profitability,
    get_order_funnel,
)

router = APIRouter()


def _validate_store(
    store_id: int,
    membership,
    db: Session,
) -> Store:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == membership.organization_id,
        Store.active == True,
    ).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


def _parse_date(
    date_str: str | None,
) -> str | None:
    if not date_str:
        return None
    try:
        datetime.fromisoformat(date_str)
        return date_str
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {date_str}",
        )


@router.get(
    "/api/stores/{store_id}/analytics/dropshipping/overview",
)
def dropshipping_overview(
    store_id: int,
    membership=Depends(require_permission("analytics.read")),
    db: Session = Depends(get_db),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """Dropshipping overview metrics."""
    _validate_store(store_id, membership, db)
    date_from = _parse_date(date_from)
    date_to = _parse_date(date_to)

    return get_dropshipping_overview(
        db,
        membership.organization_id,
        store_id,
        date_from,
        date_to,
    )


@router.get(
    "/api/stores/{store_id}/analytics/dropshipping/profitability",
)
def dropshipping_profitability(
    store_id: int,
    membership=Depends(require_permission("analytics.read")),
    db: Session = Depends(get_db),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """Dropshipping profitability metrics."""
    _validate_store(store_id, membership, db)
    date_from = _parse_date(date_from)
    date_to = _parse_date(date_to)

    return get_profitability(
        db,
        membership.organization_id,
        store_id,
        date_from,
        date_to,
    )


@router.get(
    "/api/stores/{store_id}/analytics/dropshipping/products",
)
def dropshipping_products(
    store_id: int,
    membership=Depends(require_permission("analytics.read")),
    db: Session = Depends(get_db),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Product profitability breakdown."""
    _validate_store(store_id, membership, db)
    date_from = _parse_date(date_from)
    date_to = _parse_date(date_to)

    return get_product_profitability(
        db,
        membership.organization_id,
        store_id,
        date_from,
        date_to,
        limit,
    )


@router.get(
    "/api/stores/{store_id}/analytics/dropshipping/orders",
)
def dropshipping_orders(
    store_id: int,
    membership=Depends(require_permission("analytics.read")),
    db: Session = Depends(get_db),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
):
    """Order funnel metrics."""
    _validate_store(store_id, membership, db)
    date_from = _parse_date(date_from)
    date_to = _parse_date(date_to)

    return get_order_funnel(
        db,
        membership.organization_id,
        store_id,
        date_from,
        date_to,
    )
