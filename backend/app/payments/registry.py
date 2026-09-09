"""Payment provider registry.

Central registry for all payment providers. Avoids scattered
'if provider == "nequi"' checks throughout the codebase.
"""
from __future__ import annotations

from .base import PaymentProvider
from .nequi import NequiPaymentProvider

_providers: dict[str, PaymentProvider] = {}


def _register(provider: PaymentProvider) -> None:
    _providers[provider.provider_code] = provider


def get_provider(code: str) -> PaymentProvider | None:
    return _providers.get(code)


def get_all_providers() -> list[PaymentProvider]:
    return list(_providers.values())


def get_providers_for_market(
    country_code: str,
    currency: str,
) -> list[PaymentProvider]:
    return [
        p
        for p in _providers.values()
        if p.is_available(country_code, currency)
    ]


# Register all providers
_register(NequiPaymentProvider())
