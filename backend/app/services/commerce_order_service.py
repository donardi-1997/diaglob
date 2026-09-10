"""Commerce-order application service."""
from typing import Any

from sqlalchemy.orm import Session

from ..shopify_orders import list_shopify_orders
from .sales_attribution import enrich_orders_with_attribution


def list_commerce_orders(
    db: Session,
    organization_id: int,
    store_id: int,
) -> list[dict[str, Any]]:
    """List provider-backed orders with current sales attribution attached."""
    orders = list_shopify_orders(
        db=db,
        store_id=store_id,
        organization_id=organization_id,
    )
    return enrich_orders_with_attribution(
        db,
        organization_id,
        store_id,
        orders,
    )
