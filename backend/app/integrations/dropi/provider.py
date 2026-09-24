"""Dropi supplier adapter compatibility layer.

Dropi remains a placeholder until official API access is available. The module
now implements Diaglob's provider-neutral SupplierProvider contract so legacy
Dropi code can coexist with CJ and future suppliers without defining the core
supplier interface.
"""

from __future__ import annotations

from abc import ABC
from typing import Any

from ...suppliers import (
    SupplierNotConfiguredError,
    SupplierProvider,
    SupplierProviderError,
)


class DropiNotConfiguredError(SupplierNotConfiguredError):
    """Raised when Dropi integration is not configured."""

    def __init__(self):
        super().__init__("dropi")
        self.args = (
            "Dropi integration is not yet configured. "
            "Awaiting official API access and credentials.",
        )


class DropiProviderError(SupplierProviderError):
    """Raised when Dropi API returns an error."""


class DropiProvider(SupplierProvider, ABC):
    """Dropi-specific supplier provider contract."""

    provider_key = "dropi"


class DropiPlaceholder(DropiProvider):
    """Placeholder implementation that fails clearly until Dropi is usable."""

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
    """Return the Dropi implementation available in this runtime."""
    import os

    api_key = os.getenv("DROPI_API_KEY")
    api_base = os.getenv("DROPI_API_BASE_URL")

    if api_key and api_base:
        # Keep the placeholder until a documented official implementation
        # exists. Never invent production endpoints or credentials.
        pass

    return DropiPlaceholder()
