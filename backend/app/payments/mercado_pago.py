"""Mercado Pago PIX payment provider for Brazil.

Uses Mercado Pago's official Payments API. PIX is exposed only for
Brazil/BRL. Credentials are stored through the existing encrypted payment
connection fields; ``client_secret`` contains the Mercado Pago Access Token.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import httpx

from .base import (
    PaymentProvider,
    PaymentStatus,
    ProviderPaymentResult,
    ProviderReversalResult,
    ProviderStatusResult,
)

API_BASE = "https://api.mercadopago.com"

STATUS_MAP: dict[str, PaymentStatus] = {
    "pending": PaymentStatus.PENDING,
    "approved": PaymentStatus.PAID,
    "authorized": PaymentStatus.PROCESSING,
    "in_process": PaymentStatus.PROCESSING,
    "in_mediation": PaymentStatus.PROCESSING,
    "rejected": PaymentStatus.REJECTED,
    "cancelled": PaymentStatus.CANCELLED,
    "refunded": PaymentStatus.REVERSED,
    "charged_back": PaymentStatus.REVERSED,
}


def _normalized_status(value: str | None) -> PaymentStatus:
    return STATUS_MAP.get((value or "").lower(), PaymentStatus.PENDING)


class MercadoPagoPixProvider(PaymentProvider):
    @property
    def provider_code(self) -> str:
        return "mercado_pago"

    @property
    def display_name(self) -> str:
        return "Mercado Pago"

    @property
    def supported_countries(self) -> list[str]:
        return ["BR"]

    @property
    def supported_currencies(self) -> list[str]:
        return ["BRL"]

    @property
    def supported_payment_methods(self) -> list[str]:
        return ["pix"]

    @property
    def supports_reversals(self) -> bool:
        return True

    async def authenticate(
        self,
        credentials: dict[str, str],
        environment: str,
    ) -> dict[str, Any]:
        access_token = credentials.get("client_secret", "").strip()
        if not access_token:
            raise ValueError("Mercado Pago access token is required")
        return {"access_token": access_token}

    async def _headers(
        self,
        credentials: dict[str, str],
        environment: str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, str]:
        auth = await self.authenticate(credentials, environment)
        headers = {
            "Authorization": f"Bearer {auth['access_token']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key
        return headers

    async def create_payment(
        self,
        credentials: dict[str, str],
        environment: str,
        amount: Decimal,
        currency: str,
        customer_phone: str,
        description: str,
        idempotency_key: str,
        metadata: dict[str, Any] | None = None,
    ) -> ProviderPaymentResult:
        if currency != "BRL":
            raise ValueError("PIX through Mercado Pago requires BRL")

        payer = metadata or {}
        email = str(payer.get("customer_email") or "").strip()
        document = "".join(
            ch for ch in str(payer.get("customer_document") or "") if ch.isdigit()
        )
        document_type = str(
            payer.get("customer_document_type") or "CPF"
        ).upper()

        if not email:
            raise ValueError("customer_email is required for PIX")
        if document_type != "CPF" or len(document) != 11:
            raise ValueError("A valid 11-digit CPF is required for PIX")

        payload: dict[str, Any] = {
            "transaction_amount": float(amount),
            "description": description,
            "payment_method_id": "pix",
            "payer": {
                "email": email,
                "identification": {
                    "type": "CPF",
                    "number": document,
                },
            },
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE}/v1/payments",
                headers=await self._headers(
                    credentials,
                    environment,
                    idempotency_key=idempotency_key,
                ),
                json=payload,
            )

        if response.status_code not in (200, 201):
            detail = response.text[:500]
            raise RuntimeError(
                f"Mercado Pago payment creation failed: "
                f"{response.status_code} {detail}"
            )

        data = response.json()
        transaction_data = (
            data.get("point_of_interaction", {})
            .get("transaction_data", {})
        )
        action_data = {
            "qr_code": transaction_data.get("qr_code"),
            "qr_code_base64": transaction_data.get("qr_code_base64"),
            "ticket_url": transaction_data.get("ticket_url"),
        }
        action_data = {k: v for k, v in action_data.items() if v}

        return ProviderPaymentResult(
            provider_transaction_id=str(data["id"]),
            status=_normalized_status(data.get("status")),
            provider_status=str(data.get("status") or "pending"),
            payment_method="pix",
            expires_at=data.get("date_of_expiration"),
            raw_response=data,
            requires_action=bool(action_data),
            action_data=action_data or None,
        )

    async def get_payment_status(
        self,
        credentials: dict[str, str],
        environment: str,
        provider_transaction_id: str,
    ) -> ProviderStatusResult:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{API_BASE}/v1/payments/{provider_transaction_id}",
                headers=await self._headers(credentials, environment),
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"Mercado Pago status query failed: {response.status_code}"
            )
        data = response.json()
        return ProviderStatusResult(
            status=_normalized_status(data.get("status")),
            provider_status=str(data.get("status") or "pending"),
            provider_error_code=data.get("status_detail")
            if data.get("status") == "rejected"
            else None,
            paid_at=data.get("date_approved"),
            raw_response=data,
        )

    async def cancel_payment(
        self,
        credentials: dict[str, str],
        environment: str,
        provider_transaction_id: str,
    ) -> ProviderStatusResult:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.put(
                f"{API_BASE}/v1/payments/{provider_transaction_id}",
                headers=await self._headers(credentials, environment),
                json={"status": "cancelled"},
            )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Mercado Pago cancellation failed: {response.status_code}"
            )
        data = response.json()
        return ProviderStatusResult(
            status=_normalized_status(data.get("status")),
            provider_status=str(data.get("status") or "cancelled"),
            raw_response=data,
        )

    async def reverse_payment(
        self,
        credentials: dict[str, str],
        environment: str,
        provider_transaction_id: str,
        amount: Decimal,
        reason: str,
    ) -> ProviderReversalResult:
        idem = str(uuid.uuid4())
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE}/v1/payments/{provider_transaction_id}/refunds",
                headers=await self._headers(
                    credentials,
                    environment,
                    idempotency_key=idem,
                ),
                json={},
            )
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"Mercado Pago refund failed: {response.status_code}"
            )
        data = response.json()
        refund_status = str(data.get("status") or "approved").lower()
        normalized = (
            PaymentStatus.REVERSED
            if refund_status in {"approved", "refunded"}
            else PaymentStatus.PROCESSING
        )
        return ProviderReversalResult(
            status=normalized,
            provider_status=refund_status,
            raw_response=data,
        )
