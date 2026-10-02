"""Automatic Shopify -> CJ -> Shopify fulfillment orchestration."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..integrations.cj.client import CJError
from ..model_domains.fulfillment_automation import AutoFulfillmentJob
from ..model_domains.shipments import Shipment
from ..model_domains.supplier_integrations import SupplierConnection
from ..model_domains.supplier_orders import SupplierOrder
from ..models import CommerceConnection, Order, OrderItem
from ..shopify_client import ShopifyAPIError
from .shopify_fulfillment import (
    ShopifyFulfillmentError,
    create_shopify_fulfillment_from_shipment,
    missing_fulfillment_scopes,
)
from .supplier_catalog import quote_cj_freight
from .supplier_mappings import resolve_cj_variant_mapping
from .supplier_orders import (
    SupplierOrderError,
    SupplierOrderNotFound,
    create_cj_supplier_order,
)


CJ_PROVIDER = "cj"
_TERMINAL_JOB_STATUSES = {"shopify_fulfilled", "cancelled", "skipped"}
_RETRYABLE_JOB_STATUSES = {"pending", "retry"}


class AutoFulfillmentError(Exception):
    pass


def _cj_connection(
    db: Session,
    organization_id: int,
    store_id: int,
) -> SupplierConnection | None:
    return (
        db.query(SupplierConnection)
        .filter(
            SupplierConnection.organization_id == organization_id,
            SupplierConnection.store_id == store_id,
            SupplierConnection.provider == CJ_PROVIDER,
            SupplierConnection.status == "connected",
        )
        .first()
    )


def _shopify_connection(
    db: Session,
    organization_id: int,
    store_id: int,
) -> CommerceConnection | None:
    return (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == store_id,
            CommerceConnection.provider == "shopify",
            CommerceConnection.status == "connected",
        )
        .first()
    )


def _eligible_order(order: Order) -> bool:
    if order.source != "shopify":
        return False
    if (order.payment_status or "").lower() != "paid":
        return False
    if (order.fulfillment_status or "").lower() == "fulfilled":
        return False
    if (order.lifecycle_status or "").lower() in {
        "cancelled",
        "refunded",
        "voided",
        "fulfilled",
    }:
        return False
    return True


def _serialize_job(job: AutoFulfillmentJob) -> dict:
    return {
        "id": job.id,
        "order_id": job.order_id,
        "supplier_order_id": job.supplier_order_id,
        "shipment_id": job.shipment_id,
        "provider": job.provider,
        "status": job.status,
        "attempts": job.attempts,
        "origin_country_code": job.origin_country_code,
        "logistic_name": job.logistic_name,
        "tracking_number": job.tracking_number,
        "shopify_fulfillment_id": job.shopify_fulfillment_id,
        "last_error": job.last_error,
        "last_attempt_at": (
            job.last_attempt_at.isoformat() + "Z"
            if job.last_attempt_at
            else None
        ),
        "completed_at": (
            job.completed_at.isoformat() + "Z"
            if job.completed_at
            else None
        ),
    }


def configure_cj_auto_fulfillment(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    enabled: bool,
    origin_country_code: str = "CN",
    notify_customer: bool = True,
) -> dict:
    connection = _cj_connection(db, organization_id, store_id)
    if connection is None:
        raise AutoFulfillmentError("CJ_NOT_CONNECTED")

    origin = (origin_country_code or "").strip().upper()
    if len(origin) != 2 or not origin.isalpha():
        raise AutoFulfillmentError("INVALID_ORIGIN_COUNTRY")

    connection.auto_fulfillment_enabled = bool(enabled)
    connection.auto_origin_country_code = origin
    connection.auto_notify_customer = bool(notify_customer)
    connection.updated_at = datetime.utcnow()
    db.commit()

    queued_ids: list[int] = []
    if enabled:
        queued_ids = enqueue_store_paid_orders(
            db,
            organization_id,
            store_id,
        )

    return {
        "ok": True,
        "provider": CJ_PROVIDER,
        "enabled": bool(enabled),
        "origin_country_code": origin,
        "notify_customer": bool(notify_customer),
        "queued_job_ids": queued_ids,
    }


def enqueue_shopify_order(
    db: Session,
    order_id: int,
) -> AutoFulfillmentJob | None:
    order = db.query(Order).filter(Order.id == order_id).first()
    if order is None or not _eligible_order(order):
        return None

    connection = _cj_connection(
        db,
        order.organization_id,
        order.store_id,
    )
    if connection is None or not connection.auto_fulfillment_enabled:
        return None

    job = (
        db.query(AutoFulfillmentJob)
        .filter(
            AutoFulfillmentJob.store_id == order.store_id,
            AutoFulfillmentJob.order_id == order.id,
            AutoFulfillmentJob.provider == CJ_PROVIDER,
        )
        .first()
    )
    now = datetime.utcnow()
    if job is None:
        job = AutoFulfillmentJob(
            organization_id=order.organization_id,
            store_id=order.store_id,
            order_id=order.id,
            provider=CJ_PROVIDER,
            status="pending",
            attempts=0,
            origin_country_code=(
                connection.auto_origin_country_code or "CN"
            ).upper(),
            created_at=now,
            updated_at=now,
        )
        db.add(job)
    elif job.status not in _TERMINAL_JOB_STATUSES and job.supplier_order_id is None:
        job.status = "pending"
        job.origin_country_code = (
            connection.auto_origin_country_code or "CN"
        ).upper()
        job.last_error = None
        job.updated_at = now

    db.commit()
    db.refresh(job)
    return job


def enqueue_store_paid_orders(
    db: Session,
    organization_id: int,
    store_id: int,
) -> list[int]:
    orders = (
        db.query(Order)
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store_id,
            Order.source == "shopify",
            Order.payment_status == "paid",
        )
        .all()
    )
    job_ids = []
    for order in orders:
        if not _eligible_order(order):
            continue
        job = enqueue_shopify_order(db, order.id)
        if job is not None and job.status in _RETRYABLE_JOB_STATUSES:
            job_ids.append(job.id)
    return job_ids


def requeue_store_auto_fulfillment(
    db: Session,
    organization_id: int,
    store_id: int,
) -> list[int]:
    jobs = (
        db.query(AutoFulfillmentJob)
        .filter(
            AutoFulfillmentJob.organization_id == organization_id,
            AutoFulfillmentJob.store_id == store_id,
            AutoFulfillmentJob.provider == CJ_PROVIDER,
            AutoFulfillmentJob.status.in_(
                [
                    "waiting_mapping",
                    "waiting_shopify_reconnect",
                    "retry",
                    "blocked_address",
                    "waiting_logistics",
                ]
            ),
        )
        .all()
    )
    now = datetime.utcnow()
    for job in jobs:
        job.status = "pending"
        job.last_error = None
        job.updated_at = now
    db.commit()
    return [job.id for job in jobs]


def _shipping_for_cj(order: Order) -> dict:
    shipping = dict(order.shipping_address or {})
    required = {
        "country": "SHIPPING_COUNTRY_REQUIRED",
        "country_code": "SHIPPING_COUNTRY_CODE_REQUIRED",
        "province": "SHIPPING_PROVINCE_REQUIRED",
        "city": "SHIPPING_CITY_REQUIRED",
        "customer_name": "SHIPPING_CUSTOMER_NAME_REQUIRED",
        "address1": "SHIPPING_ADDRESS_REQUIRED",
    }
    for field, code in required.items():
        if not str(shipping.get(field) or "").strip():
            raise AutoFulfillmentError(code)
    return shipping


def _price(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _choose_logistics(options: list[dict]) -> dict | None:
    candidates = [
        option
        for option in options
        if str(option.get("logistics_name") or "").strip()
    ]
    if not candidates:
        return None

    priced = [
        (cost, option)
        for option in candidates
        if (cost := _price(option.get("price_usd"))) is not None
    ]
    if priced:
        priced.sort(key=lambda row: (row[0], str(row[1].get("logistics_name"))))
        return priced[0][1]
    return candidates[0]


def _mark_failure(
    db: Session,
    job: AutoFulfillmentJob,
    *,
    status: str,
    error: str,
) -> dict:
    job.status = status
    job.last_error = error[:1000]
    job.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def process_auto_fulfillment_job(
    db: Session,
    job_id: int,
) -> dict:
    job = (
        db.query(AutoFulfillmentJob)
        .filter(AutoFulfillmentJob.id == job_id)
        .first()
    )
    if job is None:
        raise AutoFulfillmentError("AUTO_FULFILLMENT_JOB_NOT_FOUND")
    if job.status in _TERMINAL_JOB_STATUSES:
        return _serialize_job(job)

    order = (
        db.query(Order)
        .filter(
            Order.id == job.order_id,
            Order.organization_id == job.organization_id,
            Order.store_id == job.store_id,
        )
        .first()
    )
    if order is None:
        return _mark_failure(
            db,
            job,
            status="skipped",
            error="ORDER_NOT_FOUND",
        )
    if not _eligible_order(order):
        return _mark_failure(
            db,
            job,
            status="skipped",
            error="ORDER_NOT_ELIGIBLE",
        )

    cj_connection = _cj_connection(
        db,
        job.organization_id,
        job.store_id,
    )
    if cj_connection is None or not cj_connection.auto_fulfillment_enabled:
        return _mark_failure(
            db,
            job,
            status="disabled",
            error="AUTO_FULFILLMENT_DISABLED",
        )

    shopify_connection = _shopify_connection(
        db,
        job.organization_id,
        job.store_id,
    )
    if shopify_connection is None:
        return _mark_failure(
            db,
            job,
            status="waiting_shopify_reconnect",
            error="SHOPIFY_NOT_CONNECTED",
        )
    missing_scopes = missing_fulfillment_scopes(shopify_connection)
    if missing_scopes:
        return _mark_failure(
            db,
            job,
            status="waiting_shopify_reconnect",
            error=(
                "SHOPIFY_FULFILLMENT_SCOPES_REQUIRED:"
                + ",".join(missing_scopes)
            ),
        )

    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    if not items:
        return _mark_failure(
            db,
            job,
            status="waiting_mapping",
            error="ORDER_ITEMS_REQUIRED",
        )

    cj_items = []
    supplier_items = []
    for item in items:
        mapping = resolve_cj_variant_mapping(
            db,
            order.organization_id,
            order.store_id,
            product_variant_id=item.variant_id,
            shopify_variant_id=item.shopify_variant_id,
        )
        if mapping is None:
            return _mark_failure(
                db,
                job,
                status="waiting_mapping",
                error=f"CJ_VARIANT_MAPPING_REQUIRED:{item.id}",
            )
        cj_items.append(
            {
                "variant_id": mapping.external_variant_id,
                "quantity": item.quantity,
            }
        )
        supplier_items.append(
            {
                "order_item_id": item.id,
                "quantity": item.quantity,
            }
        )

    try:
        shipping = _shipping_for_cj(order)
    except AutoFulfillmentError as exc:
        return _mark_failure(
            db,
            job,
            status="blocked_address",
            error=str(exc),
        )

    job.status = "processing"
    job.attempts += 1
    job.last_attempt_at = datetime.utcnow()
    job.last_error = None
    job.updated_at = datetime.utcnow()
    db.commit()

    try:
        freight = quote_cj_freight(
            db,
            order.organization_id,
            order.store_id,
            start_country_code=job.origin_country_code,
            end_country_code=str(shipping["country_code"]),
            zip_code=shipping.get("zip"),
            items=cj_items,
        )
        logistics = _choose_logistics(freight.get("options") or [])
        if logistics is None:
            return _mark_failure(
                db,
                job,
                status="waiting_logistics",
                error="CJ_LOGISTICS_OPTION_NOT_AVAILABLE",
            )

        logistic_name = str(logistics["logistics_name"]).strip()
        supplier_order = create_cj_supplier_order(
            db,
            order.organization_id,
            order.store_id,
            order_id=order.id,
            idempotency_key=f"auto-cj-{order.id}",
            items=supplier_items,
            shipping=shipping,
            from_country_code=job.origin_country_code,
            logistic_name=logistic_name,
            remark=f"Diaglob auto fulfillment Shopify order {order.order_number}",
            is_sandbox=False,
        )
    except (
        CJError,
        SupplierOrderError,
        SupplierOrderNotFound,
    ) as exc:
        return _mark_failure(
            db,
            job,
            status="retry",
            error=str(exc),
        )

    job.supplier_order_id = supplier_order["id"]
    job.logistic_name = logistic_name
    job.status = "supplier_created"
    job.last_error = None
    job.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def process_auto_fulfillment_job_background(job_id: int) -> None:
    db = SessionLocal()
    try:
        process_auto_fulfillment_job(db, job_id)
    except Exception:
        db.rollback()
    finally:
        db.close()


def process_pending_auto_fulfillment_jobs(
    db: Session,
    *,
    limit: int = 10,
) -> int:
    jobs = (
        db.query(AutoFulfillmentJob)
        .filter(AutoFulfillmentJob.status.in_(["pending", "retry"]))
        .order_by(AutoFulfillmentJob.id.asc())
        .limit(limit)
        .all()
    )
    processed = 0
    for job in jobs:
        process_auto_fulfillment_job(db, job.id)
        processed += 1
    return processed


def sync_shopify_from_shipment(
    db: Session,
    shipment_id: int,
) -> dict | None:
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if shipment is None:
        return None

    supplier_order = (
        db.query(SupplierOrder)
        .filter(SupplierOrder.id == shipment.supplier_order_id)
        .first()
    )
    if supplier_order is None:
        return None

    job = (
        db.query(AutoFulfillmentJob)
        .filter(
            AutoFulfillmentJob.supplier_order_id == supplier_order.id,
            AutoFulfillmentJob.provider == CJ_PROVIDER,
        )
        .first()
    )
    if job is None:
        return None
    if job.status == "shopify_fulfilled":
        return _serialize_job(job)

    connection = _cj_connection(
        db,
        job.organization_id,
        job.store_id,
    )
    notify_customer = bool(
        connection.auto_notify_customer
        if connection is not None
        else True
    )

    try:
        result = create_shopify_fulfillment_from_shipment(
            db,
            supplier_order=supplier_order,
            shipment=shipment,
            notify_customer=notify_customer,
        )
    except ShopifyFulfillmentError as exc:
        code = str(exc)
        status = (
            "waiting_shopify_reconnect"
            if code.startswith("SHOPIFY_FULFILLMENT_SCOPES_REQUIRED")
            else "retry"
        )
        return _mark_failure(db, job, status=status, error=code)
    except ShopifyAPIError as exc:
        return _mark_failure(
            db,
            job,
            status="retry",
            error=str(exc),
        )

    job.shipment_id = shipment.id
    job.tracking_number = shipment.tracking_number
    job.shopify_fulfillment_id = result.get("fulfillment_id")
    job.status = "shopify_fulfilled"
    job.last_error = None
    job.completed_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()

    order = db.query(Order).filter(Order.id == job.order_id).first()
    if order is not None:
        order.fulfillment_status = "fulfilled"
        order.lifecycle_status = "fulfilled"
        order.lifecycle_synced_at = datetime.utcnow()

    db.commit()
    db.refresh(job)
    return _serialize_job(job)


def sync_shopify_from_shipment_background(shipment_id: int) -> None:
    db = SessionLocal()
    try:
        sync_shopify_from_shipment(db, shipment_id)
    except Exception:
        db.rollback()
    finally:
        db.close()


__all__ = [
    "AutoFulfillmentError",
    "configure_cj_auto_fulfillment",
    "enqueue_shopify_order",
    "enqueue_store_paid_orders",
    "process_auto_fulfillment_job",
    "process_auto_fulfillment_job_background",
    "process_pending_auto_fulfillment_jobs",
    "requeue_store_auto_fulfillment",
    "sync_shopify_from_shipment",
    "sync_shopify_from_shipment_background",
]
