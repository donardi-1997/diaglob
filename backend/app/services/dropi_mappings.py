"""Dropi supplier variant mappings, reusing the existing multi-provider table.

Mapping is explicit and tenant-scoped: never infer fulfillment IDs from a SKU.
No data is sent to Dropi or Shopify by these operations.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..model_domains.supplier_variant_mappings import SupplierVariantMapping
from ..models import Product, ProductVariant, Store


PROVIDER = "dropi"


class DropiMappingError(Exception):
    """Stable, sanitized domain error."""


def _store(db: Session, organization_id: int, store_id: int) -> Store:
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
        raise DropiMappingError("DROPI_STORE_NOT_FOUND")
    return store


def _variant(
    db: Session,
    organization_id: int,
    store_id: int,
    variant_id: int,
) -> tuple[ProductVariant, Product]:
    found = (
        db.query(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            ProductVariant.id == variant_id,
            Product.organization_id == organization_id,
            Product.store_id == store_id,
        )
        .first()
    )
    if not found:
        raise DropiMappingError("DROPI_VARIANT_NOT_FOUND")
    return found[0], found[1]


def _serialize(
    variant: ProductVariant, product: Product, mapping: SupplierVariantMapping | None
) -> dict:
    return {
        "provider": PROVIDER,
        "product_id": product.id,
        "product_title": product.title,
        "product_variant_id": variant.id,
        "shopify_variant_id": variant.shopify_variant_id,
        "variant_title": variant.title,
        "sku": variant.sku,
        "mapped": bool(mapping and mapping.active),
        "external_product_id": mapping.external_product_id if mapping else None,
        "external_variant_id": mapping.external_variant_id if mapping else None,
        "external_sku": mapping.external_sku if mapping else None,
        "active": bool(mapping and mapping.active),
    }


def list_mappings(db: Session, organization_id: int, store_id: int) -> dict:
    _store(db, organization_id, store_id)
    rows = (
        db.query(ProductVariant, Product)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(Product.organization_id == organization_id, Product.store_id == store_id)
        .order_by(Product.title.asc(), ProductVariant.title.asc(), ProductVariant.id.asc())
        .all()
    )
    mappings = (
        db.query(SupplierVariantMapping)
        .filter(
            SupplierVariantMapping.organization_id == organization_id,
            SupplierVariantMapping.store_id == store_id,
            SupplierVariantMapping.provider == PROVIDER,
        )
        .all()
    )
    by_variant = {mapping.product_variant_id: mapping for mapping in mappings}
    items = [_serialize(variant, product, by_variant.get(variant.id)) for variant, product in rows]
    count = sum(1 for item in items if item["mapped"])
    return {"provider": PROVIDER, "items": items, "total": len(items), "mapped": count, "unmapped": len(items) - count}


def upsert_mapping(
    db: Session,
    organization_id: int,
    store_id: int,
    variant_id: int,
    *,
    external_product_id: str,
    external_variant_id: str,
    external_sku: str | None = None,
    active: bool = True,
) -> dict:
    _store(db, organization_id, store_id)
    variant, product = _variant(db, organization_id, store_id, variant_id)
    product_ref = (external_product_id or "").strip()
    variant_ref = (external_variant_id or "").strip()
    sku_ref = (external_sku or "").strip() or None
    if not product_ref or not variant_ref:
        raise DropiMappingError("DROPI_MAPPING_IDS_REQUIRED")

    mapping = (
        db.query(SupplierVariantMapping)
        .filter(
            SupplierVariantMapping.organization_id == organization_id,
            SupplierVariantMapping.store_id == store_id,
            SupplierVariantMapping.product_variant_id == variant_id,
            SupplierVariantMapping.provider == PROVIDER,
        )
        .first()
    )
    now = datetime.utcnow()
    if mapping is None:
        mapping = SupplierVariantMapping(
            organization_id=organization_id,
            store_id=store_id,
            product_variant_id=variant_id,
            provider=PROVIDER,
            external_product_id=product_ref,
            external_variant_id=variant_ref,
            external_sku=sku_ref,
            active=active,
            created_at=now,
            updated_at=now,
        )
        db.add(mapping)
    else:
        mapping.external_product_id = product_ref
        mapping.external_variant_id = variant_ref
        mapping.external_sku = sku_ref
        mapping.active = active
        mapping.updated_at = now
    db.commit()
    db.refresh(mapping)
    return _serialize(variant, product, mapping)


def delete_mapping(
    db: Session, organization_id: int, store_id: int, variant_id: int
) -> dict:
    _store(db, organization_id, store_id)
    _variant(db, organization_id, store_id, variant_id)
    mapping = (
        db.query(SupplierVariantMapping)
        .filter(
            SupplierVariantMapping.organization_id == organization_id,
            SupplierVariantMapping.store_id == store_id,
            SupplierVariantMapping.product_variant_id == variant_id,
            SupplierVariantMapping.provider == PROVIDER,
        )
        .first()
    )
    if mapping is None:
        raise DropiMappingError("DROPI_MAPPING_NOT_FOUND")
    db.delete(mapping)
    db.commit()
    return {"ok": True, "provider": PROVIDER, "product_variant_id": variant_id}
