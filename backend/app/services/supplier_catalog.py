"""CJ supplier catalog and freight orchestration."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..integrations.cj import client as cj_client
from .supplier_connections import get_valid_cj_access_token


def _canonical_product(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": "cj",
        "external_product_id": str(raw.get("id") or raw.get("pid") or ""),
        "title": raw.get("nameEn") or raw.get("productNameEn") or "",
        "sku": raw.get("sku") or raw.get("spu") or raw.get("productSku"),
        "image_url": raw.get("bigImage") or raw.get("productImage"),
        "supplier_cost_usd": (
            raw.get("nowPrice")
            or raw.get("discountPrice")
            or raw.get("sellPrice")
        ),
        "suggested_sell_price": raw.get("suggestSellPrice"),
        "category_id": raw.get("categoryId"),
        "category_name": (
            raw.get("threeCategoryName")
            or raw.get("categoryName")
        ),
        "listed_count": raw.get("listedNum"),
    }


def _canonical_variant(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": "cj",
        "external_variant_id": str(raw.get("vid") or ""),
        "external_product_id": str(raw.get("pid") or ""),
        "title": raw.get("variantNameEn") or raw.get("variantName") or "",
        "sku": raw.get("variantSku"),
        "barcode": raw.get("barcode"),
        "image_url": raw.get("variantImage"),
        "option": raw.get("variantKey"),
        "supplier_cost_usd": raw.get("variantSellPrice"),
        "suggested_sell_price": raw.get("variantSugSellPrice"),
        "weight_g": raw.get("variantWeight"),
        "length_mm": raw.get("variantLength"),
        "width_mm": raw.get("variantWidth"),
        "height_mm": raw.get("variantHeight"),
    }


def _extract_list_v2_products(data: dict[str, Any]) -> list[dict[str, Any]]:
    content = data.get("content") or []
    products: list[dict[str, Any]] = []

    for entry in content:
        if not isinstance(entry, dict):
            continue
        product_list = entry.get("productList")
        if isinstance(product_list, list):
            products.extend(
                product
                for product in product_list
                if isinstance(product, dict)
            )
        else:
            products.append(entry)

    return products


def list_cj_products(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    query: str | None = None,
    limit: int = 20,
    page: int = 1,
) -> dict:
    token = get_valid_cj_access_token(db, organization_id, store_id)
    data = cj_client.list_products(
        token,
        query=query,
        limit=limit,
        page=page,
    )
    products = _extract_list_v2_products(data)

    return {
        "provider": "cj",
        "items": [_canonical_product(item) for item in products],
        "page": page,
        "limit": limit,
        "total": data.get("totalRecords"),
        "total_pages": data.get("totalPages"),
    }


def get_cj_product(
    db: Session,
    organization_id: int,
    store_id: int,
    product_id: str,
) -> dict:
    token = get_valid_cj_access_token(db, organization_id, store_id)
    raw = cj_client.get_product(token, product_id)
    result = _canonical_product(raw)
    result.update(
        {
            "description": raw.get("description") or "",
            "images": raw.get("productImageSet") or [],
            "logistics_properties": raw.get("productProEnSet") or [],
            "product_type": raw.get("productType"),
        }
    )
    raw_variants = raw.get("variants") or []
    result["variants"] = [
        _canonical_variant(item)
        for item in raw_variants
        if isinstance(item, dict)
    ]
    return result


def list_cj_variants(
    db: Session,
    organization_id: int,
    store_id: int,
    product_id: str,
    *,
    country_code: str | None = None,
) -> list[dict]:
    token = get_valid_cj_access_token(db, organization_id, store_id)
    items = cj_client.get_variants(
        token,
        product_id,
        country_code=country_code,
    )
    return [
        _canonical_variant(item)
        for item in items
        if isinstance(item, dict)
    ]


def get_cj_stock(
    db: Session,
    organization_id: int,
    store_id: int,
    variant_id: str,
) -> dict:
    token = get_valid_cj_access_token(db, organization_id, store_id)
    raw_warehouses = cj_client.get_stock(token, variant_id)

    warehouses = []
    total_inventory = 0
    for item in raw_warehouses:
        if not isinstance(item, dict):
            continue
        warehouse_total = int(item.get("totalInventoryNum") or 0)
        total_inventory += warehouse_total
        warehouses.append(
            {
                "warehouse_id": str(item.get("areaId") or ""),
                "warehouse_name": item.get("areaEn"),
                "country_code": item.get("countryCode"),
                "total_inventory": warehouse_total,
                "cj_inventory": int(item.get("cjInventoryNum") or 0),
                "factory_inventory": int(item.get("factoryInventoryNum") or 0),
            }
        )

    return {
        "provider": "cj",
        "external_variant_id": variant_id,
        "total_inventory": total_inventory,
        "warehouses": warehouses,
    }


def quote_cj_freight(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    start_country_code: str,
    end_country_code: str,
    items: list[dict],
    zip_code: str | None = None,
) -> dict:
    token = get_valid_cj_access_token(db, organization_id, store_id)
    raw_options = cj_client.calculate_freight(
        token,
        start_country_code=start_country_code,
        end_country_code=end_country_code,
        products=items,
        zip_code=zip_code,
    )

    options = []
    for item in raw_options:
        if not isinstance(item, dict):
            continue
        options.append(
            {
                "logistics_name": item.get("logisticName"),
                "transit_time": item.get("logisticAging"),
                "price_usd": (
                    item.get("totalPostageFee")
                    if item.get("totalPostageFee") is not None
                    else item.get("logisticPrice")
                ),
                "base_price_usd": item.get("logisticPrice"),
                "taxes_fee_usd": item.get("taxesFee"),
                "clearance_fee_usd": item.get("clearanceOperationFee"),
            }
        )

    return {
        "provider": "cj",
        "origin_country_code": start_country_code.upper(),
        "destination_country_code": end_country_code.upper(),
        "items": items,
        "options": options,
    }
