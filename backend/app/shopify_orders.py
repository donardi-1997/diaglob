import uuid
import re

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
            fulfillment_status=None,
            source="shopify",
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
        token = decrypt_shopify_secret(
            connection.access_token_encrypted
        )

        client = ShopifyGraphQLClient(
            shop_domain=(
                connection.external_store_url
            ),
            access_token=token,
        )

        shopify_input: dict = {
            "lineItems": shopify_line_items,
        }

        if note:
            shopify_input["note"] = note

        if customer_email:
            shopify_input["email"] = (
                customer_email
            )

        if customer_name:
            shopify_input["name"] = (
                customer_name
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

    # Emit order.created event for automations
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
