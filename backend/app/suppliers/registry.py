"""Supplier provider registry.

Application services can resolve suppliers by stable provider key without
importing vendor-specific modules.
"""

from __future__ import annotations

from collections.abc import Callable

from .base import SupplierProvider
from .context import SupplierRuntimeContext


class SupplierProviderNotRegisteredError(LookupError):
    """Raised when a provider key has no registered factory."""


SupplierFactory = Callable[[SupplierRuntimeContext], SupplierProvider]

_provider_factories: dict[str, SupplierFactory] = {}


def _normalize_key(provider_key: str) -> str:
    key = (provider_key or "").strip().lower()
    if not key:
        raise ValueError("Supplier provider key is required")
    return key


def register_supplier_provider(
    provider_key: str,
    factory: SupplierFactory,
    *,
    replace: bool = False,
) -> None:
    """Register a provider factory under a normalized key."""
    key = _normalize_key(provider_key)

    if key in _provider_factories and not replace:
        raise ValueError(f"Supplier provider already registered: {key}")

    _provider_factories[key] = factory


def get_supplier_provider(
    provider_key: str,
    context: SupplierRuntimeContext,
) -> SupplierProvider:
    """Resolve a tenant-scoped provider instance from its registered factory."""
    key = _normalize_key(provider_key)

    factory = _provider_factories.get(key)
    if factory is None:
        raise SupplierProviderNotRegisteredError(
            f"Supplier provider is not registered: {key}"
        )

    provider = factory(context)
    if not isinstance(provider, SupplierProvider):
        raise TypeError(
            f"Supplier factory for {key} returned an invalid provider"
        )

    if provider.key() != key:
        raise ValueError(
            f"Supplier provider key mismatch: expected {key}, got {provider.key()}"
        )

    return provider


def registered_supplier_providers() -> tuple[str, ...]:
    """Return registered provider keys in deterministic order."""
    return tuple(sorted(_provider_factories))


def clear_supplier_registry() -> None:
    """Clear registrations. Intended for test isolation."""
    _provider_factories.clear()
