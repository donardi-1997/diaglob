"""CJ supplier-order lifecycle with local idempotency and reconciliation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..integrations.cj import client as cj_client
from ..integrations.cj.client import CJError, CJTemporaryError
from ..model_domains.supplier_integrations import SupplierConnection
from ..model_domains.supplier_orders import SupplierOrder, SupplierOrderItem
from ..models import Order, OrderItem, Store
from .supplier_connections import get_valid_cj_access_token

CJ_PROVIDER = "cj"
_CANCELLABLE_CJ_STATUSES = {"CREATED", "IN_CART"}


class SupplierOrderError(Exception):
    pass


class SupplierOrderNotFound(SupplierOrderError):
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
    if not store:
        raise SupplierOrderNotFound("STORE_NOT_FOUND")
    return store


def _require_commerce_order(
    db: Session,
    organization_id: int,
    store_id: int,
    order_id: int,
) -> Order:
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
        .first()
    )
    if not order:
        raise SupplierOrderNotFound("ORDER_NOT_FOUND")
    return order


def _get_cj_connection(
    db: Session,
    organization_id: int,
    store_id: int,
) -> SupplierConnection:
    connection = (
        db.query(SupplierConnection)
        .filter(
            SupplierConnection.organization_id == organization_id,
            SupplierConnection.store_id == store_id,
            SupplierConnection.provider == CJ_PROVIDER,
        )
        .first()
    )
    if not connection:
        raise SupplierOrderNotFound("CJ_NOT_CONNECTED")
    return connection


def _money(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _serialize(order: SupplierOrder, *, idempotent: bool = False) -> dict:
    return {
        "id": order.id,
        "provider": order.provider,
        "order_id": order.order_id,
        "provider_order_number": order.provider_order_number,
        "external_order_id": order.external_order_id,
        "shipment_order_id": order.shipment_order_id,
        "supplier_status": order.supplier_status,
        "supplier_substatus": order.supplier_substatus,
        "creation_status": order.creation_status,
        "product_amount": (
            float(order.product_amount)
            if order.product_amount is not None
            else None
        ),
        "postage_amount": (
            float(order.postage_amount)
            if order.postage_amount is not None
            else None
        ),
        "order_amount": (
            float(order.order_amount)
            if order.order_amount is not None
            else None
        ),
        "actual_payment": (
            float(order.actual_payment)
            if order.actual_payment is not None
            else None
        ),
        "currency": order.currency,
        "last_error": order.last_error,
        "last_synced_at": (
            order.last_synced_at.isoformat() + "Z"
            if order.last_synced_at
            else None
        ),
        "idempotent": idempotent,
        "items": [
            {
                "id": item.id,
                "order_item_id": item.order_item_id,
                "external_variant_id": item.external_variant_id,
                "provider_line_item_id": item.provider_line_item_id,
                "quantity": item.quantity,
            }
            for item in order.items
        ],
    }


def _apply_remote(
    supplier_order: SupplierOrder,
    remote: dict[str, Any],
) -> None:
    supplier_order.external_order_id = (
        str(remote.get("orderId") or remote.get("cjOrderId") or "").strip()
        or supplier_order.external_order_id
    )
    supplier_order.shipment_order_id = (
        str(remote.get("shipmentOrderId") or "").strip()
        or supplier_order.shipment_order_id
    )
    supplier_order.supplier_status = (
        str(remote.get("orderStatus") or "").strip()
        or supplier_order.supplier_status
    )
    supplier_order.supplier_substatus = (
        str(remote.get("subStatus") or "").strip() or None
    )
    supplier_order.product_amount = _money(remote.get("productAmount"))
    supplier_order.postage_amount = _money(remote.get("postageAmount"))
    supplier_order.order_amount = _money(remote.get("orderAmount"))
    supplier_order.actual_payment = _money(remote.get("actualPayment"))
    supplier_order.creation_status = "created"
    supplier_order.last_error = None
    supplier_order.last_synced_at = datetime.utcnow()
    supplier_order.updated_at = datetime.utcnow()

    by_store_line_id = {
        str(item.order_item_id): item
        for item in supplier_order.items
        if item.order_item_id is not None
    }
    for remote_item in remote.get("productInfoList") or []:
        if not isinstance(remote_item, dict):
            continue
        local_item = by_store_line_id.get(
            str(remote_item.get("storeLineItemId") or "")
        )
        if local_item is not None:
            local_item.provider_line_item_id = (
                str(remote_item.get("lineItemId") or "").strip() or None
            )


def _validate_items(
    db: Session,
    order: Order,
    items: list[dict],
) -> list[tuple[OrderItem, str, int]]:
    if not items:
        raise SupplierOrderError("SUPPLIER_ORDER_ITEMS_REQUIRED")

    order_items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .all()
    )
    item_map = {item.id: item for item in order_items}
    normalized: list[tuple[OrderItem, str, int]] = []
    seen: set[int] = set()

    for payload in items:
        order_item_id = int(payload.get("order_item_id") or 0)
        if order_item_id in seen:
            raise SupplierOrderError("DUPLICATE_ORDER_ITEM")
        seen.add(order_item_id)

        order_item = item_map.get(order_item_id)
        if order_item is None:
            raise SupplierOrderError("ORDER_ITEM_NOT_FOUND")

        variant_id = str(payload.get("external_variant_id") or "").strip()
        if not variant_id:
            raise SupplierOrderError("CJ_VARIANT_ID_REQUIRED")

        quantity = int(payload.get("quantity") or 0)
        if quantity <= 0 or quantity > order_item.quantity:
            raise SupplierOrderError("INVALID_SUPPLIER_QUANTITY")

        normalized.append((order_item, variant_id, quantity))

    return normalized


def _assert_idempotency_matches(
    supplier_order: SupplierOrder,
    commerce_order: Order,
    normalized_items: list[tuple[OrderItem, str, int]],
) -> None:
    if supplier_order.order_id != commerce_order.id:
        raise SupplierOrderError("IDEMPOTENCY_PAYLOAD_MISMATCH")

    persisted = sorted(
        (
            item.order_item_id,
            item.external_variant_id,
            item.quantity,
        )
        for item in supplier_order.items
    )
    incoming = sorted(
        (
            order_item.id,
            external_variant_id,
            quantity,
        )
        for order_item, external_variant_id, quantity in normalized_items
    )
    if persisted and persisted != incoming:
        raise SupplierOrderError("IDEMPOTENCY_PAYLOAD_MISMATCH")


def _reconcile_existing(
    db: Session,
    supplier_order: SupplierOrder,
    access_token: str,
) -> bool:
    try:
        remote = cj_client.get_order(
            access_token,
            supplier_order.provider_order_number,
        )
    except CJError as exc:
        if exc.code == 1600300:
            return False
        raise

    if not remote:
        return False

    _apply_remote(supplier_order, remote)
    db.commit()
    db.refresh(supplier_order)
    return True


def create_cj_supplier_order(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    order_id: int,
    idempotency_key: str,
    items: list[dict],
    shipping: dict,
    from_country_code: str,
    logistic_name: str,
    remark: str | None = None,
    is_sandbox: bool = False,
) -> dict:
    store = _require_store(db, organization_id, store_id)
    if not store.active:
        raise SupplierOrderError("STORE_NOT_ACTIVE")

    commerce_order = _require_commerce_order(
        db,
        organization_id,
        store_id,
        order_id,
    )
    idempotency_key = (idempotency_key or "").strip()
    if not idempotency_key:
        raise SupplierOrderError("IDEMPOTENCY_KEY_REQUIRED")
    if len(idempotency_key) > 100:
        raise SupplierOrderError("IDEMPOTENCY_KEY_TOO_LONG")

    normalized_items = _validate_items(db, commerce_order, items)

    existing = (
        db.query(SupplierOrder)
        .filter(
            SupplierOrder.store_id == store_id,
            SupplierOrder.provider == CJ_PROVIDER,
            SupplierOrder.idempotency_key == idempotency_key,
        )
        .first()
    )

    if existing:
        _assert_idempotency_matches(
            existing,
            commerce_order,
            normalized_items,
        )
        if existing.creation_status == "created":
            return _serialize(existing, idempotent=True)

    logistic_name = (logistic_name or "").strip()
    if not logistic_name:
        raise SupplierOrderError("LOGISTIC_NAME_REQUIRED")

    origin = (from_country_code or "").strip().upper()
    destination = str(shipping.get("country_code") or "").strip().upper()
    if len(origin) != 2 or not origin.isalpha():
        raise SupplierOrderError("INVALID_ORIGIN_COUNTRY")
    if len(destination) != 2 or not destination.isalpha():
        raise SupplierOrderError("INVALID_DESTINATION_COUNTRY")

    required_shipping = {
        "country": "SHIPPING_COUNTRY_REQUIRED",
        "province": "SHIPPING_PROVINCE_REQUIRED",
        "city": "SHIPPING_CITY_REQUIRED",
        "customer_name": "SHIPPING_CUSTOMER_NAME_REQUIRED",
        "address1": "SHIPPING_ADDRESS_REQUIRED",
    }
    for field, error_code in required_shipping.items():
        if not str(shipping.get(field) or "").strip():
            raise SupplierOrderError(error_code)

    connection = _get_cj_connection(db, organization_id, store_id)
    access_token = get_valid_cj_access_token(
        db,
        organization_id,
        store_id,
    )

    if existing and existing.creation_status in {"pending", "unknown"}:
        if _reconcile_existing(db, existing, access_token):
            return _serialize(existing, idempotent=True)

    if existing:
        supplier_order = existing
        supplier_order.creation_status = "pending"
        supplier_order.last_error = None
        supplier_order.updated_at = datetime.utcnow()
    else:
        now = datetime.utcnow()
        supplier_order = SupplierOrder(
            organization_id=organization_id,
            store_id=store_id,
            order_id=commerce_order.id,
            supplier_connection_id=connection.id,
            provider=CJ_PROVIDER,
            provider_order_number="PENDING",
            idempotency_key=idempotency_key,
            creation_status="pending",
            currency="USD",
            created_at=now,
            updated_at=now,
        )
        db.add(supplier_order)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            duplicate = (
                db.query(SupplierOrder)
                .filter(
                    SupplierOrder.store_id == store_id,
                    SupplierOrder.provider == CJ_PROVIDER,
                    SupplierOrder.idempotency_key == idempotency_key,
                )
                .first()
            )
            if duplicate:
                return _serialize(duplicate, idempotent=True)
            raise

        supplier_order.provider_order_number = (
            f"DG-{store_id}-{supplier_order.id}"
        )

        for order_item, external_variant_id, quantity in normalized_items:
            db.add(
                SupplierOrderItem(
                    supplier_order_id=supplier_order.id,
                    order_item_id=order_item.id,
                    external_variant_id=external_variant_id,
                    quantity=quantity,
                    created_at=now,
                )
            )

    db.commit()
    db.refresh(supplier_order)

    payload: dict[str, Any] = {
        "orderNumber": supplier_order.provider_order_number,
        "shippingCountryCode": destination,
        "shippingCountry": str(shipping.get("country") or "").strip(),
        "shippingProvince": str(shipping.get("province") or "").strip(),
        "shippingCity": str(shipping.get("city") or "").strip(),
        "shippingCustomerName": str(shipping.get("customer_name") or "").strip(),
        "shippingAddress": str(shipping.get("address1") or "").strip(),
        "logisticName": logistic_name,
        "fromCountryCode": origin,
        "platform": "Api",
        "shopLogisticsType": 2,
        "orderFlow": 1,
        "payType": 3,
        "isSandbox": 1 if is_sandbox else 0,
        "products": [
            {
                "vid": external_variant_id,
                "quantity": quantity,
                "storeLineItemId": str(order_item.id),
            }
            for order_item, external_variant_id, quantity in normalized_items
        ],
    }

    optional_map = {
        "shippingZip": shipping.get("zip"),
        "shippingCounty": shipping.get("county"),
        "shippingPhone": shipping.get("phone"),
        "shippingAddress2": shipping.get("address2"),
        "houseNumber": shipping.get("house_number"),
        "email": shipping.get("email"),
        "taxId": shipping.get("tax_id"),
        "remark": remark,
    }
    for field, value in optional_map.items():
        if value not in (None, ""):
            payload[field] = str(value).strip()

    try:
        remote = cj_client.create_order_v3(access_token, payload)
    except CJTemporaryError as exc:
        supplier_order.creation_status = "unknown"
        supplier_order.last_error = str(exc)[:500]
        supplier_order.updated_at = datetime.utcnow()
        db.commit()
        raise
    except CJError as exc:
        supplier_order.creation_status = "failed"
        supplier_order.last_error = str(exc)[:500]
        supplier_order.updated_at = datetime.utcnow()
        db.commit()
        raise

    _apply_remote(supplier_order, remote)
    db.commit()
    db.refresh(supplier_order)
    return _serialize(supplier_order)


def sync_cj_supplier_order(
    db: Session,
    organization_id: int,
    store_id: int,
    supplier_order_id: int,
) -> dict:
    _require_store(db, organization_id, store_id)
    supplier_order = (
        db.query(SupplierOrder)
        .filter(
            SupplierOrder.id == supplier_order_id,
            SupplierOrder.organization_id == organization_id,
            SupplierOrder.store_id == store_id,
            SupplierOrder.provider == CJ_PROVIDER,
        )
        .first()
    )
    if not supplier_order:
        raise SupplierOrderNotFound("SUPPLIER_ORDER_NOT_FOUND")

    access_token = get_valid_cj_access_token(
        db,
        organization_id,
        store_id,
    )
    remote = cj_client.get_order(
        access_token,
        supplier_order.external_order_id
        or supplier_order.provider_order_number,
        features=["LOGISTICS_TIMELINESS"],
    )
    _apply_remote(supplier_order, remote)
    db.commit()
    db.refresh(supplier_order)
    return _serialize(supplier_order)


def cancel_cj_supplier_order(
    db: Session,
    organization_id: int,
    store_id: int,
    supplier_order_id: int,
) -> dict:
    current = sync_cj_supplier_order(
        db,
        organization_id,
        store_id,
        supplier_order_id,
    )
    status = (current.get("supplier_status") or "").upper()
    if status not in _CANCELLABLE_CJ_STATUSES:
        raise SupplierOrderError("CJ_ORDER_NOT_CANCELLABLE")

    supplier_order = (
        db.query(SupplierOrder)
        .filter(SupplierOrder.id == supplier_order_id)
        .first()
    )
    if supplier_order is None:
        raise SupplierOrderNotFound("SUPPLIER_ORDER_NOT_FOUND")

    access_token = get_valid_cj_access_token(
        db,
        organization_id,
        store_id,
    )
    provider_order_id = (
        supplier_order.external_order_id
        or supplier_order.provider_order_number
    )
    deleted = cj_client.delete_order(access_token, provider_order_id)
    if not deleted:
        raise SupplierOrderError("CJ_ORDER_DELETE_REJECTED")

    supplier_order.supplier_status = "CANCELLED"
    supplier_order.last_synced_at = datetime.utcnow()
    supplier_order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(supplier_order)
    return _serialize(supplier_order)
