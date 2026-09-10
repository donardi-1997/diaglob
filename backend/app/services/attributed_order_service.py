"""Commerce order orchestration with explicit sales attribution."""
from sqlalchemy.orm import Session

from ..models import CommerceConnection, Store
from ..shopify_cod_orders import create_shopify_cod_order
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
    """Create a Shopify order and attribute it only after a local order exists."""
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


def create_attributed_shopify_cod_order(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    customer_id: int,
    variant_local_id: int,
    quantity: int,
    customer_email: str | None,
    customer_phone: str,
    shipping_address: dict,
    note: str,
    idempotency_key: str,
    ai_agent_id: int,
    conversation_id: int,
) -> dict:
    """Create an actual COD Shopify order and explicitly attribute it to AI."""
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
            Store.active.is_(True),
        )
        .first()
    )
    if not store:
        raise ValueError("Store not found")

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == store_id,
            CommerceConnection.provider == "shopify",
            CommerceConnection.status == "connected",
        )
        .first()
    )
    if not connection:
        raise ValueError("SHOPIFY_NOT_CONNECTED")

    result = create_shopify_cod_order(
        db=db,
        store=store,
        connection=connection,
        customer_id=customer_id,
        variant_local_id=variant_local_id,
        quantity=quantity,
        customer_email=customer_email,
        customer_phone=customer_phone,
        shipping_address=shipping_address,
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
            actor_type="ai",
            ai_agent_id=ai_agent_id,
            conversation_id=conversation_id,
            source="ai_conversational_checkout",
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
