"""Dropshipping analytics API endpoints."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..api.deps import get_db, require_permission
from ..models import Store
from ..services.dropshipping_analytics import (
    get_dropshipping_overview,
    get_order_funnel,
    get_product_profitability,
    get_profitability,
)

router = APIRouter()


def _validate_store(
    store_id: int,
    membership,
    db: Session,
) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == membership.organization_id,
            Store.active.is_(True),
        )
        .first()
    )
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


def _parse_date(
    date_str: str | None,
    *,
    inclusive_end: bool = False,
) -> datetime | None:
    """Parse ISO dates and make date-only end bounds inclusive by day."""
    if not date_str:
        return None

    try:
        parsed = datetime.fromisoformat(date_str)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: {date_str}",
        ) from exc

    if inclusive_end and len(date_str) == 10:
        parsed += timedelta(days=1)

    return parsed


def _parse_range(
    date_from: str | None,
    date_to: str | None,
) -> tuple[datetime | None, datetime | None]:
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to, inclusive_end=True)

    if parsed_from and parsed_to and parsed_from >= parsed_to:
        raise HTTPException(
            status_code=400,
            detail="date_from must be before or equal to date_to",
        )

    return parsed_from, parsed_to


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
    store = _validate_store(store_id, membership, db)
    parsed_from, parsed_to = _parse_range(date_from, date_to)

    result = get_dropshipping_overview(
        db,
        membership.organization_id,
        store_id,
        parsed_from,
        parsed_to,
    )
    result["currency"] = store.currency
    return result


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
    parsed_from, parsed_to = _parse_range(date_from, date_to)

    return get_profitability(
        db,
        membership.organization_id,
        store_id,
        parsed_from,
        parsed_to,
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
    parsed_from, parsed_to = _parse_range(date_from, date_to)

    return get_product_profitability(
        db,
        membership.organization_id,
        store_id,
        parsed_from,
        parsed_to,
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
    parsed_from, parsed_to = _parse_range(date_from, date_to)

    return get_order_funnel(
        db,
        membership.organization_id,
        store_id,
        parsed_from,
        parsed_to,
    )
