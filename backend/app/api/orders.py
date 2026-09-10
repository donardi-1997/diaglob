from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership, Store
from ..services.commerce_order_service import list_commerce_orders
from ..services.manual_sales_attribution import set_manual_order_attribution
from ..services.sales_attribution import SalesAttributionError
from .deps import require_permission

router = APIRouter()


class SalesAttributionUpdateRequest(BaseModel):
    actor_type: Literal["human", "ai"] | None = None
    actor_id: int | None = None


@router.get(
    "/api/stores/{store_id}"
    "/commerce/orders"
)
def list_store_commerce_orders(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
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

    orders = list_commerce_orders(
        db=db,
        store_id=store.id,
        organization_id=store.organization_id,
    )

    return {
        "items": orders,
        "total": len(orders),
    }


@router.patch(
    "/api/stores/{store_id}"
    "/commerce/orders/{order_id}/sales-attribution"
)
def update_order_sales_attribution(
    store_id: int,
    order_id: int,
    payload: SalesAttributionUpdateRequest,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    """Explicitly assign, reassign, or clear the closer for one order."""
    try:
        attribution = set_manual_order_attribution(
            db=db,
            organization_id=membership.organization_id,
            store_id=store_id,
            order_id=order_id,
            changed_by_user_id=membership.user_id,
            actor_type=payload.actor_type,
            actor_id=payload.actor_id,
        )
    except SalesAttributionError as exc:
        status_code = 404 if str(exc) == "Order not found" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    return {
        "order_id": order_id,
        "sales_attribution": attribution,
    }
