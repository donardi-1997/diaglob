"""Commerce-order application service."""
from typing import Any

from sqlalchemy.orm import Session

from ..shopify_orders import list_shopify_orders
from .customer_risk_service import enrich_order_payloads
from .sales_attribution import enrich_orders_with_attribution


def list_commerce_orders(
    db: Session,
    organization_id: int,
    store_id: int,
) -> list[dict[str, Any]]:
    """List provider-backed orders with attribution and customer-risk signals."""
    orders = list_shopify_orders(
        db=db,
        store_id=store_id,
        organization_id=organization_id,
    )
    attributed = enrich_orders_with_attribution(
        db,
        organization_id,
        store_id,
        orders,
    )
    return enrich_order_payloads(
        db=db,
        organization_id=organization_id,
        store_id=store_id,
        payloads=attributed,
    )
