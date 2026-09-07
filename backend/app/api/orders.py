from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    OrganizationMembership,
    Store,
)
from .deps import require_permission

router = APIRouter()


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

    from ..shopify_orders import list_shopify_orders

    orders = list_shopify_orders(
        db=db,
        store_id=store.id,
        organization_id=store.organization_id,
    )

    return {
        "items": orders,
        "total": len(orders),
    }
