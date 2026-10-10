"""Fail-closed Shopify App Store release readiness evaluation.

No Shopify API calls, database writes, billing, or production changes.
"""
from __future__ import annotations

from dataclasses import dataclass

REQUIRED_GATES = (
    "privacy_export_and_redaction",
    "retention_and_legal_holds",
    "external_processors_and_backups",
    "anti_reingestion",
    "shopify_billing_entitlements",
    "oauth_install_uninstall_e2e",
    "protected_customer_data_scopes",
    "checkout_order_policy_review",
    "listing_and_partner_dashboard",
    "release_head_ci",
)


@dataclass(frozen=True)
class ShopifyReleaseReadiness:
    ready: bool
    missing: tuple[str, ...]


def evaluate_shopify_release_readiness(
    evidence: dict[str, bool] | None = None,
) -> ShopifyReleaseReadiness:
    """Unknown, absent and non-boolean evidence fails closed.

    An affirmative result is a technical checklist, not legal or Shopify
    approval. Evidence must be independently verified for the exact release.
    """
    supplied = evidence or {}
    missing = tuple(
        gate for gate in REQUIRED_GATES
        if type(supplied.get(gate)) is not bool or supplied[gate] is not True
    )
    return ShopifyReleaseReadiness(ready=not missing, missing=missing)
