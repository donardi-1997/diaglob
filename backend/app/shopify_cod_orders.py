"""Shopify COD order creation for confirmed conversational checkouts.

This is intentionally separate from the historical POC order path. It creates
an actual Shopify order with pending payment, confirmed shipping data and
production Diaglob tags.
"""
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .automations import safe_emit_event
from .models import CommerceConnection, Order, OrderItem, ProductVariant, Store
from .shopify_client import (
    ORDER_CREATE_MUTATION,
    ShopifyAPIError,
    ShopifyGraphQLClient,
    ShopifyUserError,
)
from .shopify_security import decrypt_shopify_secret

COD_TAGS = ["DIAGLOB_CHAT", "DIAGLOB_COD"]


def _sanitize_error(message: str) -> str:
    message = re.sub(
        r"(access[-_ ]?token|token|password|secret)\s*[=:]\s*\S+",
        r"\1=***",
        message,
        flags=re.IGNORECASE,
    )
    return message[:500]


def _response(order: Order, *, idempotent: bool) -> dict:
    return {
        "ok": order.external_creation_status == "created",
        "idempotent": idempotent,
        "order_id": order.id,
        "order_number": order.order_number,
        "shopify_order_id": order.shopify_order_id,
        "status": order.lifecycle_status or order.external_creation_status,
        "total_amount": float(order.total_amount),
        "currency": order.currency,
        "external_creation_status": order.external_creation_status,
    }


def _shopify_shipping_address(address: dict) -> dict:
    result = {
        "firstName": address["first_name"],
        "address1": address["address1"],
        "city": address["city"],
        "countryCode": address["country_code"],
        "phone": address.get("phone"),
    }
    optional = {
        "lastName": address.get("last_name"),
        "address2": address.get("address2"),
        "province": address.get("province"),
        "provinceCode": address.get("province_code"),
        "zip": address.get("zip"),
    }
    result.update({key: value for key, value in optional.items() if value})
    return {key: value for key, value in result.items() if value}


def create_shopify_cod_order(
    *,
    db: Session,
    store: Store,
    connection: CommerceConnection,
    customer_id: int,
    variant_local_id: int,
    quantity: int,
    customer_email: str | None,
    customer_phone: str,
    shipping_address: dict,
    note: str,
    idempotency_key: str,
) -> dict:
    """Create one actual pending-payment Shopify order idempotently."""
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")

    existing = (
        db.query(Order)
        .filter(
            Order.organization_id == store.organization_id,
            Order.store_id == store.id,
            Order.idempotency_key == idempotency_key,
        )
        .first()
    )
    if existing:
        return _response(existing, idempotent=True)

    variant = (
        db.query(ProductVariant)
        .join(ProductVariant.product)
        .filter(
            ProductVariant.id == variant_local_id,
            ProductVariant.product.has(
                store_id=store.id,
                organization_id=store.organization_id,
                active=True,
            ),
        )
        .first()
    )
    if not variant:
        raise ValueError("Variant does not belong to this store")
    if not variant.shopify_variant_id:
        raise ValueError("Variant is not linked to Shopify")
    if not variant.available or int(variant.inventory_quantity or 0) < quantity:
        raise ValueError("Variant is out of stock")

    total = float(variant.price) * quantity
    order = Order(
        organization_id=store.organization_id,
        store_id=store.id,
        customer_id=customer_id,
        order_number=f"CHAT-COD-{idempotency_key[-12:].upper()}",
        total_amount=total,
        currency=store.currency,
        financial_status="pending",
        payment_method="cash_on_delivery",
        payment_status="pending",
        fulfillment_status=None,
        lifecycle_status=None,
        source="shopify_chat_cod",
        note=note,
        idempotency_key=idempotency_key,
        external_creation_status="pending",
        external_last_error=None,
    )
    db.add(order)

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(Order)
            .filter(
                Order.store_id == store.id,
                Order.idempotency_key == idempotency_key,
            )
            .first()
        )
        if existing:
            return _response(existing, idempotent=True)
        raise

    db.add(
        OrderItem(
            order_id=order.id,
            organization_id=store.organization_id,
            store_id=store.id,
            product_id=variant.product_id,
            variant_id=variant.id,
            shopify_variant_id=variant.shopify_variant_id,
            title=variant.product.title,
            sku=variant.sku,
            quantity=quantity,
            unit_price=float(variant.price),
            unit_cost=(float(variant.product.cost) if variant.product.cost is not None else None),
            currency=store.currency,
        )
    )
    db.commit()

    order_input = {
        "lineItems": [
            {
                "variantId": f"gid://shopify/ProductVariant/{variant.shopify_variant_id}",
                "quantity": quantity,
            }
        ],
        "phone": customer_phone,
        "shippingAddress": _shopify_shipping_address(shipping_address),
        "tags": COD_TAGS,
        "note": note,
    }
    if customer_email:
        order_input["email"] = customer_email

    try:
        token = decrypt_shopify_secret(connection.access_token_encrypted or "")
        data = ShopifyGraphQLClient(
            shop_domain=connection.external_store_url,
            access_token=token,
        ).query(ORDER_CREATE_MUTATION, {"order": order_input})
    except ShopifyAPIError as exc:
        order.external_creation_status = "unknown"
        order.external_last_error = _sanitize_error(str(exc))
        db.commit()
        raise

    result = data.get("orderCreate") or {}
    user_errors = result.get("userErrors") or []
    if user_errors:
        message = "; ".join(
            error.get("message", "Shopify user error") for error in user_errors
        )
        order.external_creation_status = "failed"
        order.external_last_error = _sanitize_error(message)
        db.commit()
        raise ShopifyUserError(_sanitize_error(message))

    shopify_order = result.get("order") or {}
    shopify_order_id = shopify_order.get("id")
    if not shopify_order_id:
        order.external_creation_status = "unknown"
        order.external_last_error = "Shopify returned no order ID"
        db.commit()
        raise RuntimeError("Shopify returned no order ID")

    order.shopify_order_id = shopify_order_id
    order.order_number = shopify_order.get("name") or order.order_number
    order.external_creation_status = "created"
    order.external_last_error = None
    order.lifecycle_status = "confirmed"
    order.lifecycle_synced_at = None
    db.commit()

    safe_emit_event(
        db=db,
        organization_id=store.organization_id,
        store_id=store.id,
        event_type="order.created",
        payload={
            "order": {
                "id": order.id,
                "store_id": store.id,
                "organization_id": store.organization_id,
                "source": order.source,
                "lifecycle_status": order.lifecycle_status,
                "payment_method": order.payment_method,
            }
        },
        event_id=f"order:{order.id}:created",
    )

    return _response(order, idempotent=False)
