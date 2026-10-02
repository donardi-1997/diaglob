"""Secure Shopify order webhook ingestion.

Shopify sends order lifecycle events with the complete order payload. This module
verifies HMAC signatures, resolves the tenant/store from the Shopify domain, and
upserts customer/order/item state idempotently.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..automations import safe_emit_event
from ..models import (
    CommerceConnection,
    Customer,
    CustomerStoreProfile,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    Store,
)
from ..shopify_oauth import get_shopify_client_secret, normalize_shop_domain

logger = logging.getLogger(__name__)

SUPPORTED_TOPICS = frozenset(
    {
        "orders/create",
        "orders/updated",
        "orders/cancelled",
    }
)


class ShopifyWebhookError(Exception):
    """Raised when an authenticated Shopify webhook cannot be processed safely."""


def verify_shopify_webhook_hmac(
    raw_body: bytes,
    hmac_header: str | None,
) -> bool:
    """Verify Shopify's base64 encoded HMAC-SHA256 request signature."""
    if not raw_body or not hmac_header:
        return False

    try:
        secret = get_shopify_client_secret()
    except RuntimeError:
        logger.error("SHOPIFY_CLIENT_SECRET is not configured for webhook verification")
        return False

    digest = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")

    return hmac.compare_digest(expected, hmac_header.strip())


def resolve_shopify_connection(
    db: Session,
    shop_domain: str,
) -> CommerceConnection | None:
    """Resolve one active Shopify connection from the authenticated shop header."""
    try:
        normalized = normalize_shop_domain(shop_domain)
    except (ValueError, AttributeError):
        return None

    return (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider == "shopify",
            CommerceConnection.external_store_url == normalized,
            CommerceConnection.status == "connected",
        )
        .first()
    )


def process_shopify_order_webhook(
    db: Session,
    *,
    connection: CommerceConnection,
    topic: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Upsert one Shopify order event into the connected tenant/store."""
    if topic not in SUPPORTED_TOPICS:
        return {
            "ok": True,
            "action": "ignored",
            "topic": topic,
        }

    if not isinstance(payload, dict):
        raise ShopifyWebhookError("INVALID_PAYLOAD")

    external_order_id = _string_id(payload.get("id"))
    if not external_order_id:
        raise ShopifyWebhookError("ORDER_ID_REQUIRED")

    store = (
        db.query(Store)
        .filter(
            Store.id == connection.store_id,
            Store.organization_id == connection.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if store is None:
        raise ShopifyWebhookError("STORE_NOT_FOUND")

    customer = _upsert_customer(
        db,
        store=store,
        payload=payload,
    )

    order = (
        db.query(Order)
        .filter(
            Order.organization_id == connection.organization_id,
            Order.store_id == connection.store_id,
            Order.shopify_order_id == external_order_id,
        )
        .first()
    )
    created = order is None

    if order is None:
        order = Order(
            organization_id=connection.organization_id,
            store_id=connection.store_id,
            shopify_order_id=external_order_id,
            external_order_id=external_order_id,
            order_number=_order_number(payload, external_order_id),
            total_amount=_money(
                payload.get("current_total_price")
                or payload.get("total_price")
                or 0
            ),
            currency=_currency(payload, store.currency),
            source="shopify",
            external_creation_status="created",
            created_at=_parse_datetime(payload.get("created_at"))
            or datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(order)
        db.flush()

    _apply_order_fields(
        order,
        payload=payload,
        topic=topic,
        customer=customer,
        store=store,
    )
    _replace_order_items(
        db,
        order=order,
        payload=payload,
        store=store,
    )

    db.commit()
    db.refresh(order)

    if customer is not None:
        _refresh_customer_store_profile(
            db,
            store=store,
            customer=customer,
            external_customer_id=_shopify_customer_id(payload),
            last_order_ref=order.order_number,
        )
        db.commit()

    if created:
        safe_emit_event(
            db=db,
            organization_id=connection.organization_id,
            store_id=connection.store_id,
            event_type="order.created",
            payload={
                "order": {
                    "id": order.id,
                    "order_number": order.order_number,
                    "total_amount": float(order.total_amount),
                    "currency": order.currency,
                    "financial_status": order.financial_status,
                    "payment_status": order.payment_status,
                    "fulfillment_status": order.fulfillment_status,
                    "source": "shopify",
                },
                "customer_id": order.customer_id,
            },
            event_id=f"shopify:order:{external_order_id}:created",
        )

    return {
        "ok": True,
        "action": "created" if created else "updated",
        "order_id": order.id,
        "shopify_order_id": external_order_id,
        "topic": topic,
    }


def _apply_order_fields(
    order: Order,
    *,
    payload: dict[str, Any],
    topic: str,
    customer: Customer | None,
    store: Store,
) -> None:
    order.customer_id = customer.id if customer is not None else None
    order.external_order_id = _string_id(payload.get("id"))
    order.order_number = _order_number(payload, order.external_order_id or str(order.id))
    order.total_amount = _money(
        payload.get("current_total_price")
        or payload.get("total_price")
        or order.total_amount
        or 0
    )
    order.currency = _currency(payload, store.currency)
    order.financial_status = _clean_text(payload.get("financial_status"), 50)
    order.payment_status = _normalize_payment_status(payload.get("financial_status"))
    order.payment_method = _payment_method(payload)
    order.fulfillment_status = (
        _clean_text(payload.get("fulfillment_status"), 50)
        or "unfulfilled"
    )
    order.lifecycle_status = _lifecycle_status(payload, topic)
    order.lifecycle_synced_at = datetime.utcnow()
    order.note = _clean_text(payload.get("note"), 10000)
    order.source = "shopify"
    order.external_creation_status = "created"
    order.external_last_error = None
    order.shipping_address = _shipping_address(payload)
    order.updated_at = _parse_datetime(payload.get("updated_at")) or datetime.utcnow()


def _replace_order_items(
    db: Session,
    *,
    order: Order,
    payload: dict[str, Any],
    store: Store,
) -> None:
    line_items = payload.get("line_items") or []
    if not isinstance(line_items, list):
        raise ShopifyWebhookError("INVALID_LINE_ITEMS")

    existing_items = {
        item.shopify_line_item_id: item
        for item in db.query(OrderItem)
        .filter(
            OrderItem.order_id == order.id,
            OrderItem.shopify_line_item_id.isnot(None),
        )
        .all()
        if item.shopify_line_item_id
    }
    seen_line_item_ids: set[str] = set()

    for line in line_items:
        if not isinstance(line, dict):
            continue

        shopify_line_item_id = _string_id(line.get("id"))
        shopify_variant_id = _string_id(line.get("variant_id"))
        local_variant = _find_local_variant(
            db,
            store_id=store.id,
            shopify_variant_id=shopify_variant_id,
        )

        title = (
            _clean_text(line.get("title"), 255)
            or _clean_text(line.get("name"), 255)
            or "Shopify item"
        )
        sku = _clean_text(line.get("sku"), 255)
        quantity = _int_value(line.get("quantity"), minimum=1, default=1)
        unit_price = _money(line.get("price") or 0)

        item = (
            existing_items.get(shopify_line_item_id)
            if shopify_line_item_id
            else None
        )

        if item is None:
            item = OrderItem(
                order_id=order.id,
                organization_id=store.organization_id,
                store_id=store.id,
                shopify_line_item_id=shopify_line_item_id,
                currency=order.currency,
            )
            db.add(item)

        item.product_id = local_variant.product_id if local_variant else None
        item.variant_id = local_variant.id if local_variant else None
        item.shopify_variant_id = shopify_variant_id
        item.title = title
        item.sku = sku
        item.quantity = quantity
        item.unit_price = unit_price
        item.currency = order.currency

        if shopify_line_item_id:
            seen_line_item_ids.add(shopify_line_item_id)

    stale_ids = set(existing_items) - seen_line_item_ids
    if stale_ids:
        (
            db.query(OrderItem)
            .filter(
                OrderItem.order_id == order.id,
                OrderItem.shopify_line_item_id.in_(stale_ids),
            )
            .delete(synchronize_session=False)
        )


def _find_local_variant(
    db: Session,
    *,
    store_id: int,
    shopify_variant_id: str | None,
) -> ProductVariant | None:
    if not shopify_variant_id:
        return None

    return (
        db.query(ProductVariant)
        .join(Product, Product.id == ProductVariant.product_id)
        .filter(
            Product.store_id == store_id,
            ProductVariant.shopify_variant_id == shopify_variant_id,
        )
        .first()
    )


def _upsert_customer(
    db: Session,
    *,
    store: Store,
    payload: dict[str, Any],
) -> Customer | None:
    customer_payload = payload.get("customer")
    customer_data = customer_payload if isinstance(customer_payload, dict) else {}

    shipping = payload.get("shipping_address")
    shipping_data = shipping if isinstance(shipping, dict) else {}

    billing = payload.get("billing_address")
    billing_data = billing if isinstance(billing, dict) else {}

    external_customer_id = _string_id(customer_data.get("id"))
    email = (
        _clean_text(customer_data.get("email"), 200)
        or _clean_text(payload.get("email"), 200)
    )
    phone = (
        _clean_text(customer_data.get("phone"), 50)
        or _clean_text(shipping_data.get("phone"), 50)
        or _clean_text(billing_data.get("phone"), 50)
        or ""
    )

    first_name = (
        _clean_text(customer_data.get("first_name"), 80)
        or _clean_text(shipping_data.get("first_name"), 80)
        or _clean_text(billing_data.get("first_name"), 80)
        or ""
    )
    last_name = (
        _clean_text(customer_data.get("last_name"), 80)
        or _clean_text(shipping_data.get("last_name"), 80)
        or _clean_text(billing_data.get("last_name"), 80)
        or ""
    )
    name = " ".join(part for part in (first_name, last_name) if part).strip()
    if not name:
        name = _clean_text(shipping_data.get("name"), 150) or email or phone or "Shopify customer"

    country_code = (
        _clean_text(shipping_data.get("country_code"), 2)
        or _clean_text(billing_data.get("country_code"), 2)
    )
    if country_code:
        country_code = country_code.upper()

    if not external_customer_id and not email and not phone:
        return None

    customer: Customer | None = None

    if external_customer_id:
        profile = (
            db.query(CustomerStoreProfile)
            .filter(
                CustomerStoreProfile.organization_id == store.organization_id,
                CustomerStoreProfile.store_id == store.id,
                CustomerStoreProfile.external_customer_id == external_customer_id,
            )
            .first()
        )
        if profile is not None:
            customer = profile.customer

    if customer is None and phone:
        customer = (
            db.query(Customer)
            .filter(
                Customer.organization_id == store.organization_id,
                Customer.phone == phone,
            )
            .first()
        )

    if customer is None and email:
        customer = (
            db.query(Customer)
            .filter(
                Customer.organization_id == store.organization_id,
                func.lower(Customer.email) == email.lower(),
            )
            .first()
        )

    if customer is None:
        customer = Customer(
            organization_id=store.organization_id,
            name=name[:150],
            phone=phone[:50],
            email=email,
            country_code=country_code,
        )
        db.add(customer)
        db.flush()
    else:
        customer.name = name[:150]
        if phone:
            customer.phone = phone[:50]
        if email:
            customer.email = email
        if country_code:
            customer.country_code = country_code

    _ensure_customer_store_profile(
        db,
        store=store,
        customer=customer,
        external_customer_id=external_customer_id,
    )
    return customer


def _ensure_customer_store_profile(
    db: Session,
    *,
    store: Store,
    customer: Customer,
    external_customer_id: str | None,
) -> CustomerStoreProfile:
    profile = (
        db.query(CustomerStoreProfile)
        .filter(
            CustomerStoreProfile.customer_id == customer.id,
            CustomerStoreProfile.store_id == store.id,
        )
        .first()
    )
    if profile is None:
        profile = CustomerStoreProfile(
            organization_id=store.organization_id,
            customer_id=customer.id,
            store_id=store.id,
            external_customer_id=external_customer_id,
            orders_count=0,
            total_spent=0,
            currency=store.currency,
        )
        db.add(profile)
        db.flush()
    elif external_customer_id and not profile.external_customer_id:
        profile.external_customer_id = external_customer_id

    return profile


def _refresh_customer_store_profile(
    db: Session,
    *,
    store: Store,
    customer: Customer,
    external_customer_id: str | None,
    last_order_ref: str,
) -> None:
    profile = _ensure_customer_store_profile(
        db,
        store=store,
        customer=customer,
        external_customer_id=external_customer_id,
    )

    aggregates = (
        db.query(
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_amount), 0),
        )
        .filter(
            Order.organization_id == store.organization_id,
            Order.store_id == store.id,
            Order.customer_id == customer.id,
            Order.lifecycle_status != "cancelled",
        )
        .one()
    )
    profile.orders_count = int(aggregates[0] or 0)
    profile.total_spent = aggregates[1] or Decimal("0")
    profile.currency = store.currency
    profile.last_order_ref = last_order_ref


def _shopify_customer_id(payload: dict[str, Any]) -> str | None:
    customer = payload.get("customer")
    if not isinstance(customer, dict):
        return None
    return _string_id(customer.get("id"))


def _shipping_address(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = payload.get("shipping_address")
    if not isinstance(raw, dict) or not raw:
        return None

    first = _clean_text(raw.get("first_name"), 100) or ""
    last = _clean_text(raw.get("last_name"), 100) or ""
    customer_name = " ".join(part for part in (first, last) if part).strip()
    customer_name = customer_name or _clean_text(raw.get("name"), 150) or "Customer"

    return {
        "customer_name": customer_name,
        "first_name": first or None,
        "last_name": last or None,
        "company": _clean_text(raw.get("company"), 150),
        "address1": _clean_text(raw.get("address1"), 500),
        "address2": _clean_text(raw.get("address2"), 500),
        "city": _clean_text(raw.get("city"), 100),
        "province": _clean_text(raw.get("province"), 100),
        "province_code": _clean_text(raw.get("province_code"), 20),
        "country": _clean_text(raw.get("country"), 100),
        "country_code": (
            (_clean_text(raw.get("country_code"), 2) or "").upper() or None
        ),
        "zip": _clean_text(raw.get("zip"), 30),
        "phone": _clean_text(raw.get("phone"), 50),
        "email": _clean_text(payload.get("email"), 200),
    }


def _lifecycle_status(payload: dict[str, Any], topic: str) -> str:
    if topic == "orders/cancelled" or payload.get("cancelled_at"):
        return "cancelled"

    fulfillment = str(payload.get("fulfillment_status") or "").lower()
    financial = str(payload.get("financial_status") or "").lower()

    if fulfillment == "fulfilled":
        return "fulfilled"
    if financial == "paid":
        return "paid"
    if financial in {"refunded", "voided"}:
        return financial
    return "open"


def _normalize_payment_status(value: Any) -> str | None:
    status = str(value or "").strip().lower()
    if not status:
        return None

    aliases = {
        "partially_paid": "partial",
        "partially_refunded": "partial_refund",
        "authorized": "authorized",
        "pending": "pending",
        "paid": "paid",
        "refunded": "refunded",
        "voided": "voided",
    }
    return aliases.get(status, status[:50])


def _payment_method(payload: dict[str, Any]) -> str | None:
    gateways = payload.get("payment_gateway_names")
    if isinstance(gateways, list) and gateways:
        return _clean_text(gateways[0], 50)
    return _clean_text(payload.get("gateway"), 50)


def _order_number(payload: dict[str, Any], fallback: str) -> str:
    number = payload.get("order_number")
    if number not in (None, ""):
        return str(number)[:100]

    name = str(payload.get("name") or "").strip()
    if name:
        return name.lstrip("#")[:100]

    return fallback[:100]


def _currency(payload: dict[str, Any], fallback: str) -> str:
    value = str(payload.get("currency") or fallback or "USD").strip().upper()
    return value[:3] or "USD"


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _int_value(value: Any, *, minimum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _string_id(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _clean_text(value: Any, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    return cleaned[:max_length]


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        normalized = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError):
        return None
