"""Payment provider abstraction layer.

Defines the interface that all payment providers must implement.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any


class PaymentStatus(str, Enum):
    PENDING = "pending"
    REQUIRES_ACTION = "requires_action"
    PROCESSING = "processing"
    PAID = "paid"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"
    REVERSED = "reversed"


# Allowed status transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    PaymentStatus.PENDING: {
        PaymentStatus.REQUIRES_ACTION,
        PaymentStatus.PROCESSING,
        PaymentStatus.PAID,
        PaymentStatus.REJECTED,
        PaymentStatus.CANCELLED,
        PaymentStatus.EXPIRED,
        PaymentStatus.FAILED,
    },
    PaymentStatus.REQUIRES_ACTION: {
        PaymentStatus.PROCESSING,
        PaymentStatus.PAID,
        PaymentStatus.REJECTED,
        PaymentStatus.CANCELLED,
        PaymentStatus.EXPIRED,
        PaymentStatus.FAILED,
    },
    PaymentStatus.PROCESSING: {
        PaymentStatus.PAID,
        PaymentStatus.REJECTED,
        PaymentStatus.EXPIRED,
        PaymentStatus.FAILED,
    },
    PaymentStatus.PAID: {
        PaymentStatus.REVERSED,
    },
    PaymentStatus.REJECTED: set(),
    PaymentStatus.CANCELLED: set(),
    PaymentStatus.EXPIRED: set(),
    PaymentStatus.FAILED: set(),
    PaymentStatus.REVERSED: set(),
}


def is_valid_transition(
    current: str, target: str
) -> bool:
    allowed = VALID_TRANSITIONS.get(
        current, set()
    )
    return target in allowed


@dataclass
class ProviderPaymentResult:
    """Result of a payment creation request."""
    provider_transaction_id: str
    status: PaymentStatus
    provider_status: str
    payment_method: str
    expires_at: str | None = None
    raw_response: dict[str, Any] | None = None
    requires_action: bool = False
    action_data: dict[str, Any] | None = None


@dataclass
class ProviderStatusResult:
    """Result of a payment status query."""
    status: PaymentStatus
    provider_status: str
    provider_error_code: str | None = None
    provider_error_message: str | None = None
    paid_at: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class ProviderReversalResult:
    """Result of a payment reversal."""
    status: PaymentStatus
    provider_status: str
    provider_error_code: str | None = None
    provider_error_message: str | None = None
    raw_response: dict[str, Any] | None = None


class PaymentProvider(ABC):
    """Abstract base class for payment providers."""

    @property
    @abstractmethod
    def provider_code(self) -> str:
        """Unique provider identifier (e.g. 'nequi')."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name."""
        ...

    @property
    @abstractmethod
    def supported_countries(self) -> list[str]:
        """ISO 3166-1 alpha-2 country codes."""
        ...

    @property
    @abstractmethod
    def supported_currencies(self) -> list[str]:
        """ISO 4217 currency codes."""
        ...

    @property
    @abstractmethod
    def supported_payment_methods(self) -> list[str]:
        """Payment method codes (e.g. 'nequi_push', 'nequi_qr')."""
        ...

    @property
    def supports_webhooks(self) -> bool:
        return False

    @property
    def supports_reversals(self) -> bool:
        return False

    def is_available(
        self,
        country_code: str,
        currency: str,
    ) -> bool:
        return (
            country_code in self.supported_countries
            and currency in self.supported_currencies
        )

    @abstractmethod
    async def authenticate(
        self,
        credentials: dict[str, str],
        environment: str,
    ) -> dict[str, Any]:
        """Authenticate with the provider and return token data."""
        ...

    @abstractmethod
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
        """Create a payment request with the provider."""
        ...

    @abstractmethod
    async def get_payment_status(
        self,
        credentials: dict[str, str],
        environment: str,
        provider_transaction_id: str,
    ) -> ProviderStatusResult:
        """Query the current status of a payment."""
        ...

    @abstractmethod
    async def cancel_payment(
        self,
        credentials: dict[str, str],
        environment: str,
        provider_transaction_id: str,
    ) -> ProviderStatusResult:
        """Cancel a pending payment."""
        ...

    async def reverse_payment(
        self,
        credentials: dict[str, str],
        environment: str,
        provider_transaction_id: str,
        amount: Decimal,
        reason: str,
    ) -> ProviderReversalResult:
        """Reverse a completed payment. Override if supported."""
        raise NotImplementedError(
            f"{self.provider_code} does not support reversals"
        )

    def verify_webhook(
        self,
        headers: dict[str, str],
        body: bytes,
        webhook_secret: str,
    ) -> bool:
        """Verify webhook authenticity. Override if supported."""
        raise NotImplementedError(
            f"{self.provider_code} does not support webhooks"
        )

    def parse_webhook(
        self,
        headers: dict[str, str],
        body: bytes,
    ) -> dict[str, Any]:
        """Parse webhook payload. Override if supported."""
        raise NotImplementedError(
            f"{self.provider_code} does not support webhooks"
        )
