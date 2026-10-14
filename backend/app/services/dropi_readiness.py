"""Read-only Shopify order readiness diagnostics for a future Dropi adapter.

No external writes, customer PII, remote order payloads or order enqueueing.
All checks fail closed. A green readiness state never authorizes submission.
"""
from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from ..model_domains.supplier_variant_mappings import SupplierVariantMapping
from ..models import CommerceConnection, DropiConnection, Order, Product, ProductVariant, Store
from .order_confirmation import is_cod_order


class DropiReadinessError(Exception):
    """Sanitized code only."""


def assess_order(
    order: Order,
    mappings: dict[int, SupplierVariantMapping],
    resolved_variant_ids: dict[str, int],
    *,
    dropi_verified: bool,
    shopify_connected: bool,
    country_code: str,
) -> dict:
    """Pure adapter dry-run over an already tenant-checked Shopify order."""
    blockers = []
    if not shopify_connected:
        blockers.append("SHOPIFY_NOT_CONNECTED")
    if not dropi_verified:
        blockers.append("DROPI_NOT_VERIFIED")
    if (order.source or "").lower() != "shopify":
        blockers.append("DROPI_ORDER_NOT_FROM_SHOPIFY")
    payment_ready = (order.payment_status or "").lower() == "paid"
    cod = is_cod_order(order)
    confirmed_cod = cod and (order.confirmation_status or "").lower() == "confirmed"
    if not (payment_ready or confirmed_cod):
        blockers.append("PAYMENT_NOT_READY")
    if (order.fulfillment_status or "").lower() == "fulfilled" or (
        order.lifecycle_status or ""
    ).lower() in {"cancelled", "refunded", "voided", "fulfilled"}:
        blockers.append("ORDER_ALREADY_FINALIZED")

    shipping = order.shipping_address if isinstance(order.shipping_address, dict) else {}
    required_shipping = ("customer_name", "address1", "city", "province", "phone")
    missing_fields = [
        key for key in required_shipping if not str(shipping.get(key) or "").strip()
    ]
    if missing_fields:
        blockers.append("SHIPPING_INCOMPLETE")
    shipping_country = str(shipping.get("country_code") or "").upper().strip()
    if shipping_country != (country_code or "").upper():
        blockers.append("SHIPPING_COUNTRY_MISMATCH")

    prepared_items = []
    if not order.items:
        blockers.append("ORDER_HAS_NO_ITEMS")
    if len(order.items) > 50:
        blockers.append("DROPI_TOO_MANY_ORDER_ITEMS")

    for item in order.items[:50]:
        variant_id = item.variant_id
        if variant_id is None and item.shopify_variant_id:
            variant_id = resolved_variant_ids.get(str(item.shopify_variant_id))
        mapping = mappings.get(variant_id) if variant_id is not None else None
        if mapping is None or not mapping.active:
            blockers.append("DROPI_VARIANT_UNMAPPED")
        if not isinstance(item.quantity, int) or not 1 <= item.quantity <= 1000:
            blockers.append("DROPI_QUANTITY_INVALID")
        prepared_items.append({
            "order_item_id": item.id,
            "shopify_variant_id": item.shopify_variant_id,
            "sku": item.sku,
            "quantity": item.quantity,
            "mapped": bool(mapping and mapping.active),
            "dropi_product_id": mapping.external_product_id if mapping and mapping.active else None,
            "dropi_variant_id": mapping.external_variant_id if mapping and mapping.active else None,
        })

    # Stable per-store/per-source-order key; never derived from names or addresses.
    source_order_key = order.shopify_order_id or str(order.id)
    fingerprint = hashlib.sha256(
        f"dropi:v1:{order.organization_id}:{order.store_id}:{source_order_key}".encode("utf-8")
    ).hexdigest()

    return {
        "provider": "dropi",
        "order_id": order.id,
        "shopify_order_id": order.shopify_order_id,
        "order_number": order.order_number,
        "dry_run": True,
        "ready_for_provider_contract_test": not blockers,
        "can_send_to_dropi": False,  # NEVER authorize fulfillment via this endpoint.
        "idempotency_key": "dropi_" + fingerprint[:32],
        "rate_type": "CON RECAUDO" if cod else "SIN RECAUDO",
        "missing_shipping_fields": missing_fields,
        "blockers": sorted(set(blockers)),
        "items": prepared_items,
    }


def order_readiness(
    db: Session, organization_id: int, store_id: int, order_id: int
) -> dict:
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
        raise DropiReadinessError("DROPI_STORE_NOT_FOUND")
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
        .first()
    )
    if order is None:
        raise DropiReadinessError("DROPI_ORDER_NOT_FOUND")
    connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.organization_id == organization_id,
            DropiConnection.store_id == store_id,
        )
        .first()
    )
    shopify = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == store_id,
            CommerceConnection.provider == "shopify",
            CommerceConnection.status == "connected",
        )
        .first()
    )
    mapping_rows = (
        db.query(SupplierVariantMapping)
        .filter(
            SupplierVariantMapping.organization_id == organization_id,
            SupplierVariantMapping.store_id == store_id,
            SupplierVariantMapping.provider == "dropi",
            SupplierVariantMapping.active.is_(True),
        )
        .all()
    )
    mappings = {mapping.product_variant_id: mapping for mapping in mapping_rows}
    local_variants = (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.organization_id == organization_id,
            Product.store_id == store_id,
        )
        .all()
    )
    resolved = {
        str(variant.shopify_variant_id): variant.id
        for variant in local_variants
        if variant.shopify_variant_id
    }
    return assess_order(
        order, mappings, resolved,
        dropi_verified=bool(connection and connection.status == "verified"),
        shopify_connected=shopify is not None,
        country_code=store.country_code,
    )
