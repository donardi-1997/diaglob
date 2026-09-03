import re
from sqlalchemy.orm import Session

from .models import CommerceConnection, Order, OrderItem, ProductVariant, Store
from .shopify_client import (
    ORDER_CREATE_MUTATION,
    ShopifyAPIError,
    ShopifyGraphQLClient,
    ShopifyUserError,
)
from .shopify_security import decrypt_shopify_secret


POC_TAGS = ["DIAGLOB_POC", "DIAGLOB_POC_API"]
POC_NOTE = "Created by Diaglob Shopify/Dropify POC"
SHOPIFY_VARIANT_GID_RE = re.compile(
    r"^gid://shopify/ProductVariant/[1-9][0-9]*$"
)


def _sanitize_error(message: str) -> str:
    message = re.sub(
        r"(access[-_ ]?token|token|password|secret)\s*[=:]\s*\S+",
        r"\1=***",
        message,
        flags=re.IGNORECASE,
    )
    return message[:500]


def _existing_response(order: Order) -> dict:
    return {
        "success": True,
        "idempotent": True,
        "shopify_order_id": order.shopify_order_id,
        "shopify_order_name": order.order_number,
        "tags": POC_TAGS,
    }


def create_poc_order(
    *,
    db: Session,
    store: Store,
    connection: CommerceConnection,
    variant_id: str,
    quantity: int,
    customer_email: str,
    customer_phone: str | None,
    shipping_address: dict,
    tags: list[str] | None,
    note: str | None,
    idempotency_key: str,
) -> dict:
    if not SHOPIFY_VARIANT_GID_RE.fullmatch(variant_id):
        raise ValueError("variant_id must be a Shopify ProductVariant GID")

    variant_number = variant_id.rsplit("/", 1)[1]
    variant = (
        db.query(ProductVariant)
        .join(ProductVariant.product)
        .filter(
            ProductVariant.shopify_variant_id == variant_number,
            ProductVariant.product.has(
                store_id=store.id,
                organization_id=store.organization_id,
            ),
        )
        .first()
    )
    if not variant:
        raise ValueError("Shopify variant does not belong to this store")

    existing = (
        db.query(Order)
        .filter(
            Order.store_id == store.id,
            Order.organization_id == store.organization_id,
            Order.idempotency_key == idempotency_key,
            Order.source == "shopify_poc",
        )
        .first()
    )
    if existing:
        return _existing_response(existing)

    order = Order(
        organization_id=store.organization_id,
        store_id=store.id,
        order_number=f"POC-{idempotency_key[:16]}",
        total_amount=float(variant.price) * quantity,
        currency=store.currency,
        financial_status="pending",
        fulfillment_status=None,
        source="shopify_poc",
        note=note or POC_NOTE,
        idempotency_key=idempotency_key,
        external_creation_status="pending",
        external_last_error=None,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            organization_id=store.organization_id,
            store_id=store.id,
            product_id=variant.product_id,
            variant_id=variant.id,
            shopify_variant_id=variant_number,
            title=variant.title,
            sku=variant.sku,
            quantity=quantity,
            unit_price=float(variant.price),
            currency=store.currency,
        )
    )
    db.commit()

    order_input = {
        "lineItems": [
            {
                "variantId": variant_id,
                "quantity": quantity,
            }
        ],
        "email": customer_email,
        "phone": customer_phone,
        "shippingAddress": {
            "firstName": shipping_address["first_name"],
            "lastName": shipping_address["last_name"],
            "address1": shipping_address["address1"],
            "address2": shipping_address.get("address2"),
            "city": shipping_address["city"],
            "province": shipping_address.get("province"),
            "provinceCode": shipping_address.get("province_code"),
            "countryCode": shipping_address["country_code"],
            "zip": shipping_address["zip"],
        },
        "tags": list(dict.fromkeys(POC_TAGS + (tags or []))),
        "note": note or POC_NOTE,
    }

    try:
        token = decrypt_shopify_secret(
            connection.access_token_encrypted or ""
        )
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
            error.get("message", "Shopify user error")
            for error in user_errors
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
    order.note = note or POC_NOTE
    db.commit()

    return {
        "success": True,
        "idempotent": False,
        "shopify_order_id": shopify_order_id,
        "shopify_order_name": order.order_number,
        "tags": order_input["tags"],
    }
