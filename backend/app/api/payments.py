"""Payment API routes.

Thin HTTP layer that delegates to payment_service.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..api.deps import (
    get_current_membership,
    require_permission,
)
from ..models import OrganizationMembership
from ..services import payment_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================


class ConfigureConnectionRequest(BaseModel):
    provider: str
    environment: str = "sandbox"
    client_id: str | None = None
    client_secret: str | None = None
    access_token: str | None = None
    webhook_secret: str | None = None
    merchant_reference: str | None = None


class CreatePaymentRequest(BaseModel):
    provider: str = "nequi"
    amount: Decimal | None = None
    currency: str | None = None
    customer_phone: str
    customer_email: str | None = None
    customer_document: str | None = None
    customer_document_type: str | None = None
    idempotency_key: str | None = None
    order_id: int | None = None
    payment_method: str = "nequi_push"


class ReversePaymentRequest(BaseModel):
    reason: str = "Merchant requested reversal"


def _get_store(
    store_id: int,
    membership: OrganizationMembership,
    db: Session,
):
    """Validate store ownership."""
    from ..models import Store

    store = db.get(Store, store_id)
    if (
        not store
        or store.organization_id
        != membership.organization_id
    ):
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )
    return store


# ============================================================
# PROVIDER AVAILABILITY
# ============================================================


@router.get(
    "/api/stores/{store_id}/payments/providers",
)
def list_payment_providers(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    """List available payment providers for a store."""
    store = _get_store(store_id, membership, db)

    providers = payment_service.get_available_providers(
        store.country_code, store.currency
    )

    return {
        "store_id": store_id,
        "providers": providers,
    }


# ============================================================
# CONNECTION MANAGEMENT
# ============================================================


@router.get(
    "/api/stores/{store_id}/payments/{provider}/status",
)
def get_connection_status(
    store_id: int,
    provider: str,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    """Get payment provider connection status."""
    _get_store(store_id, membership, db)

    return payment_service.get_connection_status(
        db,
        membership.organization_id,
        store_id,
        provider,
    )


@router.post(
    "/api/stores/{store_id}/payments/{provider}/connect",
)
def configure_payment_connection(
    store_id: int,
    provider: str,
    body: ConfigureConnectionRequest,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    """Configure a payment provider connection."""
    try:
        conn = payment_service.configure_connection(
            db,
            membership.organization_id,
            store_id,
            provider,
            body.environment,
            body.client_id,
            body.client_secret,
            body.webhook_secret,
            body.merchant_reference,
            body.access_token,
        )
        db.commit()
    except payment_service.PaymentError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        )

    return {
        "ok": True,
        "connected": True,
        "provider": conn.provider,
        "status": conn.status,
        "environment": conn.environment,
    }


@router.delete(
    "/api/stores/{store_id}/payments/{provider}/disconnect",
)
def disconnect_payment(
    store_id: int,
    provider: str,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    """Disconnect a payment provider."""
    try:
        payment_service.disconnect(
            db,
            membership.organization_id,
            store_id,
            provider,
        )
        db.commit()
    except payment_service.PaymentError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        )

    return {
        "ok": True,
        "connected": False,
        "provider": provider,
    }


# ============================================================
# PAYMENT CREATION
# ============================================================


@router.post(
    "/api/stores/{store_id}/payments",
    status_code=201,
)
async def create_payment(
    store_id: int,
    body: CreatePaymentRequest,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    """Create a new payment."""
    import uuid as _uuid

    idempotency_key = (
        body.idempotency_key
        or str(_uuid.uuid4())
    )

    try:
        txn = payment_service.create_payment(
            db,
            membership.organization_id,
            store_id,
            body.provider,
            body.amount or Decimal("0"),
            body.currency or "",
            body.customer_phone,
            idempotency_key,
            body.order_id,
            body.payment_method,
        )

        # Execute the payment with the provider
        txn = await payment_service.execute_payment(
            db,
            membership.organization_id,
            store_id,
            txn.id,
            metadata={
                "customer_email": body.customer_email,
                "customer_document": body.customer_document,
                "customer_document_type": (
                    body.customer_document_type
                ),
            },
        )

        db.commit()
    except payment_service.PaymentError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        )

    return _serialize_transaction(txn)


# ============================================================
# PAYMENT STATUS
# ============================================================


@router.get(
    "/api/stores/{store_id}/payments/{payment_id}",
)
def get_payment(
    store_id: int,
    payment_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.read")
    ),
    db: Session = Depends(get_db),
):
    """Get payment details."""
    try:
        txn = (
            db.query(payment_service.PaymentTransaction)
            .filter(
                payment_service.PaymentTransaction.id
                == payment_id,
                payment_service.PaymentTransaction.organization_id
                == membership.organization_id,
                payment_service.PaymentTransaction.store_id
                == store_id,
            )
            .first()
        )
    except Exception:
        txn = None

    if not txn:
        from ..models import PaymentTransaction

        txn = (
            db.query(PaymentTransaction)
            .filter(
                PaymentTransaction.id == payment_id,
                PaymentTransaction.organization_id
                == membership.organization_id,
                PaymentTransaction.store_id == store_id,
            )
            .first()
        )

    if not txn:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PAYMENT_NOT_FOUND",
                "message": "Payment not found",
            },
        )

    return _serialize_transaction(txn)


@router.post(
    "/api/stores/{store_id}/payments/{payment_id}/reconcile",
)
async def reconcile_payment(
    store_id: int,
    payment_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    """Reconcile payment status with the provider."""
    try:
        txn = await payment_service.reconcile_payment_status(
            db,
            membership.organization_id,
            store_id,
            payment_id,
        )
        db.commit()
    except payment_service.PaymentError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        )

    return _serialize_transaction(txn)


# ============================================================
# CANCELLATION
# ============================================================


@router.post(
    "/api/stores/{store_id}/payments/{payment_id}/cancel",
)
async def cancel_payment(
    store_id: int,
    payment_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    """Cancel a pending payment."""
    try:
        txn = await payment_service.cancel_payment(
            db,
            membership.organization_id,
            store_id,
            payment_id,
        )
        db.commit()
    except payment_service.PaymentError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        )

    return _serialize_transaction(txn)


# ============================================================
# REVERSAL
# ============================================================


@router.post(
    "/api/stores/{store_id}/payments/{payment_id}/reverse",
)
async def reverse_payment(
    store_id: int,
    payment_id: int,
    body: ReversePaymentRequest,
    membership: OrganizationMembership = Depends(
        require_permission("commerce.write")
    ),
    db: Session = Depends(get_db),
):
    """Reverse a paid payment."""
    try:
        txn = await payment_service.reverse_payment(
            db,
            membership.organization_id,
            store_id,
            payment_id,
            body.reason,
        )
        db.commit()
    except payment_service.PaymentError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        )

    return _serialize_transaction(txn)


# ============================================================
# WEBHOOK
# ============================================================


@router.post("/api/webhooks/payments/{provider}")
async def payment_webhook(
    provider: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Process a payment provider webhook."""
    body = await request.body()
    headers = dict(request.headers)

    try:
        result = await payment_service.process_webhook(
            db, provider, headers, body
        )
        db.commit()
    except payment_service.PaymentError as exc:
        db.rollback()
        logger.error(
            "webhook_error provider=%s code=%s",
            provider,
            exc.code,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        )

    return result


# ============================================================
# SERIALIZATION
# ============================================================


def _serialize_transaction(txn) -> dict[str, Any]:
    """Serialize a transaction for API response."""
    return {
        "id": txn.id,
        "provider": txn.provider,
        "status": txn.status,
        "amount": str(txn.amount),
        "currency": txn.currency,
        "payment_method": txn.payment_method,
        "provider_transaction_id": (
            txn.provider_transaction_id
        ),
        "order_id": txn.order_id,
        "customer_phone": _mask_phone(
            txn.customer_phone
        ),
        "provider_status": txn.provider_status,
        "expires_at": (
            txn.expires_at.isoformat()
            if txn.expires_at
            else None
        ),
        "paid_at": (
            txn.paid_at.isoformat()
            if txn.paid_at
            else None
        ),
        "created_at": (
            txn.created_at.isoformat()
            if txn.created_at
            else None
        ),
        "action_data": getattr(
            txn, "_action_data", None
        ),
    }


def _mask_phone(phone: str | None) -> str | None:
    """Mask phone number for API response."""
    if not phone or len(phone) < 6:
        return phone
    return f"{phone[:3]}***{phone[-2:]}"