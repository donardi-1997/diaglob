"""Provider-neutral billing contracts.

Business services depend on this module rather than concrete payment providers.
Adapters translate provider-specific configuration and transport failures into the
stable exceptions below.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BillingProviderConfigurationError(Exception):
    """Raised when a configured billing provider cannot be used."""


class UnsupportedBillingProviderError(BillingProviderConfigurationError):
    """Raised when an organization references an unregistered provider."""


class BillingProviderError(Exception):
    """Provider-neutral error surfaced by billing adapters."""

    def __init__(
        self,
        *,
        provider: str,
        status_code: int = 502,
        detail: Any = None,
    ) -> None:
        self.provider = provider
        self.status_code = int(status_code or 502)
        self.detail = detail or {"message": "Billing provider request failed"}
        super().__init__(str(self.detail))


class BillingProvider(ABC):
    """Capabilities required by Diaglob subscription billing orchestration."""

    name: str
    webhook_signature_header: str | None = None

    @abstractmethod
    def is_configured(self) -> bool:
        """Return whether the provider has enough configuration for API calls."""

    @abstractmethod
    def get_price_id(self, plan: str, billing_period_months: int = 1) -> str:
        """Resolve the provider price identifier for a Diaglob plan/period."""

    @abstractmethod
    def get_plan_from_price_id(self, price_id: str) -> str | None:
        """Resolve a provider price identifier back to a Diaglob plan."""

    @abstractmethod
    def get_billing_period_from_price_id(self, price_id: str) -> int | None:
        """Resolve a provider price identifier back to a billing period."""

    @abstractmethod
    def get_subscription_price_id(self, data: dict) -> str | None:
        """Extract the active price identifier from provider subscription data."""

    @abstractmethod
    def create_transaction(
        self,
        *,
        price_id: str,
        organization_id: int,
        plan_key: str,
        billing_period_months: int,
    ) -> dict:
        """Create a checkout-capable subscription transaction."""

    @abstractmethod
    def get_subscription(self, subscription_id: str) -> dict:
        """Fetch provider subscription state."""

    @abstractmethod
    def preview_subscription_update(
        self,
        *,
        subscription_id: str,
        items: list[dict],
        proration_billing_mode: str,
        on_payment_failure: str = "prevent_change",
        next_billed_at: str | None = None,
    ) -> dict:
        """Preview a subscription mutation."""

    @abstractmethod
    def update_subscription(
        self,
        *,
        subscription_id: str,
        items: list[dict],
        proration_billing_mode: str,
        on_payment_failure: str = "prevent_change",
        custom_data: dict | None = None,
        timeout: int = 45,
        next_billed_at: str | None = None,
    ) -> dict:
        """Apply a subscription mutation."""

    @abstractmethod
    def cancel_subscription(self, subscription_id: str) -> dict:
        """Schedule subscription cancellation."""

    @abstractmethod
    def resume_subscription(self, subscription_id: str) -> dict:
        """Remove a scheduled cancellation when supported."""

    @abstractmethod
    def verify_webhook(self, raw_body: bytes, signature_header: str) -> None:
        """Validate provider webhook authenticity."""
