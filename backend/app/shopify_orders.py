from .shopify_token_lifecycle import connection_access_token
import uuid
import re
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    CommerceConnection,
    Order,
    OrderItem,
    ProductVariant,
    Store,
)
from .shopify_client import (
    DRAFT_ORDER_CREATE_MUTATION,
    ShopifyAuthError,
    ShopifyGraphQLClient,
    ShopifyGraphQLError,
    ShopifyAPIError,
    ShopifyUserError,
)
from .shopify_security import decrypt_shopify_secret
from .automations import safe_emit_event
from .services.catalog_availability import variant_is_purchasable
from .services.shopify_privacy_suppression import evaluate_shopify_local_privacy


def build_draft_order_input(
    *,
    line_items: list[dict],
    note: str | None,
    customer_email: str | None,
    customer_name: str | None,
    customer_phone: str | None = None,
    shipping_address: dict | None = None,
) -> dict:
    """Build only fields supported by Shopify's DraftOrderInput.

    DraftOrderInput has no `name` property. Buyer name supplied to DIAGLOB
    is metadata, not the draft order name or an authenticated Shopify Customer.
    Never invent a customer identity by setting an unsupported GraphQL field.
    """
    payload = {"lineItems": line_items}
    if note:
        payload["note"] = note
    if customer_email:
        payload["email"] = customer_email
    if customer_name and customer_name.strip():
        payload["customAttributes"] = [
            {"key": "diaglob_customer_name", "value": customer_name.strip()},
        ]
    if customer_phone:
        payload["phone"] = customer_phone
    if shipping_address is not None:
        # MailingAddressInput has no province text field. In particular,
        # do not blindly forward input supplied by a buyer or AI agent.
        supported = {
            "firstName", "lastName", "address1", "address2",
            "city", "countryCode", "provinceCode", "zip", "phone",
            "company",
        }
        if not isinstance(shipping_address, dict):
            raise ValueError("SHOPIFY_DRAFT_SHIPPING_ADDRESS_INVALID")
        extra = set(shipping_address) - supported
        if extra or not shipping_address.get("address1") or not shipping_address.get("countryCode"):
            raise ValueError("SHOPIFY_DRAFT_SHIPPING_ADDRESS_INVALID")
        payload["shippingAddress"] = {
            key: value for key, value in shipping_address.items()
            if value is not None and value != ""
        }
    return payload


def _sanitize_error(msg: str) -> str:
    msg = re.sub(
        r"token\s*[=:]\s*\S+",
        "token=***",
        msg,
        flags=re.IGNORECASE,
    )
    msg = re.sub(
        r"password\s*[=:]\s*\S+",
        "password=***",
        msg,
        flags=re.IGNORECASE,
    )
    msg = re.sub(
        r"Bearer\s+\S+",
        "Bearer ***",
        msg,
        flags=re.IGNORECASE,
    )
    return msg[:500]


def _build_line_item_gid(
    variant: ProductVariant,
) -> str:
    return (
        f"gid://shopify/"
        f"ProductVariant/"
        f"{variant.shopify_variant_id}"
    )


def _validate_and_build_items(
    *,
    db: Session,
    store: Store,
    items_payload: list[dict],
) -> tuple[dict, list[dict]]:
    if not items_payload:
        raise ValueError(
            "At least one item is required"
        )

    variant_ids = [
        item["variant_local_id"]
        for item in items_payload
    ]

    variants = (
        db.query(ProductVariant)
        .filter(
            ProductVariant.id.in_(variant_ids),
        )
        .all()
    )

    variant_map = {v.id: v for v in variants}

    for item in items_payload:
        vid = item["variant_local_id"]

        if vid not in variant_map:
            raise ValueError(
                f"Variant {vid} not found"
            )

        variant = variant_map[vid]
        product = variant.product

        if (
            product is None
            or product.store_id != store.id
            or product.organization_id != store.organization_id
        ):
            raise ValueError(
                f"Variant {vid} does not belong "
                f"to this store"
            )

        quantity = item.get("quantity", 0)

        if quantity <= 0:
            raise ValueError(
                f"Quantity must be > 0 for "
                f"variant {vid}"
            )

        if not variant.shopify_variant_id or not variant_is_purchasable(variant, quantity):
            raise ValueError(f"Variant {vid} is not purchasable")

    quantities: dict[int, int] = {}
    for item in items_payload:
        vid = item["variant_local_id"]
        quantities[vid] = quantities.get(vid, 0) + item["quantity"]
    for vid, quantity in quantities.items():
        if not variant_is_purchasable(variant_map[vid], quantity):
            raise ValueError(f"Variant {vid} has insufficient verified stock")

    shopify_line_items = []

    for item in items_payload:
        variant = variant_map[
            item["variant_local_id"]
        ]

        shopify_line_items.append(
            {
                "variantId": _build_line_item_gid(
                    variant
                ),
                "quantity": item["quantity"],
            }
        )

    return variant_map, shopify_line_items


def _build_order_response(
    order: Order,
    *,
    idempotent: bool = False,
) -> dict:
    items = [
        {
            "id": item.id,
            "title": item.title,
            "sku": item.sku,
            "quantity": item.quantity,
            "unit_price": float(
                item.unit_price
            ),
            "currency": item.currency,
            "shopify_variant_id": (
                item.shopify_variant_id
            ),
        }
        for item in order.items
    ]

    return {
        "ok": True,
        "idempotent": idempotent,
        "order_id": order.id,
        "status": (
            order.financial_status or "pending"
        ),
        "shopify_draft_order_id": (
            order.shopify_draft_order_id
        ),
        "invoice_url": order.invoice_url,
        "total_amount": float(
            order.total_amount
        ),
        "currency": order.currency,
        "order_number": order.order_number,
        "external_creation_status": (
            order.external_creation_status
        ),
        "items": items,
    }


def create_shopify_draft_order(
    *,
    db: Session,
    store: Store,
    connection: CommerceConnection,
    items_payload: list[dict],
    customer_email: str | None = None,
    customer_name: str | None = None,
    note: str | None = None,
    idempotency_key: str | None = None,
    customer_phone: str | None = None,
    customer_id: int | None = None,
    shipping_address: dict | None = None,
    source: str = "shopify",
) -> dict:
    """
    Creates a Shopify Draft Order with proper
    lifecycle tracking via external_creation_status.

    Transaction flow:
      1. Idempotency check with status-aware
         retry policy.
      2. Validate variants belong to store.
      3. Create local Order
         (external_creation_status="pending").
      4. Create OrderItems.
      5. Flush + COMMIT (persist local intent
         BEFORE Shopify call).
      6. Call Shopify draftOrderCreate.
      7. On SUCCESS:
         external_creation_status="created",
         save shopify_draft_order_id + invoice_url.
      8. On DETERMINISTIC FAILURE:
         external_creation_status="failed".
      9. On AMBIGUOUS FAILURE:
         external_creation_status="unknown".
     10. COMMIT.

    Retry policy (store_id, idempotency_key):
      created  → return existing, NO Shopify call
      pending  → return existing, NO Shopify call
      unknown  → return existing, NO Shopify call
      failed   → reuse order, retry Shopify
    """

    # No draft order or existing retry may reinstate an actively suppressed buyer.
    privacy_block = evaluate_shopify_local_privacy(
        db, organization_id=store.organization_id, store_id=store.id,
        local_customer_id=customer_id,
        customer_email=customer_email,
        customer_phone=customer_phone,
    )
    if privacy_block:
        raise ValueError("SHOPIFY_PRIVACY_SUPPRESSED")

    # ------------------------------------------
    # 1. IDEMPOTENCY CHECK
    # ------------------------------------------

    existing_order = None

    if idempotency_key:
        existing_order = (
            db.query(Order)
            .filter(
                Order.idempotency_key
                == idempotency_key,
                Order.store_id == store.id,
            )
            .first()
        )

        if existing_order:
            ecs = (
                existing_order
                .external_creation_status
            )

            if ecs == "created":
                return _build_order_response(
                    existing_order,
                    idempotent=True,
                )

            if ecs in ("pending", "unknown"):
                return _build_order_response(
                    existing_order,
                    idempotent=True,
                )

            # ecs == "failed": fall through to retry

    # ------------------------------------------
    # 2. VALIDATE + BUILD LINE ITEMS
    # ------------------------------------------

    variant_map, shopify_line_items = (
        _validate_and_build_items(
            db=db,
            store=store,
            items_payload=items_payload,
        )
    )

    # ------------------------------------------
    # 3. CREATE LOCAL ORDER (if new)
    # ------------------------------------------

    if existing_order:
        order = existing_order
    else:
        order = Order(
            organization_id=(
                store.organization_id
            ),
            store_id=store.id,
            order_number=(
                f"DRAFT-"
                f"{uuid.uuid4().hex[:8].upper()}"
            ),
            total_amount=0,
            currency=store.currency,
            financial_status="pending",
            payment_status="pending",
            customer_id=customer_id,
            fulfillment_status=None,
            source=source,
            shopify_draft_order_id=None,
            invoice_url=None,
            idempotency_key=idempotency_key,
            note=note,
            external_creation_status="pending",
            external_last_error=None,
        )

        db.add(order)

        try:
            db.flush()
        except IntegrityError:
            db.rollback()

            if idempotency_key:
                existing = (
                    db.query(Order)
                    .filter(
                        Order.idempotency_key
                        == idempotency_key,
                        Order.store_id
                        == store.id,
                    )
                    .first()
                )

                if existing:
                    return _build_order_response(
                        existing,
                        idempotent=True,
                    )

            raise

    # ------------------------------------------
    # 4. CREATE ORDER ITEMS (if new order)
    # ------------------------------------------

    if not existing_order:
        for item in items_payload:
            variant = variant_map[
                item["variant_local_id"]
            ]

            order_item = OrderItem(
                order_id=order.id,
                organization_id=(
                    store.organization_id
                ),
                store_id=store.id,
                product_id=(
                    variant.product_id
                ),
                variant_id=variant.id,
                shopify_variant_id=(
                    variant.shopify_variant_id
                ),
                title=variant.title,
                sku=variant.sku,
                quantity=item["quantity"],
                unit_price=float(
                    variant.price
                ),
                currency=store.currency,
            )

            db.add(order_item)

    # ------------------------------------------
    # 5. FLUSH + COMMIT local intent
    #    UNIQUE constraint protects against
    #    concurrent duplicates.
    #
    #    If retrying a failed order, reset to
    #    "pending" BEFORE commit so that a crash
    #    between commit and Shopify call leaves
    #    the order in "pending" (no retry) rather
    #    than "failed" (would retry again).
    # ------------------------------------------

    if existing_order:
        order.external_creation_status = "pending"
        order.external_last_error = None

    try:
        db.flush()
    except IntegrityError:
        db.rollback()

        if idempotency_key:
            existing = (
                db.query(Order)
                .filter(
                    Order.idempotency_key
                    == idempotency_key,
                    Order.store_id
                    == store.id,
                )
                .first()
            )

            if existing:
                return _build_order_response(
                    existing,
                    idempotent=True,
                )

        raise

    db.commit()

    # ------------------------------------------
    # 6. CALL SHOPIFY
    # ------------------------------------------

    try:
        token = connection_access_token(connection, decrypt_legacy=decrypt_shopify_secret)

        client = ShopifyGraphQLClient(
            shop_domain=(
                connection.external_store_url
            ),
            access_token=token,
        )

        shopify_input = build_draft_order_input(
            line_items=shopify_line_items,
            note=note,
            customer_email=customer_email,
            customer_name=customer_name,
            customer_phone=customer_phone,
            shipping_address=shipping_address,
        )

        data = client.query(
            DRAFT_ORDER_CREATE_MUTATION,
            {"input": shopify_input},
        )

    except ShopifyUserError as exc:
        order.external_creation_status = (
            "failed"
        )
        order.external_last_error = (
            _sanitize_error(str(exc))
        )
        db.commit()

        # Emit order.failed event for automations
        safe_emit_event(
            db=db,
            organization_id=store.organization_id,
            store_id=store.id,
            event_type="order.failed",
            payload={
                "order": {
                    "id": order.id,
                    "store_id": store.id,
                    "organization_id": store.organization_id,
                    "source": order.source,
                    "external_creation_status": "failed",
                },
                "error": {
                    "type": "ShopifyUserError",
                    "message": _sanitize_error(str(exc)),
                },
            },
            event_id=f"order:{order.id}:failed",
        )
        raise

    except ShopifyAuthError as exc:
        order.external_creation_status = (
            "failed"
        )
        order.external_last_error = (
            _sanitize_error(str(exc))
        )
        db.commit()

        # Emit order.failed event for automations
        safe_emit_event(
            db=db,
            organization_id=store.organization_id,
            store_id=store.id,
            event_type="order.failed",
            payload={
                "order": {
                    "id": order.id,
                    "store_id": store.id,
                    "organization_id": store.organization_id,
                    "source": order.source,
                    "external_creation_status": "failed",
                },
                "error": {
                    "type": "ShopifyAuthError",
                    "message": _sanitize_error(str(exc)),
                },
            },
            event_id=f"order:{order.id}:failed",
        )
        raise

    except (
        ShopifyAPIError,
        ShopifyGraphQLError,
    ) as exc:
        order.external_creation_status = (
            "unknown"
        )
        order.external_last_error = (
            _sanitize_error(str(exc))
        )
        db.commit()
        raise

    # ------------------------------------------
    # 7. CHECK USER ERRORS (explicit check)
    # ------------------------------------------

    draft_data = (
        data.get("draftOrderCreate") or {}
    )

    user_errors = (
        draft_data.get("userErrors") or []
    )

    if user_errors:
        error_msg = (
            user_errors[0].get(
                "message",
                "Shopify user error",
            )
        )

        order.external_creation_status = (
            "failed"
        )
        order.external_last_error = (
            _sanitize_error(error_msg)
        )
        db.commit()

        # Emit order.failed event for automations
        safe_emit_event(
            db=db,
            organization_id=store.organization_id,
            store_id=store.id,
            event_type="order.failed",
            payload={
                "order": {
                    "id": order.id,
                    "store_id": store.id,
                    "organization_id": store.organization_id,
                    "source": order.source,
                    "external_creation_status": "failed",
                },
                "error": {
                    "type": "ShopifyUserError",
                    "message": _sanitize_error(error_msg),
                },
            },
            event_id=f"order:{order.id}:failed",
        )

        raise ShopifyUserError(error_msg)

    # ------------------------------------------
    # 8. SUCCESS
    # ------------------------------------------

    draft_order = (
        draft_data.get("draftOrder") or {}
    )

    shopify_gid = draft_order.get("id", "")

    total_price_str = (
        draft_order.get("totalPriceSet", {})
        .get("shopMoney", {})
        .get("amount", "0")
    )

    currency_code = (
        draft_order.get("totalPriceSet", {})
        .get("shopMoney", {})
        .get(
            "currencyCode",
            store.currency,
        )
    )

    invoice_url = (
        draft_order.get("invoiceUrl")
    )
    if source == "shopify_chat_checkout":
        # A failed/malformed response could have created a draft in Shopify.
        # Fail closed and do NOT retry blindly, or claim any order completed.
        url = urlsplit(invoice_url) if isinstance(invoice_url, str) else None
        if (
            not shopify_gid
            or url is None
            or url.scheme != "https"
            # Invoice URLs must resolve to the exact Shopify shop we
            # authenticated, not an arbitrary HTTPS destination.
            or url.netloc.lower() != connection.external_store_url.lower()
            or "/invoices/" not in url.path
            or url.username is not None
            or url.password is not None
            or url.fragment
        ):
            order.external_creation_status = "unknown"
            order.external_last_error = "SHOPIFY_CHECKOUT_LINK_UNAVAILABLE"
            db.commit()
            raise ShopifyUserError("SHOPIFY_CHECKOUT_LINK_UNAVAILABLE")

    order_name = (
        draft_order.get("name", "")
    )

    order.shopify_draft_order_id = (
        shopify_gid
    )
    order.invoice_url = invoice_url
    order.total_amount = float(
        total_price_str
    )
    order.order_number = (
        order_name or order.order_number
    )
    order.external_creation_status = (
        "created"
    )
    order.external_last_error = None

    db.commit()

    # Shopify chat checkout has only created a draft, not a purchase.
    # Its order.created automation must come from a verified order webhook.
    if source != "shopify_chat_checkout":
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
                    "total": float(order.total_amount),
                    "currency": order.currency,
                    "external_creation_status": "created",
                    "shopify_draft_order_id": order.shopify_draft_order_id,
                }
            },
            event_id=f"order:{order.id}:created",
        )

    return {
        "ok": True,
        "idempotent": False,
        "order_id": order.id,
        "status": "pending",
        "shopify_draft_order_id": shopify_gid,
        "invoice_url": invoice_url,
        "total_amount": float(
            total_price_str
        ),
        "currency": currency_code,
        "order_number": (
            order_name or order.order_number
        ),
        "external_creation_status": "created",
    }


def list_shopify_orders(
    *,
    db: Session,
    store_id: int,
    organization_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    orders = (
        db.query(Order)
        .filter(
            Order.store_id == store_id,
            Order.organization_id
            == organization_id,
        )
        .order_by(Order.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    results = []

    for order in orders:
        items = [
            {
                "id": item.id,
                "title": item.title,
                "sku": item.sku,
                "quantity": item.quantity,
                "unit_price": float(
                    item.unit_price
                ),
                "currency": item.currency,
                "shopify_variant_id": (
                    item.shopify_variant_id
                ),
            }
            for item in order.items
        ]

        results.append(
            {
                "id": order.id,
                "order_number": (
                    order.order_number
                ),
                "total_amount": float(
                    order.total_amount
                ),
                "currency": order.currency,
                "financial_status": (
                    order.financial_status
                ),
                "fulfillment_status": (
                    order.fulfillment_status
                ),
                "source": order.source,
                "invoice_url": order.invoice_url,
                "shopify_draft_order_id": (
                    order.shopify_draft_order_id
                ),
                "note": order.note,
                "external_creation_status": (
                    order.external_creation_status
                ),
                "created_at": (
                    order.created_at.isoformat()
                    if order.created_at
                    else None
                ),
                "items": items,
            }
        )

    return results


def get_shopify_order(
    *,
    db: Session,
    order_id: int,
    store_id: int,
    organization_id: int,
) -> dict | None:
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.store_id == store_id,
            Order.organization_id
            == organization_id,
        )
        .first()
    )

    if not order:
        return None

    items = [
        {
            "id": item.id,
            "title": item.title,
            "sku": item.sku,
            "quantity": item.quantity,
            "unit_price": float(
                item.unit_price
            ),
            "currency": item.currency,
            "shopify_variant_id": (
                item.shopify_variant_id
            ),
        }
        for item in order.items
    ]

    return {
        "id": order.id,
        "order_number": order.order_number,
        "total_amount": float(
            order.total_amount
        ),
        "currency": order.currency,
        "financial_status": (
            order.financial_status
        ),
        "fulfillment_status": (
            order.fulfillment_status
        ),
        "source": order.source,
        "invoice_url": order.invoice_url,
        "shopify_draft_order_id": (
            order.shopify_draft_order_id
        ),
        "note": order.note,
        "external_creation_status": (
            order.external_creation_status
        ),
        "created_at": (
            order.created_at.isoformat()
            if order.created_at
            else None
        ),
        "items": items,
    }
