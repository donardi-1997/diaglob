"""Payment service — business logic for payment operations.

This module handles payment provider connections, transaction
lifecycle, and webhook processing. It does NOT import FastAPI.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Order, PaymentConnection, PaymentTransaction, Store
from ..payment_security import decrypt_payment_secret, encrypt_payment_secret
from ..payments.base import PaymentStatus, is_valid_transition
from ..payments.registry import get_provider

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    def __init__(self, code: str, message: str | None = None):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class PaymentConnectionNotFoundError(PaymentError):
    def __init__(self):
        super().__init__("PAYMENT_PROVIDER_NOT_CONNECTED", "Payment provider is not connected")


class PaymentNotFoundError(PaymentError):
    def __init__(self):
        super().__init__("PAYMENT_NOT_FOUND", "Payment not found")


class PaymentInvalidAmountError(PaymentError):
    def __init__(self, detail: str = ""):
        super().__init__("PAYMENT_INVALID_AMOUNT", detail or "Invalid payment amount")


class PaymentAlreadyPaidError(PaymentError):
    def __init__(self):
        super().__init__("PAYMENT_ALREADY_PAID", "Payment is already paid")


class PaymentExpiredError(PaymentError):
    def __init__(self):
        super().__init__("PAYMENT_EXPIRED", "Payment has expired")


class PaymentRejectedError(PaymentError):
    def __init__(self):
        super().__init__("PAYMENT_REJECTED", "Payment was rejected")


class PaymentProviderError(PaymentError):
    def __init__(self, detail: str = ""):
        super().__init__("PAYMENT_PROVIDER_ERROR", detail or "Payment provider error")


class PaymentCurrencyError(PaymentError):
    def __init__(self, currency: str):
        super().__init__("PAYMENT_INVALID_AMOUNT", f"Unsupported currency: {currency}")


def payment_provider_available(provider_code: str, country_code: str, currency: str) -> bool:
    provider = get_provider(provider_code)
    return bool(provider and provider.is_available(country_code, currency))


def get_available_providers(country_code: str, currency: str) -> list[dict[str, Any]]:
    from ..payments.registry import get_providers_for_market

    providers = get_providers_for_market(country_code, currency)
    return [
        {
            "code": p.provider_code,
            "name": p.display_name,
            "payment_methods": p.supported_payment_methods,
            "supports_webhooks": p.supports_webhooks,
            "supports_reversals": p.supports_reversals,
        }
        for p in providers
    ]


def get_connection(
    db: Session,
    organization_id: int,
    store_id: int,
    provider_code: str,
) -> PaymentConnection | None:
    return (
        db.execute(
            select(PaymentConnection).where(
                PaymentConnection.organization_id == organization_id,
                PaymentConnection.store_id == store_id,
                PaymentConnection.provider == provider_code,
            )
        )
        .scalars()
        .first()
    )


def get_connection_status(
    db: Session,
    organization_id: int,
    store_id: int,
    provider_code: str,
) -> dict[str, Any]:
    conn = get_connection(db, organization_id, store_id, provider_code)
    if not conn:
        return {
            "connected": False,
            "provider": provider_code,
            "status": "disconnected",
            "environment": None,
            "merchant_reference": None,
            "connected_at": None,
            "last_error": None,
        }
    return {
        "connected": conn.status == "connected",
        "provider": conn.provider,
        "status": conn.status,
        "environment": conn.environment,
        "merchant_reference": conn.merchant_reference,
        "connected_at": conn.connected_at.isoformat() if conn.connected_at else None,
        "last_error": conn.last_error,
    }


def configure_connection(
    db: Session,
    organization_id: int,
    store_id: int,
    provider_code: str,
    environment: str,
    client_id: str | None,
    client_secret: str | None,
    webhook_secret: str | None = None,
    merchant_reference: str | None = None,
    access_token: str | None = None,
) -> PaymentConnection:
    store = db.get(Store, store_id)
    if not store or store.organization_id != organization_id:
        raise PaymentError("PAYMENT_STORE_NOT_FOUND", "Store not found")

    provider = get_provider(provider_code)
    if not provider:
        raise PaymentError("PAYMENT_PROVIDER_NOT_FOUND", f"Unknown provider: {provider_code}")
    if not provider.is_available(store.country_code, store.currency):
        raise PaymentError(
            "PAYMENT_PROVIDER_UNAVAILABLE",
            f"{provider.display_name} is not available for {store.country_code}/{store.currency}",
        )

    secret = access_token or client_secret
    if provider_code == "mercado_pago":
        if not secret:
            raise PaymentError(
                "PAYMENT_CREDENTIALS_REQUIRED",
                "Mercado Pago access token is required",
            )
        client_id = client_id or "mercado_pago"
    elif not client_id or not client_secret:
        raise PaymentError(
            "PAYMENT_CREDENTIALS_REQUIRED",
            "client_id and client_secret are required",
        )

    conn = get_connection(db, organization_id, store_id, provider_code)
    if not conn:
        conn = PaymentConnection(
            organization_id=organization_id,
            store_id=store_id,
            provider=provider_code,
        )
        db.add(conn)

    conn.environment = environment
    conn.client_id_encrypted = encrypt_payment_secret(client_id or provider_code)
    conn.client_secret_encrypted = encrypt_payment_secret(secret or "")
    if webhook_secret:
        conn.webhook_secret_encrypted = encrypt_payment_secret(webhook_secret)
    conn.merchant_reference = merchant_reference
    conn.status = "connected"
    conn.connected_at = datetime.now(timezone.utc)
    conn.last_error = None
    db.flush()
    return conn


def disconnect(db: Session, organization_id: int, store_id: int, provider_code: str) -> None:
    conn = get_connection(db, organization_id, store_id, provider_code)
    if not conn:
        raise PaymentConnectionNotFoundError()
    conn.status = "disconnected"
    conn.last_error = None
    db.flush()


def get_connection_credentials(
    db: Session,
    organization_id: int,
    store_id: int,
    provider_code: str,
) -> dict[str, str]:
    conn = get_connection(db, organization_id, store_id, provider_code)
    if not conn or conn.status != "connected":
        raise PaymentConnectionNotFoundError()
    creds: dict[str, str] = {}
    if conn.client_id_encrypted:
        creds["client_id"] = decrypt_payment_secret(conn.client_id_encrypted)
    if conn.client_secret_encrypted:
        creds["client_secret"] = decrypt_payment_secret(conn.client_secret_encrypted)
    if conn.webhook_secret_encrypted:
        creds["webhook_secret"] = decrypt_payment_secret(conn.webhook_secret_encrypted)
    return creds


def create_payment(
    db: Session,
    organization_id: int,
    store_id: int,
    provider_code: str,
    amount: Decimal | float | str,
    currency: str,
    customer_phone: str,
    idempotency_key: str,
    order_id: int | None = None,
    payment_method: str = "nequi_push",
    description: str = "Payment",
) -> PaymentTransaction:
    store = db.get(Store, store_id)
    if not store or store.organization_id != organization_id:
        raise PaymentError("PAYMENT_STORE_NOT_FOUND", "Store not found")

    if order_id:
        order = db.get(Order, order_id)
        if not order or order.organization_id != organization_id or order.store_id != store_id:
            raise PaymentError("PAYMENT_ORDER_NOT_FOUND", "Order not found or access denied")

    if currency != store.currency:
        raise PaymentCurrencyError(currency)

    try:
        amount_decimal = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        raise PaymentInvalidAmountError("Amount must be a valid number")
    if amount_decimal <= 0:
        raise PaymentInvalidAmountError("Amount must be greater than zero")

    provider = get_provider(provider_code)
    if not provider:
        raise PaymentError("PAYMENT_PROVIDER_NOT_FOUND", f"Unknown provider: {provider_code}")
    if not provider.is_available(store.country_code, store.currency):
        raise PaymentError(
            "PAYMENT_PROVIDER_UNAVAILABLE",
            f"{provider.display_name} is not available for this store",
        )
    if payment_method not in provider.supported_payment_methods:
        raise PaymentError(
            "PAYMENT_METHOD_UNAVAILABLE",
            f"{payment_method} is not supported by {provider.display_name}",
        )

    conn = get_connection(db, organization_id, store_id, provider_code)
    if not conn or conn.status != "connected":
        raise PaymentConnectionNotFoundError()

    existing = (
        db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.organization_id == organization_id,
                PaymentTransaction.idempotency_key == idempotency_key,
            )
        )
        .scalars()
        .first()
    )
    if existing:
        logger.info("payment_idempotent_hit payment_id=%s status=%s", existing.id, existing.status)
        return existing

    txn = PaymentTransaction(
        organization_id=organization_id,
        store_id=store_id,
        order_id=order_id,
        provider=provider_code,
        idempotency_key=idempotency_key,
        amount=amount_decimal,
        currency=currency,
        status=PaymentStatus.PENDING.value,
        payment_method=payment_method,
        customer_phone=customer_phone,
        merchant_reference=conn.merchant_reference,
    )
    db.add(txn)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = (
            db.execute(
                select(PaymentTransaction).where(
                    PaymentTransaction.organization_id == organization_id,
                    PaymentTransaction.idempotency_key == idempotency_key,
                )
            )
            .scalars()
            .first()
        )
        if existing:
            return existing
        raise PaymentError("PAYMENT_CREATION_FAILED", "Could not create payment")

    logger.info(
        "payment_created payment_id=%s provider=%s amount=%s currency=%s",
        txn.id,
        provider_code,
        amount_decimal,
        currency,
    )
    return txn


async def execute_payment(
    db: Session,
    organization_id: int,
    store_id: int,
    payment_id: int,
    metadata: dict[str, Any] | None = None,
) -> PaymentTransaction:
    txn = _get_owned_transaction(db, organization_id, store_id, payment_id)
    if txn.status != PaymentStatus.PENDING.value:
        if txn.status == PaymentStatus.PAID.value:
            raise PaymentAlreadyPaidError()
        raise PaymentError("PAYMENT_INVALID_STATUS", f"Payment is {txn.status}, cannot execute")

    creds = get_connection_credentials(db, organization_id, store_id, txn.provider)
    provider = get_provider(txn.provider)
    if not provider:
        raise PaymentProviderError("Provider not found")
    conn = get_connection(db, organization_id, store_id, txn.provider)
    environment = conn.environment if conn else "sandbox"

    try:
        result = await provider.create_payment(
            credentials=creds,
            environment=environment,
            amount=Decimal(str(txn.amount)),
            currency=txn.currency,
            customer_phone=txn.customer_phone or "",
            description=f"Order #{txn.order_id}" if txn.order_id else "Payment",
            idempotency_key=txn.idempotency_key,
            metadata=metadata,
        )
    except Exception as exc:
        logger.exception("payment_provider_error payment_id=%s", txn.id)
        _update_transaction_status(
            txn,
            PaymentStatus.FAILED.value,
            provider_status="PROVIDER_ERROR",
            provider_error_code="PROVIDER_ERROR",
            provider_error_message=str(exc)[:500],
        )
        db.flush()
        raise PaymentProviderError(str(exc)[:200])

    txn.provider_transaction_id = result.provider_transaction_id
    _update_transaction_status(txn, result.status.value, provider_status=result.provider_status)
    if result.action_data:
        setattr(txn, "_action_data", result.action_data)
    if result.expires_at:
        try:
            txn.expires_at = datetime.fromisoformat(result.expires_at)
        except ValueError:
            pass
    db.flush()
    logger.info(
        "payment_executed payment_id=%s provider_txn_id=%s status=%s",
        txn.id,
        result.provider_transaction_id,
        result.status.value,
    )
    return txn


async def reconcile_payment_status(
    db: Session,
    organization_id: int,
    store_id: int,
    payment_id: int,
) -> PaymentTransaction:
    txn = _get_owned_transaction(db, organization_id, store_id, payment_id)
    if not txn.provider_transaction_id:
        raise PaymentError("PAYMENT_NOT_EXECUTED", "Payment has not been sent to provider")
    creds = get_connection_credentials(db, organization_id, store_id, txn.provider)
    provider = get_provider(txn.provider)
    if not provider:
        raise PaymentProviderError("Provider not found")
    conn = get_connection(db, organization_id, store_id, txn.provider)
    environment = conn.environment if conn else "sandbox"
    try:
        result = await provider.get_payment_status(
            credentials=creds,
            environment=environment,
            provider_transaction_id=txn.provider_transaction_id,
        )
    except Exception as exc:
        logger.exception("payment_status_query_failed payment_id=%s", txn.id)
        raise PaymentProviderError(str(exc)[:200])
    _update_transaction_status(
        txn,
        result.status.value,
        provider_status=result.provider_status,
        provider_error_code=result.provider_error_code,
        provider_error_message=result.provider_error_message,
        paid_at=result.paid_at,
    )
    db.flush()
    return txn


def process_webhook(
    db: Session,
    provider_code: str,
    headers: dict[str, str],
    body: bytes,
) -> dict[str, Any]:
    provider = get_provider(provider_code)
    if not provider:
        raise PaymentError("PAYMENT_PROVIDER_NOT_FOUND", f"Unknown provider: {provider_code}")
    try:
        parsed = provider.parse_webhook(headers, body)
    except Exception as exc:
        raise PaymentError("PAYMENT_WEBHOOK_INVALID", f"Invalid webhook payload: {exc}")
    provider_txn_id = parsed.get("provider_transaction_id")
    if not provider_txn_id:
        raise PaymentError("PAYMENT_WEBHOOK_INVALID", "Missing transaction ID")
    txn = (
        db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.provider == provider_code,
                PaymentTransaction.provider_transaction_id == provider_txn_id,
            )
        )
        .scalars()
        .first()
    )
    if not txn:
        logger.warning("webhook_unknown_transaction provider=%s txn_id=%s", provider_code, provider_txn_id)
        return {"status": "ignored", "reason": "unknown_transaction"}

    conn = get_connection(db, txn.organization_id, txn.store_id, provider_code)
    if conn and conn.webhook_secret_encrypted:
        webhook_secret = decrypt_payment_secret(conn.webhook_secret_encrypted)
        if not provider.verify_webhook(headers, body, webhook_secret):
            raise PaymentError("PAYMENT_WEBHOOK_INVALID", "Invalid webhook signature")

    event_id = parsed.get("raw", {}).get("eventId", "")
    if event_id and conn and conn.last_event_id == event_id:
        return {"status": "duplicate", "payment_id": txn.id}

    nequi_status = parsed.get("status", "")
    from ..payments.nequi import NEQUI_STATUS_MAP
    normalized = NEQUI_STATUS_MAP.get(nequi_status, PaymentStatus.PENDING)
    _update_transaction_status(
        txn,
        normalized.value,
        provider_status=nequi_status,
        paid_at=parsed.get("timestamp"),
    )
    if conn and event_id:
        conn.last_event_id = event_id
        conn.last_event_at = datetime.now(timezone.utc)
    db.flush()
    logger.info(
        "webhook_processed payment_id=%s status=%s -> %s",
        txn.id,
        nequi_status,
        normalized.value,
    )
    return {"status": "processed", "payment_id": txn.id, "new_status": normalized.value}


async def cancel_payment(
    db: Session,
    organization_id: int,
    store_id: int,
    payment_id: int,
) -> PaymentTransaction:
    txn = _get_owned_transaction(db, organization_id, store_id, payment_id)
    if txn.status not in (PaymentStatus.PENDING.value, PaymentStatus.REQUIRES_ACTION.value):
        raise PaymentError("PAYMENT_INVALID_STATUS", f"Cannot cancel payment in {txn.status} state")
    if not txn.provider_transaction_id:
        _update_transaction_status(txn, PaymentStatus.CANCELLED.value)
        db.flush()
        return txn
    creds = get_connection_credentials(db, organization_id, store_id, txn.provider)
    provider = get_provider(txn.provider)
    if not provider:
        raise PaymentProviderError("Provider not found")
    conn = get_connection(db, organization_id, store_id, txn.provider)
    environment = conn.environment if conn else "sandbox"
    try:
        result = await provider.cancel_payment(
            credentials=creds,
            environment=environment,
            provider_transaction_id=txn.provider_transaction_id,
        )
    except Exception as exc:
        logger.exception("payment_cancel_failed payment_id=%s", txn.id)
        raise PaymentProviderError(str(exc)[:200])
    _update_transaction_status(txn, result.status.value, provider_status=result.provider_status)
    db.flush()
    return txn


async def reverse_payment(
    db: Session,
    organization_id: int,
    store_id: int,
    payment_id: int,
    reason: str = "Merchant requested reversal",
) -> PaymentTransaction:
    txn = _get_owned_transaction(db, organization_id, store_id, payment_id)
    if txn.status != PaymentStatus.PAID.value:
        raise PaymentError("PAYMENT_INVALID_STATUS", "Only paid payments can be reversed")
    if not txn.provider_transaction_id:
        raise PaymentError("PAYMENT_NOT_EXECUTED", "Payment has no provider reference")
    creds = get_connection_credentials(db, organization_id, store_id, txn.provider)
    provider = get_provider(txn.provider)
    if not provider:
        raise PaymentProviderError("Provider not found")
    if not provider.supports_reversals:
        raise PaymentError(
            "PAYMENT_REVERSAL_NOT_SUPPORTED",
            f"{provider.display_name} does not support reversals",
        )
    conn = get_connection(db, organization_id, store_id, txn.provider)
    environment = conn.environment if conn else "sandbox"
    try:
        result = await provider.reverse_payment(
            credentials=creds,
            environment=environment,
            provider_transaction_id=txn.provider_transaction_id,
            amount=Decimal(str(txn.amount)),
            reason=reason,
        )
    except Exception as exc:
        logger.exception("payment_reversal_failed payment_id=%s", txn.id)
        raise PaymentProviderError(str(exc)[:200])
    _update_transaction_status(
        txn,
        result.status.value,
        provider_status=result.provider_status,
        provider_error_code=result.provider_error_code,
        provider_error_message=result.provider_error_message,
    )
    if result.status == PaymentStatus.REVERSED:
        txn.reversed_at = datetime.now(timezone.utc)
    db.flush()
    return txn


def _get_owned_transaction(
    db: Session,
    organization_id: int,
    store_id: int,
    payment_id: int,
) -> PaymentTransaction:
    txn = (
        db.execute(
            select(PaymentTransaction).where(
                PaymentTransaction.id == payment_id,
                PaymentTransaction.organization_id == organization_id,
                PaymentTransaction.store_id == store_id,
            )
        )
        .scalars()
        .first()
    )
    if not txn:
        raise PaymentNotFoundError()
    return txn


def _update_transaction_status(
    txn: PaymentTransaction,
    new_status: str,
    provider_status: str | None = None,
    provider_error_code: str | None = None,
    provider_error_message: str | None = None,
    paid_at: str | None = None,
) -> None:
    current = txn.status
    if current == new_status:
        return
    if not is_valid_transition(current, new_status):
        logger.warning(
            "payment_invalid_transition payment_id=%s %s -> %s",
            txn.id,
            current,
            new_status,
        )
        if current == "pending" and new_status in ("paid", "rejected", "expired", "failed"):
            pass
        else:
            raise PaymentError(
                "PAYMENT_INVALID_STATUS",
                f"Cannot transition from {current} to {new_status}",
            )
    txn.status = new_status
    if provider_status is not None:
        txn.provider_status = provider_status
    if provider_error_code is not None:
        txn.provider_error_code = provider_error_code
    if provider_error_message is not None:
        txn.provider_error_message = provider_error_message
    if new_status == PaymentStatus.PAID.value:
        if paid_at:
            try:
                txn.paid_at = datetime.fromisoformat(paid_at)
            except ValueError:
                txn.paid_at = datetime.now(timezone.utc)
        else:
            txn.paid_at = datetime.now(timezone.utc)
    txn.updated_at = datetime.now(timezone.utc)
    logger.info("payment_status_changed payment_id=%s %s -> %s", txn.id, current, new_status)
