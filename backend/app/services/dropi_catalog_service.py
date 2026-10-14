"""Tenant-scoped Dropi catalog browsing and comparison with Shopify mappings.

No Shopify publication, mapping mutation, stock reservation or Dropi order writes.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..integrations.dropi_native import search_products
from ..model_domains.supplier_variant_mappings import SupplierVariantMapping
from ..models import Product, ProductVariant
from .dropi_service import DropiConnectionError, _connection_and_token


def _compare_sku(local_sku: str | None, remote_sku: str | None) -> str:
    if not local_sku or not remote_sku:
        return "unknown"
    return "match" if local_sku.strip().casefold() == remote_sku.strip().casefold() else "different"


def _compare_stock(local_quantity: int | None, remote_quantity: int | None) -> str:
    if local_quantity is None or remote_quantity is None:
        return "unknown"
    if local_quantity == remote_quantity:
        return "match"
    return "different"


def attach_shopify_mappings(products: list[dict], mapped_rows: list[tuple]) -> list[dict]:
    """Annotate only explicitly mapped variants. Never infer ownership by SKU."""
    by_product: dict[str, list[dict]] = {}
    for mapping, variant, product in mapped_rows:
        if not mapping.active:
            continue
        by_product.setdefault(str(mapping.external_product_id), []).append({
            "product_variant_id": variant.id,
            "shopify_variant_id": variant.shopify_variant_id,
            "shopify_product_id": product.shopify_product_id,
            "shopify_product_title": product.title[:255],
            "shopify_sku": variant.sku,
            "dropi_variant_id": str(mapping.external_variant_id),
            "shopify_stock": variant.inventory_quantity,
        })

    result = []
    for entry in products:
        matches = by_product.get(str(entry.get("id")), []) if entry.get("id") else []
        remote_variants = {
            str(row["id"]): row for row in entry["variants"] if row.get("id") is not None
        }
        linked = []
        for match in sorted(matches, key=lambda x: x["product_variant_id"]):
            reference = remote_variants.get(match["dropi_variant_id"])
            # Absence of variations on a product index page does not mean
            # the mapping is wrong; inspect /products/v2/{id} for details.
            sku_check = _compare_sku(match["shopify_sku"], reference["sku"]) if reference else "unknown"
            stock_check = _compare_stock(match["shopify_stock"], reference["stock"]) if reference else "unknown"
            linked.append({
                "product_variant_id": match["product_variant_id"],
                "shopify_variant_id": match["shopify_variant_id"],
                "shopify_product_id": match["shopify_product_id"],
                "shopify_product_title": match["shopify_product_title"],
                "shopify_sku": match["shopify_sku"],
                "dropi_variant_id": match["dropi_variant_id"],
                "sku_check": sku_check,
                "stock_check": stock_check,
            })
        result.append({
            **entry,
            "shopify_mappings": linked,
            "mapping_status": "linked" if linked else "unmapped",
            "differences_detected": any(
                row["sku_check"] == "different" or row["stock_check"] == "different"
                for row in linked
            ),
        })
    return result


def list_catalog_page(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    page: int = 1,
    limit: int = 20,
    query: str = "",
) -> dict:
    store, connection, token = _connection_and_token(db, organization_id, store_id)
    if connection.status != "verified":
        raise DropiConnectionError("DROPPI_NOT_VERIFIED")

    page_data = search_products(
        token,
        country_code=store.country_code,
        page=page,
        limit=limit,
        query=query,
    )
    product_ids = [row["id"] for row in page_data["items"] if row["id"]]
    mapped_rows = []
    if product_ids:
        mapped_rows = (
            db.query(SupplierVariantMapping, ProductVariant, Product)
            .join(ProductVariant, ProductVariant.id == SupplierVariantMapping.product_variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .filter(
                SupplierVariantMapping.organization_id == organization_id,
                SupplierVariantMapping.store_id == store_id,
                SupplierVariantMapping.provider == "dropi",
                SupplierVariantMapping.active.is_(True),
                SupplierVariantMapping.external_product_id.in_(product_ids),
                Product.organization_id == organization_id,
                Product.store_id == store_id,
            )
            .all()
        )

    compared = attach_shopify_mappings(page_data["items"], mapped_rows)
    return {
        **page_data,
        "provider": "dropi",
        "country_code": store.country_code,
        "access_mode": "read_only",
        "shopify_write_performed": False,
        "items": compared,
        "unmapped_products": sum(item["mapping_status"] == "unmapped" for item in compared),
        "products_with_differences": sum(item["differences_detected"] for item in compared),
    }
