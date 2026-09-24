"""Supplier provider contracts shared by all dropshipping integrations.

Provider/client modules stay outside the service layer. This module defines the
stable contract that Diaglob application services can depend on without
coupling the product to CJ, Dropi, or any future supplier.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar


class SupplierProviderError(Exception):
    """Base error raised by supplier integrations."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class SupplierNotConfiguredError(SupplierProviderError):
    """Raised when a supplier cannot be used because credentials are missing."""

    def __init__(self, provider: str):
        super().__init__(
            f"{provider} supplier integration is not configured.",
            status_code=503,
        )
        self.provider = provider


class SupplierCapabilityNotSupportedError(SupplierProviderError):
    """Raised when a provider does not implement an optional capability."""

    def __init__(self, provider: str, capability: str):
        super().__init__(
            f"{provider} does not support supplier capability: {capability}",
            status_code=501,
        )
        self.provider = provider
        self.capability = capability


class SupplierProvider(ABC):
    """Provider-neutral contract for supplier operations.

    The four abstract operations are the minimum viable supplier surface.
    Richer providers can override the optional capability methods below.
    """

    provider_key: ClassVar[str] = ""

    def key(self) -> str:
        key = (self.provider_key or "").strip().lower()
        if not key:
            raise ValueError("Supplier provider_key must be configured")
        return key

    @abstractmethod
    def get_products(
        self,
        store_id: int,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search or list products exposed by the supplier."""
        ...

    @abstractmethod
    def create_order(
        self,
        store_id: int,
        items: list[dict[str, Any]],
        customer: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a supplier-side fulfillment order."""
        ...

    @abstractmethod
    def get_order(
        self,
        store_id: int,
        order_id: str,
    ) -> dict[str, Any]:
        """Return supplier-side order details."""
        ...

    @abstractmethod
    def get_shipping_quote(
        self,
        store_id: int,
        items: list[dict[str, Any]],
        destination: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a shipping quote for items and destination."""
        ...

    def get_product(
        self,
        store_id: int,
        product_id: str,
    ) -> dict[str, Any]:
        raise SupplierCapabilityNotSupportedError(self.key(), "get_product")

    def get_variants(
        self,
        store_id: int,
        product_id: str,
    ) -> list[dict[str, Any]]:
        raise SupplierCapabilityNotSupportedError(self.key(), "get_variants")

    def get_stock(
        self,
        store_id: int,
        variant_id: str,
    ) -> dict[str, Any]:
        raise SupplierCapabilityNotSupportedError(self.key(), "get_stock")

    def cancel_order(
        self,
        store_id: int,
        order_id: str,
    ) -> dict[str, Any]:
        raise SupplierCapabilityNotSupportedError(self.key(), "cancel_order")

    def get_tracking(
        self,
        store_id: int,
        order_id: str,
    ) -> dict[str, Any]:
        raise SupplierCapabilityNotSupportedError(self.key(), "get_tracking")
