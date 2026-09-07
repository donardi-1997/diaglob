from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    OrganizationMembership,
    Product,
    ProductVariant,
    Store,
)
from .deps import (
    get_store_scope,
    require_permission,
)

router = APIRouter()


class ProductVariantCreate(BaseModel):
    title: str
    sku: str | None = None
    barcode: str | None = None
    price: float
    currency: str | None = None
    inventory_quantity: int = 0
    available: bool = True
    shopify_variant_id: str | None = None


class ProductCreate(BaseModel):
    title: str
    handle: str | None = None
    description: str = ""
    image_url: str | None = None
    vendor: str | None = None
    product_type: str | None = None
    active: bool = True
    shopify_product_id: str | None = None
    variants: list[ProductVariantCreate] = []


def serialize_commerce_product(
    product: Product,
):
    return {
        "id": product.id,
        "organization_id": product.organization_id,
        "store_id": product.store_id,
        "shopify_product_id":
            product.shopify_product_id,
        "title": product.title,
        "handle": product.handle,
        "description": product.description,
        "image_url": product.image_url,
        "vendor": product.vendor,
        "product_type": product.product_type,
        "active": product.active,

        "store": {
            "id": product.store.id,
            "name": product.store.name,
            "country_code":
                product.store.country_code,
            "currency":
                product.store.currency,
        }
        if product.store
        else None,

        "variants": [
            {
                "id": variant.id,
                "shopify_variant_id":
                    variant.shopify_variant_id,
                "title": variant.title,
                "sku": variant.sku,
                "barcode": variant.barcode,
                "price":
                    float(variant.price),
                "currency":
                    variant.currency,
                "inventory_quantity":
                    variant.inventory_quantity,
                "available":
                    variant.available,
            }
            for variant in product.variants
        ],
    }


def get_allowed_store_ids(
    membership: OrganizationMembership,
):
    if membership.all_stores:
        return None

    return [
        store.id
        for store in membership.stores
        if store.active
    ]


@router.get("/api/commerce/products")
def list_commerce_products(
    q: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
        )
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Product)
        .filter(
            Product.organization_id
            == membership.organization_id,

            Product.active.is_(True),
        )
    )

    if store is not None:
        query = query.filter(
            Product.store_id == store.id
        )

    else:
        allowed_store_ids = (
            get_allowed_store_ids(
                membership
            )
        )

        if allowed_store_ids is not None:
            if not allowed_store_ids:
                return {
                    "items": [],
                    "total": 0,
                }

            query = query.filter(
                Product.store_id.in_(
                    allowed_store_ids
                )
            )

    if q and q.strip():
        search = (
            f"%{q.strip()}%"
        )

        query = query.filter(
            Product.title.ilike(
                search
            )
        )

    products = (
        query
        .order_by(
            Product.title
        )
        .all()
    )

    return {
        "items": [
            serialize_commerce_product(
                product
            )
            for product in products
        ],
        "total":
            len(products),
    }


@router.post("/api/commerce/products")
def create_commerce_product(
    payload: ProductCreate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.write"
        )
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    if store is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Select a store before "
                "creating a product"
            ),
        )

    title = (
        payload.title
        .strip()
    )

    if not title:
        raise HTTPException(
            status_code=400,
            detail=(
                "Product title is required"
            ),
        )

    product = Product(
        organization_id=
            membership.organization_id,

        store_id=
            store.id,

        shopify_product_id=
            payload.shopify_product_id,

        title=
            title,

        handle=
            payload.handle,

        description=
            payload.description,

        image_url=
            payload.image_url,

        vendor=
            payload.vendor,

        product_type=
            payload.product_type,

        active=
            payload.active,
    )

    db.add(product)
    db.flush()

    for item in payload.variants:
        currency = (
            item.currency
            or store.currency
        ).upper()

        if (
            currency
            != store.currency.upper()
        ):
            db.rollback()

            raise HTTPException(
                status_code=400,
                detail=(
                    "Variant currency must "
                    "match store currency "
                    f"({store.currency})"
                ),
            )

        if item.price < 0:
            db.rollback()

            raise HTTPException(
                status_code=400,
                detail=(
                    "Variant price cannot "
                    "be negative"
                ),
            )

        if item.inventory_quantity < 0:
            db.rollback()

            raise HTTPException(
                status_code=400,
                detail=(
                    "Inventory quantity cannot "
                    "be negative"
                ),
            )

        variant = ProductVariant(
            product_id=
                product.id,

            shopify_variant_id=
                item.shopify_variant_id,

            title=(
                item.title.strip()
                or "Default"
            ),

            sku=
                item.sku,

            barcode=
                item.barcode,

            price=
                item.price,

            currency=
                currency,

            inventory_quantity=
                item.inventory_quantity,

            available=(
                item.available
                and
                item.inventory_quantity > 0
            ),
        )

        db.add(variant)

    db.commit()
    db.refresh(product)

    return serialize_commerce_product(
        product
    )


@router.get(
    "/api/commerce/products/{product_id}"
)
def get_commerce_product(
    product_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "commerce.read"
        )
    ),
    store: Store | None = Depends(
        get_store_scope
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Product)
        .filter(
            Product.id == product_id,

            Product.organization_id
            == membership.organization_id,
        )
    )

    if store is not None:
        query = query.filter(
            Product.store_id == store.id
        )

    else:
        allowed_store_ids = (
            get_allowed_store_ids(
                membership
            )
        )

        if allowed_store_ids is not None:
            if not allowed_store_ids:
                raise HTTPException(
                    status_code=404,
                    detail="Product not found",
                )

            query = query.filter(
                Product.store_id.in_(
                    allowed_store_ids
                )
            )

    product = query.first()

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return serialize_commerce_product(
        product
    )
