"""
Dropi integration abstraction for Diaglob.

This module provides a clean interface for the Dropi commerce
provider. The actual implementation will be added when Dropi
provides official API access, documentation, and credentials.

DO NOT:
- Invent API endpoints
- Mock production responses
- Hardcode fake credentials
- Create虚假 integrations

DO:
- Define clean interfaces
- Raise clear errors when not configured
- Allow seamless swap when real implementation arrives
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DropiNotConfiguredError(Exception):
    """Raised when Dropi integration is not configured."""

    def __init__(self):
        super().__init__(
            "Dropi integration is not yet configured. "
            "Awaiting official API access and credentials."
        )


class DropiProviderError(Exception):
    """Raised when Dropi API returns an error."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class DropiProvider(ABC):
    """
    Abstract interface for Dropi commerce operations.

    When Dropi provides official access, implement this class
    with real API calls.
    """

    @abstractmethod
    def get_products(
        self,
        store_id: int,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve products from Dropi."""
        ...

    @abstractmethod
    def create_order(
        self,
        store_id: int,
        items: list[dict[str, Any]],
        customer: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an order in Dropi."""
        ...

    @abstractmethod
    def get_order(
        self,
        store_id: int,
        order_id: str,
    ) -> dict[str, Any]:
        """Get order details from Dropi."""
        ...

    @abstractmethod
    def get_shipping_quote(
        self,
        store_id: int,
        items: list[dict[str, Any]],
        destination: dict[str, Any],
    ) -> dict[str, Any]:
        """Get shipping quote from Dropi."""
        ...


class DropiPlaceholder(DropiProvider):
    """
    Placeholder implementation that raises clear errors.

    Used when Dropi is not configured. This ensures the
    system degrades gracefully.
    """

    def get_products(
        self,
        store_id: int,
        query: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        raise DropiNotConfiguredError()

    def create_order(
        self,
        store_id: int,
        items: list[dict[str, Any]],
        customer: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise DropiNotConfiguredError()

    def get_order(
        self,
        store_id: int,
        order_id: str,
    ) -> dict[str, Any]:
        raise DropiNotConfiguredError()

    def get_shipping_quote(
        self,
        store_id: int,
        items: list[dict[str, Any]],
        destination: dict[str, Any],
    ) -> dict[str, Any]:
        raise DropiNotConfiguredError()


def get_dropi_provider() -> DropiProvider:
    """
    Factory function to get the appropriate Dropi provider.

    When real credentials are available, this will return
    the actual implementation. For now, returns placeholder.
    """
    import os

    api_key = os.getenv("DROPI_API_KEY")
    api_base = os.getenv("DROPI_API_BASE_URL")

    if api_key and api_base:
        # When real implementation is ready:
        # return DropiRealProvider(api_key, api_base)
        pass

    return DropiPlaceholder()
