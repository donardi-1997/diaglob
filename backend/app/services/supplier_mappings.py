"""Supplier variant mapping lifecycle and order-resolution helpers."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..model_domains.supplier_variant_mappings import SupplierVariantMapping
from ..models import Product, ProductVariant, Store

CJ_PROVIDER = "cj"


class SupplierVariantMappingError(Exception):
    pass


class SupplierVariantMappingNotFound(SupplierVariantMappingError):
    pass


def _require_store(
    db: Session,
    organization_id: int,
    store_id: int,
) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if store is None:
        raise SupplierVariantMappingNotFound("STORE_NOT_FOUND")
    return store


def _require_variant(
    db: Session,
    organization_id: int,
    store_id: int,
    product_variant_id: int,
) -> tuple[ProductVariant, Product]:
    row = (
        db.query(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            ProductVariant.id == product_variant_id,
            Product.organization_id == organization_id,
            Product.store_id == store_id,
        )
        .first()
    )
    if row is None:
        raise SupplierVariantMappingNotFound("PRODUCT_VARIANT_NOT_FOUND")
    return row[0], row[1]


def _serialize(
    product: Product,
    variant: ProductVariant,
    mapping: SupplierVariantMapping | None,
) -> dict:
    return {
        "provider": CJ_PROVIDER,
        "product_id": product.id,
        "product_title": product.title,
        "product_variant_id": variant.id,
        "shopify_variant_id": variant.shopify_variant_id,
        "variant_title": variant.title,
        "sku": variant.sku,
        "mapped": bool(mapping and mapping.active),
        "mapping_id": mapping.id if mapping else None,
        "external_product_id": mapping.external_product_id if mapping else None,
        "external_variant_id": mapping.external_variant_id if mapping else None,
        "external_sku": mapping.external_sku if mapping else None,
        "active": mapping.active if mapping else False,
        "updated_at": (
            mapping.updated_at.isoformat() + "Z"
            if mapping and mapping.updated_at
            else None
        ),
    }


def list_cj_variant_mappings(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    _require_store(db, organization_id, store_id)

    variants = (
        db.query(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == organization_id,
            Product.store_id == store_id,
        )
        .order_by(Product.title.asc(), ProductVariant.title.asc(), ProductVariant.id.asc())
        .all()
    )
    mappings = (
        db.query(SupplierVariantMapping)
        .filter(
            SupplierVariantMapping.organization_id == organization_id,
            SupplierVariantMapping.store_id == store_id,
            SupplierVariantMapping.provider == CJ_PROVIDER,
        )
        .all()
    )
    by_variant = {mapping.product_variant_id: mapping for mapping in mappings}
    items = [
        _serialize(product, variant, by_variant.get(variant.id))
        for variant, product in variants
    ]
    mapped_count = sum(1 for item in items if item["mapped"])
    return {
        "provider": CJ_PROVIDER,
        "items": items,
        "total": len(items),
        "mapped": mapped_count,
        "unmapped": len(items) - mapped_count,
    }


def upsert_cj_variant_mapping(
    db: Session,
    organization_id: int,
    store_id: int,
    product_variant_id: int,
    *,
    external_product_id: str,
    external_variant_id: str,
    external_sku: str | None = None,
    active: bool = True,
) -> dict:
    _require_store(db, organization_id, store_id)
    variant, product = _require_variant(
        db,
        organization_id,
        store_id,
        product_variant_id,
    )

    external_product_id = (external_product_id or "").strip()
    external_variant_id = (external_variant_id or "").strip()
    external_sku = (external_sku or "").strip() or None

    if not external_product_id:
        raise SupplierVariantMappingError("CJ_PRODUCT_ID_REQUIRED")
    if not external_variant_id:
        raise SupplierVariantMappingError("CJ_VARIANT_ID_REQUIRED")

    mapping = (
        db.query(SupplierVariantMapping)
        .filter(
            SupplierVariantMapping.organization_id == organization_id,
            SupplierVariantMapping.store_id == store_id,
            SupplierVariantMapping.provider == CJ_PROVIDER,
            SupplierVariantMapping.product_variant_id == product_variant_id,
        )
        .first()
    )

    now = datetime.utcnow()
    if mapping is None:
        mapping = SupplierVariantMapping(
            organization_id=organization_id,
            store_id=store_id,
            product_variant_id=product_variant_id,
            provider=CJ_PROVIDER,
            external_product_id=external_product_id,
            external_variant_id=external_variant_id,
            external_sku=external_sku,
            active=active,
            created_at=now,
            updated_at=now,
        )
        db.add(mapping)
    else:
        mapping.external_product_id = external_product_id
        mapping.external_variant_id = external_variant_id
        mapping.external_sku = external_sku
        mapping.active = active
        mapping.updated_at = now

    db.commit()
    db.refresh(mapping)
    return _serialize(product, variant, mapping)


def delete_cj_variant_mapping(
    db: Session,
    organization_id: int,
    store_id: int,
    product_variant_id: int,
) -> dict:
    _require_store(db, organization_id, store_id)
    _require_variant(db, organization_id, store_id, product_variant_id)

    mapping = (
        db.query(SupplierVariantMapping)
        .filter(
            SupplierVariantMapping.organization_id == organization_id,
            SupplierVariantMapping.store_id == store_id,
            SupplierVariantMapping.provider == CJ_PROVIDER,
            SupplierVariantMapping.product_variant_id == product_variant_id,
        )
        .first()
    )
    if mapping is None:
        raise SupplierVariantMappingNotFound("CJ_VARIANT_MAPPING_NOT_FOUND")

    db.delete(mapping)
    db.commit()
    return {
        "ok": True,
        "provider": CJ_PROVIDER,
        "product_variant_id": product_variant_id,
    }


def resolve_cj_variant_mapping(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    product_variant_id: int | None = None,
    shopify_variant_id: str | None = None,
) -> SupplierVariantMapping | None:
    resolved_variant_id = product_variant_id

    if resolved_variant_id is None and shopify_variant_id:
        local_variant = (
            db.query(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(
                Product.organization_id == organization_id,
                Product.store_id == store_id,
                ProductVariant.shopify_variant_id == str(shopify_variant_id),
            )
            .first()
        )
        if local_variant is not None:
            resolved_variant_id = local_variant.id

    if resolved_variant_id is None:
        return None

    return (
        db.query(SupplierVariantMapping)
        .filter(
            SupplierVariantMapping.organization_id == organization_id,
            SupplierVariantMapping.store_id == store_id,
            SupplierVariantMapping.provider == CJ_PROVIDER,
            SupplierVariantMapping.product_variant_id == resolved_variant_id,
            SupplierVariantMapping.active.is_(True),
        )
        .first()
    )


__all__ = [
    "SupplierVariantMappingError",
    "SupplierVariantMappingNotFound",
    "delete_cj_variant_mapping",
    "list_cj_variant_mappings",
    "resolve_cj_variant_mapping",
    "upsert_cj_variant_mapping",
]
