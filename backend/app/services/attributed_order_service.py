"""Commerce order orchestration with explicit sales attribution."""
from sqlalchemy.orm import Session

from .sales_attribution import enrich_orders_with_attribution, record_order_attribution
from .shopify_service import (
    create_order as create_shopify_order,
    get_order as get_shopify_order,
    list_orders as list_shopify_orders,
)


def create_attributed_shopify_order(
    db: Session,
    organization_id: int,
    store_id: int,
    items_payload: list[dict],
    customer_email: str | None,
    customer_name: str | None,
    note: str | None,
    idempotency_key: str | None,
    *,
    actor_type: str,
    human_user_id: int | None = None,
    ai_agent_id: int | None = None,
    conversation_id: int | None = None,
) -> dict:
    """Create a Shopify order and attribute it only after a local order exists.

    The underlying Shopify service retains its provider responsibilities. This
    wrapper adds the application-level closer identity and works for both human
    and AI order creation paths.
    """
    result = create_shopify_order(
        db=db,
        organization_id=organization_id,
        store_id=store_id,
        items_payload=items_payload,
        customer_email=customer_email,
        customer_name=customer_name,
        note=note,
        idempotency_key=idempotency_key,
    )

    order_id = result.get("order_id")
    if result.get("ok") and order_id is not None:
        record_order_attribution(
            db,
            organization_id,
            store_id,
            int(order_id),
            actor_type=actor_type,
            human_user_id=human_user_id,
            ai_agent_id=ai_agent_id,
            conversation_id=conversation_id,
            source=(
                "ai_order_creation"
                if actor_type == "ai"
                else "diaglob_order_creation"
            ),
        )

    return result


def list_attributed_shopify_orders(
    db: Session,
    organization_id: int,
    store_id: int,
) -> list[dict]:
    """List commerce orders with an explicit closer or null attribution."""
    orders = list_shopify_orders(db, organization_id, store_id)
    return enrich_orders_with_attribution(
        db,
        organization_id,
        store_id,
        orders,
    )


def get_attributed_shopify_order(
    db: Session,
    organization_id: int,
    store_id: int,
    order_id: int,
) -> dict | None:
    """Get one commerce order and attach closer attribution when available."""
    order = get_shopify_order(db, organization_id, store_id, order_id)
    if order is None:
        return None
    return enrich_orders_with_attribution(
        db,
        organization_id,
        store_id,
        [order],
    )[0]
