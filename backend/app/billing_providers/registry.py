"""Billing provider registry and organization-level resolution."""
from __future__ import annotations

from typing import Any

from .base import BillingProvider, UnsupportedBillingProviderError
from .paddle import PaddleBillingProvider

DEFAULT_BILLING_PROVIDER = "paddle"

_PROVIDERS: dict[str, BillingProvider] = {
    "paddle": PaddleBillingProvider(),
}


def register_billing_provider(provider: BillingProvider, *, replace: bool = False) -> None:
    """Register an adapter without changing billing orchestration code."""
    name = (provider.name or "").strip().lower()
    if not name:
        raise ValueError("Billing provider name is required")
    if name in _PROVIDERS and not replace:
        raise ValueError(f"Billing provider already registered: {name}")
    _PROVIDERS[name] = provider


def get_billing_provider(name: str | None = None) -> BillingProvider:
    normalized = (name or DEFAULT_BILLING_PROVIDER).strip().lower()
    provider = _PROVIDERS.get(normalized)
    if provider is None:
        raise UnsupportedBillingProviderError(
            f"Unsupported billing provider: {normalized}"
        )
    return provider


def get_billing_provider_for_organization(organization: Any) -> BillingProvider:
    """Legacy organizations without a provider continue to use Paddle."""
    return get_billing_provider(getattr(organization, "billing_provider", None))


def registered_billing_providers() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))
