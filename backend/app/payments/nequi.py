"""Nequi Business payment provider adapter.

Implements the Nequi Push payment flow for Colombia/COP.

IMPORTANT: This adapter uses the official Nequi Business API.
Request/response fields match the documented Nequi API specification.
Unverified fields are isolated behind this adapter.

Nequi API reference:
- Authentication: OAuth2 client credentials
- Push payment: POST /payments/v2/payment
- Status query: GET /payments/v2/payment/{transactionId}
- Cancel: POST /payments/v2/payment/{transactionId}/cancel
- Webhooks: POST notification URL with signed payload
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
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

logger = logging.getLogger(__name__)

# Nequi API endpoints
NEQUI_ENDPOINTS = {
    "sandbox": {
        "auth": "https://oauth.sandbox.nequi.com/oauth2/token",
        "payments": "https://api.sandbox.nequi.com/payments/v2",
    },
    "production": {
        "auth": "https://oauth.nequi.com/oauth2/token",
        "payments": "https://api.nequi.com/payments/v2",
    },
}

# Nequi status -> Diaglob normalized status
NEQUI_STATUS_MAP: dict[str, PaymentStatus] = {
    "PENDING": PaymentStatus.PENDING,
    "APPROVED": PaymentStatus.PAID,
    "REJECTED": PaymentStatus.REJECTED,
    "EXPIRED": PaymentStatus.EXPIRED,
    "CANCELLED": PaymentStatus.CANCELLED,
    "FAILED": PaymentStatus.FAILED,
    "ERROR": PaymentStatus.FAILED,
}

# Token cache: {client_id: {"token": ..., "expires_at": ...}}
_token_cache: dict[str, dict[str, Any]] = {}


class NequiPaymentProvider(PaymentProvider):

    @property
    def provider_code(self) -> str:
        return "nequi"

    @property
    def display_name(self) -> str:
        return "Nequi"

    @property
    def supported_countries(self) -> list[str]:
        return ["CO"]

    @property
    def supported_currencies(self) -> list[str]:
        return ["COP"]

    @property
    def supported_payment_methods(self) -> list[str]:
        return ["nequi_push"]

    @property
    def supports_webhooks(self) -> bool:
        return True

    @property
    def supports_reversals(self) -> bool:
        return True

    def _get_endpoints(
        self, environment: str
    ) -> dict[str, str]:
        env = (
            "production"
            if environment == "production"
            else "sandbox"
        )
        return NEQUI_ENDPOINTS[env]

    async def authenticate(
        self,
        credentials: dict[str, str],
        environment: str,
    ) -> dict[str, Any]:
        """Get or refresh OAuth2 access token."""
        client_id = credentials.get("client_id", "")
        client_secret = credentials.get("client_secret", "")

        if not client_id or not client_secret:
            raise ValueError(
                "Nequi client_id and client_secret are required"
            )

        # Check cache
        cache_key = f"{client_id}:{environment}"
        cached = _token_cache.get(cache_key)
        if cached and cached.get("expires_at", 0) > time.time():
            return cached

        endpoints = self._get_endpoints(environment)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoints["auth"],
                data={
                    "grant_type": "client_credentials",
                },
                auth=(client_id, client_secret),
                headers={
                    "Content-Type": (
                        "application/x-www-form-urlencoded"
                    ),
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                logger.error(
                    "nequi_auth_failed status=%d",
                    response.status_code,
                )
                raise RuntimeError(
                    f"Nequi authentication failed: "
                    f"{response.status_code}"
                )

            data = response.json()
            expires_in = data.get("expires_in", 3600)

            token_data = {
                "access_token": data["access_token"],
                "token_type": data.get(
                    "token_type", "Bearer"
                ),
                "expires_at": (
                    time.time() + expires_in - 60
                ),
            }

            _token_cache[cache_key] = token_data
            return token_data

    async def _get_auth_headers(
        self,
        credentials: dict[str, str],
        environment: str,
    ) -> dict[str, str]:
        token_data = await self.authenticate(
            credentials, environment
        )
        return {
            "Authorization": (
                f"Bearer {token_data['access_token']}"
            ),
            "Content-Type": "application/json",
        }

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
        """Create a Nequi Push payment request."""
        if currency != "COP":
            raise ValueError(
                f"Nequi only supports COP, got {currency}"
            )

        headers = await self._get_auth_headers(
            credentials, environment
        )
        endpoints = self._get_endpoints(environment)

        # Nequi expects amount as integer centavos
        amount_centavos = int(amount * 100)

        # Normalize phone: strip spaces, dashes, leading +
        phone = customer_phone.strip()
        phone = phone.replace(" ", "").replace("-", "")
        if phone.startswith("+"):
            phone = phone[1:]
        # Colombia: ensure 57 prefix
        if not phone.startswith("57"):
            phone = f"57{phone}"

        request_body = {
            "phoneNumber": phone,
            "value": amount_centavos,
            "reference": idempotency_key,
            "description": description[:200],
        }

        logger.info(
            "nequi_create_payment idempotency_key=%s "
            "amount=%s phone_hint=%s***",
            idempotency_key,
            amount,
            phone[:3],
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{endpoints['payments']}/payment",
                json=request_body,
                headers={
                    **headers,
                    "X-Idempotency-Key": idempotency_key,
                },
                timeout=30.0,
            )

            data = response.json()

            if response.status_code not in (200, 201):
                error_code = data.get(
                    "code", "UNKNOWN"
                )
                error_message = data.get(
                    "message", "Payment creation failed"
                )
                logger.error(
                    "nequi_create_payment_failed "
                    "status=%d code=%s",
                    response.status_code,
                    error_code,
                )
                return ProviderPaymentResult(
                    provider_transaction_id="",
                    status=PaymentStatus.FAILED,
                    provider_status=error_code,
                    payment_method="nequi_push",
                    raw_response=data,
                )

            transaction_id = data.get(
                "transactionId", ""
            )
            nequi_status = data.get(
                "status", "PENDING"
            )
            normalized = NEQUI_STATUS_MAP.get(
                nequi_status, PaymentStatus.PENDING
            )

            # Calculate expiration (Nequi push typically
            # expires in 15 minutes)
            expires_at = None
            if normalized == PaymentStatus.PENDING:
                exp_dt = datetime.now(
                    timezone.utc
                ) + timedelta(minutes=15)
                expires_at = exp_dt.isoformat()

            logger.info(
                "nequi_payment_created "
                "transaction_id=%s status=%s",
                transaction_id,
                nequi_status,
            )

            return ProviderPaymentResult(
                provider_transaction_id=transaction_id,
                status=normalized,
                provider_status=nequi_status,
                payment_method="nequi_push",
                expires_at=expires_at,
                raw_response=data,
            )

    async def get_payment_status(
        self,
        credentials: dict[str, str],
        environment: str,
        provider_transaction_id: str,
    ) -> ProviderStatusResult:
        """Query Nequi payment status."""
        headers = await self._get_auth_headers(
            credentials, environment
        )
        endpoints = self._get_endpoints(environment)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                (
                    f"{endpoints['payments']}"
                    f"/payment/{provider_transaction_id}"
                ),
                headers=headers,
                timeout=30.0,
            )

            if response.status_code == 404:
                return ProviderStatusResult(
                    status=PaymentStatus.FAILED,
                    provider_status="NOT_FOUND",
                    provider_error_code="NOT_FOUND",
                    provider_error_message=(
                        "Payment not found at provider"
                    ),
                )

            data = response.json()

            if response.status_code != 200:
                return ProviderStatusResult(
                    status=PaymentStatus.FAILED,
                    provider_status="ERROR",
                    provider_error_code=data.get(
                        "code", "UNKNOWN"
                    ),
                    provider_error_message=data.get(
                        "message", "Status query failed"
                    ),
                    raw_response=data,
                )

            nequi_status = data.get(
                "status", "PENDING"
            )
            normalized = NEQUI_STATUS_MAP.get(
                nequi_status, PaymentStatus.PENDING
            )

            paid_at = None
            if normalized == PaymentStatus.PAID:
                paid_at = data.get(
                    "paidAt",
                    datetime.now(timezone.utc).isoformat(),
                )

            return ProviderStatusResult(
                status=normalized,
                provider_status=nequi_status,
                provider_error_code=data.get(
                    "errorCode"
                ),
                provider_error_message=data.get(
                    "errorMessage"
                ),
                paid_at=paid_at,
                raw_response=data,
            )

    async def cancel_payment(
        self,
        credentials: dict[str, str],
        environment: str,
        provider_transaction_id: str,
    ) -> ProviderStatusResult:
        """Cancel a pending Nequi payment."""
        headers = await self._get_auth_headers(
            credentials, environment
        )
        endpoints = self._get_endpoints(environment)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                (
                    f"{endpoints['payments']}"
                    f"/payment/{provider_transaction_id}"
                    f"/cancel"
                ),
                headers=headers,
                timeout=30.0,
            )

            data = response.json()

            if response.status_code != 200:
                nequi_status = data.get(
                    "status", "ERROR"
                )
                return ProviderStatusResult(
                    status=PaymentStatus.FAILED,
                    provider_status=nequi_status,
                    provider_error_code=data.get(
                        "code", "CANCEL_FAILED"
                    ),
                    provider_error_message=data.get(
                        "message",
                        "Cancellation failed",
                    ),
                    raw_response=data,
                )

            nequi_status = data.get(
                "status", "CANCELLED"
            )
            normalized = NEQUI_STATUS_MAP.get(
                nequi_status, PaymentStatus.CANCELLED
            )

            return ProviderStatusResult(
                status=normalized,
                provider_status=nequi_status,
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
        """Reverse a completed Nequi payment."""
        headers = await self._get_auth_headers(
            credentials, environment
        )
        endpoints = self._get_endpoints(environment)

        amount_centavos = int(amount * 100)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                (
                    f"{endpoints['payments']}"
                    f"/payment/{provider_transaction_id}"
                    f"/reverse"
                ),
                json={
                    "value": amount_centavos,
                    "reason": reason[:200],
                },
                headers=headers,
                timeout=30.0,
            )

            data = response.json()

            if response.status_code != 200:
                return ProviderReversalResult(
                    status=PaymentStatus.FAILED,
                    provider_status=data.get(
                        "status", "ERROR"
                    ),
                    provider_error_code=data.get(
                        "code", "REVERSE_FAILED"
                    ),
                    provider_error_message=data.get(
                        "message", "Reversal failed"
                    ),
                    raw_response=data,
                )

            nequi_status = data.get(
                "status", "REVERSED"
            )
            normalized = NEQUI_STATUS_MAP.get(
                nequi_status, PaymentStatus.REVERSED
            )

            return ProviderReversalResult(
                status=normalized,
                provider_status=nequi_status,
                raw_response=data,
            )

    def verify_webhook(
        self,
        headers: dict[str, str],
        body: bytes,
        webhook_secret: str,
    ) -> bool:
        """Verify Nequi webhook signature.

        Nequi uses HMAC-SHA256 of the raw body with
        the webhook secret.
        """
        signature = headers.get(
            "x-nequi-signature", ""
        )
        if not signature:
            signature = headers.get(
                "X-Nequi-Signature", ""
            )

        if not signature:
            logger.warning(
                "nequi_webhook_missing_signature"
            )
            return False

        expected = hmac.new(
            webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(
            signature.lower(), expected.lower()
        )

    def parse_webhook(
        self,
        headers: dict[str, str],
        body: bytes,
    ) -> dict[str, Any]:
        """Parse Nequi webhook payload."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid webhook JSON: {exc}"
            ) from exc

        return {
            "provider_transaction_id": data.get(
                "transactionId", ""
            ),
            "status": data.get("status", ""),
            "event_type": data.get("eventType", ""),
            "amount": data.get("value"),
            "currency": data.get("currency", "COP"),
            "phone_hash": data.get("phoneNumberHash"),
            "timestamp": data.get("timestamp"),
            "raw": data,
        }
