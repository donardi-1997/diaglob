"""Provider-neutral supplier integration primitives."""

from .base import (
    SupplierCapabilityNotSupportedError,
    SupplierNotConfiguredError,
    SupplierProvider,
    SupplierProviderError,
)
from .context import SupplierRuntimeContext
from .registry import (
    SupplierProviderNotRegisteredError,
    clear_supplier_registry,
    get_supplier_provider,
    register_supplier_provider,
    registered_supplier_providers,
)

__all__ = [
    "SupplierCapabilityNotSupportedError",
    "SupplierNotConfiguredError",
    "SupplierProvider",
    "SupplierProviderError",
    "SupplierRuntimeContext",
    "SupplierProviderNotRegisteredError",
    "clear_supplier_registry",
    "get_supplier_provider",
    "register_supplier_provider",
    "registered_supplier_providers",
]
