from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    CommerceConnection,
    OrganizationMembership,
    Order,
    Product,
    ProductVariant,
    Store,
)
from .deps import require_permission
from .products import serialize_commerce_product

router = APIRouter()


@router.get(
    "/api/stores/{store_id}"
    "/commerce"
)
def get_store_commerce_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
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

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
            CommerceConnection.provider == "shopify",
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "provider": None,
            "external_store_url": None,
            "status": "disconnected",
            "connected_at": None,
            "last_sync_at": None,
            "last_error": None,
            "dropi_detection": {
                "status": "not_detected",
                "label": "Dropi no detectado",
                "evidence": [],
            },
        }

    return {
        "connected":
            connection.status
            == "connected",

        "provider":
            connection.provider,

        "external_store_url":
            connection.external_store_url,

        "status":
            connection.status,

        "connected_at":
            (
                connection.connected_at.isoformat()
                + "Z"
                if connection.connected_at
                else None
            ),

        "last_sync_at":
            (
                connection.last_sync_at.isoformat()
                + "Z"
                if connection.last_sync_at
                else None
            ),

        "last_error":
            connection.last_error,
        "dropi_detection": {
            "status": "not_detected",
            "label": "Dropi no detectado",
            "evidence": [],
        },
    }


@router.get(
    "/api/stores/{store_id}"
    "/commerce/summary"
)
def get_commerce_summary(
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

    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id
            == store.id,
            CommerceConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    total_products = (
        db.query(Product)
        .filter(
            Product.store_id == store.id,
            Product.organization_id
            == membership.organization_id,
        )
        .count()
    )

    total_variants = (
        db.query(ProductVariant)
        .join(Product)
        .filter(
            Product.store_id == store.id,
            Product.organization_id
            == membership.organization_id,
        )
        .count()
    )

    orders_query = (
        db.query(Order)
        .filter(
            Order.store_id == store.id,
            Order.organization_id
            == membership.organization_id,
        )
    )

    total_orders = orders_query.count()

    orders_by_status = {}

    for status_val in (
        "pending",
        "created",
        "failed",
        "unknown",
    ):
        orders_by_status[status_val] = (
            orders_query.filter(
                Order.external_creation_status
                == status_val
            )
            .count()
        )

    total_order_value = 0.0

    value_rows = (
        db.query(
            Order.total_amount,
            Order.currency,
        )
        .filter(
            Order.store_id == store.id,
            Order.organization_id
            == membership.organization_id,
            Order.external_creation_status
            .in_(["created", "pending"]),
        )
        .all()
    )

    for amount, _currency in value_rows:
        total_order_value += float(amount)

    recent_orders = (
        db.query(Order)
        .filter(
            Order.store_id == store.id,
            Order.organization_id
            == membership.organization_id,
        )
        .order_by(Order.created_at.desc())
        .limit(5)
        .all()
    )

    recent_products = (
        db.query(Product)
        .filter(
            Product.store_id == store.id,
            Product.organization_id
            == membership.organization_id,
        )
        .order_by(Product.updated_at.desc())
        .limit(5)
        .all()
    )

    return {
        "connected":
            connection is not None
            and connection.status
            == "connected",

        "provider":
            connection.provider
            if connection
            else None,

        "total_products": total_products,
        "total_variants": total_variants,
        "total_orders": total_orders,
        "orders_by_status": orders_by_status,
        "total_order_value": round(
            total_order_value, 2
        ),
        "currency": store.currency,

        "recent_orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "total_amount": float(
                    o.total_amount
                ),
                "currency": o.currency,
                "financial_status": (
                    o.financial_status
                ),
                "source": o.source,
                "external_creation_status": (
                    o.external_creation_status
                ),
                "created_at": (
                    o.created_at.isoformat()
                    + "Z"
                    if o.created_at
                    else None
                ),
            }
            for o in recent_orders
        ],

        "recent_products": [
            {
                "id": p.id,
                "title": p.title,
                "image_url": p.image_url,
                "active": p.active,
                "updated_at": (
                    p.updated_at.isoformat()
                    + "Z"
                    if p.updated_at
                    else None
                ),
            }
            for p in recent_products
        ],
    }


@router.get(
    "/api/stores/{store_id}"
    "/commerce/products"
)
def list_store_commerce_products(
    store_id: int,
    q: str | None = None,
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

    query = (
        db.query(Product)
        .filter(
            Product.store_id == store.id,
            Product.organization_id
            == membership.organization_id,
        )
    )

    if q and q.strip():
        search = f"%{q.strip()}%"

        query = query.filter(
            Product.title.ilike(search)
        )

    products = (
        query
        .order_by(Product.title)
        .all()
    )

    return {
        "items": [
            serialize_commerce_product(p)
            for p in products
        ],
        "total": len(products),
    }
