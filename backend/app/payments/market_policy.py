"""Country and currency policy for local payment methods.

This module is intentionally provider-agnostic. It defines where a
payment method is allowed, while concrete provider adapters remain
responsible for actually processing the payment.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PaymentMethodMarket:
    code: str
    display_name: str
    countries: frozenset[str]
    currencies: frozenset[str]

    def is_available(self, country_code: str, currency: str) -> bool:
        return (
            country_code.upper() in self.countries
            and currency.upper() in self.currencies
        )


PAYMENT_METHOD_MARKETS: dict[str, PaymentMethodMarket] = {
    "nequi_push": PaymentMethodMarket(
        code="nequi_push",
        display_name="Nequi",
        countries=frozenset({"CO"}),
        currencies=frozenset({"COP"}),
    ),
    "pix": PaymentMethodMarket(
        code="pix",
        display_name="PIX",
        countries=frozenset({"BR"}),
        currencies=frozenset({"BRL"}),
    ),
}


def payment_method_available(
    payment_method: str,
    country_code: str,
    currency: str,
) -> bool:
    """Return whether a local payment method is valid for a market."""
    market = PAYMENT_METHOD_MARKETS.get(payment_method.lower())
    if market is None:
        return False
    return market.is_available(country_code, currency)


def get_payment_methods_for_market(
    country_code: str,
    currency: str,
) -> list[dict[str, str]]:
    """List market-eligible local payment methods.

    Eligibility does not imply that a concrete processing provider is
    connected. Callers must still verify provider support/connection.
    """
    return [
        {"code": market.code, "name": market.display_name}
        for market in PAYMENT_METHOD_MARKETS.values()
        if market.is_available(country_code, currency)
    ]
