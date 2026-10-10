# Shopify App Pricing channel guard

Status: development-only; no Shopify billing entitlement sync is activated.

Organizations whose trusted server-assigned `billing_provider` equals `shopify` must not use Paddle checkout, upgrade, downgrade, renewal, or downgrade cancellation routes. The HTTP API returns 409 `SHOPIFY_MANAGED_BILLING` so the UI can guide merchants to Shopify-managed plan selection. Verified incoming Paddle events for such organizations are acknowledged but ignored for entitlement mutation, preventing accidental overwrites of a Shopify-managed plan.

**Important:** This guard relies on trusted channel provenance. The system must not assign `billing_provider=shopify` based solely on a user-entered domain or redirect. The server-side onboarding and verified subscription reconciliation that set this value are still pending.

Legacy organizations with a null provider or explicit `paddle` continue using Paddle unchanged. No Shopify plan, payment, or subscription is created or changed by this code.

Pending: hosted Shopify pricing navigation, trusted initial channel binding, Shopify-managed entitlement synchronization, full retry/reconciliation, and documented migrations for legacy customers.
