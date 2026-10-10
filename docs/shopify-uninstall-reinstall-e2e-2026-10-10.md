# Shopify uninstall / reinstall — secure E2E slice

Status: backend implementation for **signed** app lifecycle and same-tenant reinstall, pending Shopify development-store end-to-end verification.

## Implementation

- After a successful OAuth connection or manual `POST /api/stores/{store_id}/shopify/webhooks/ensure`, register four shop-scoped webhook topics: `ORDERS_CREATE`, `ORDERS_UPDATED`, `ORDERS_CANCELLED` and `APP_UNINSTALLED`. The uninstall callback is `https://api.diaglob.tech/api/webhooks/shopify/uninstalled`; it is **not** one of the three mandatory privacy topics, which are configured separately at app level.
- The uninstall callback requires **raw-body HMAC-SHA256 verification**, exact topic and canonical Shopify shop domain, positive shop ID, a valid `X-Shopify-Triggered-At`, and a request body of at most 256 KiB. Invalid signatures or mismatched identities cannot affect any connection.
- `X-Shopify-Triggered-At` is compared to the persisted installation `connected_at` timestamp. A delayed uninstall older than the latest installation is acknowledged but **must not** revoke the reconnected shop.
- On valid uninstall, retain the tenant/store binding for auditing, set connection `status=revoked`, clear Shopify token/refresh/API credentials, clear granted scopes, invalidate outstanding OAuth states for the store, and move `pending`/`retry` auto-fulfillment jobs to `waiting_shopify_reconnect`. It **does not** delete customers, orders, financial information or GDPR receipts, and **does not** settle billing.
- After uninstall, only an authorized Diaglob user who owns the **same store** may request new OAuth for the **same canonical Shopify domain**. Other tenant/store/domain claims remain blocked even when the old connection is revoked. Successful OAuth refreshes `connected_at`; it never reuses the previous token.

## Safety boundaries

- Shopify documents `X-Shopify-Triggered-At` for out-of-order webhook deliveries and `X-Shopify-Hmac-Sha256` for authenticated HTTPS callbacks; their header documentation is at https://shopify.dev/docs/apps/build/webhooks/delivery-structure.
- Delivery-ID deduplication currently relies on terminal `revoked` state and timestamp guard. A new persistent event-ID ledger with replay investigation and a separate reconciliation strategy would improve auditability for full App Store readiness.
- Shopify webhook processing is **not proof of personal-data deletion**, complete uninstall, or subscription cancellation. Must still complete production-ready GDPR processing and verify Shopify-managed subscription cancellation/reconciliation.
- Do not automatically delete the existing `CommerceConnection`: preserving the original tenant/store/shop mapping prevents a foreign organization from claiming that Shopify domain after an uninstall.
- A callback without a valid timestamp fails closed and does **not** disconnect the merchant; operational alerting/retry monitoring is required.

## Development-store E2E acceptance

1. Install from the existing Shopify app → authenticate in Diaglob → merchant selects authorized store → Shopify OAuth grants → ensure four shop-scoped subscriptions.
2. Uninstall from Shopify admin → signed webhook arrives → DB marks the correct connection revoked and clears token/scopes, jobs stopped; unrelated tenant/store and GDPR inbox unchanged.
3. Send same webhook twice → second delivery is idempotent. Send a webhook older than the next installation → no new revocation.
4. Reinstall **same** Shopify shop and **same** Diaglob store → new OAuth state, new token, connected status, `connected_at` refreshed, subscriptions restored.
5. Try cross-tenant or changed-domain reinstall → rejected before issuing an OAuth token.
6. Invalid HMAC, missing timestamp, forged shop domain, unsupported topic and oversized payload → fail closed without DB mutations.

## Out of scope

No live Shopify test-store action, no merchant charges, no protected customer-data release, no policy-driven deletion, no new Shopify app, no changes to production AWS or Shopify Partner Dashboard. CI tests use synthetic fixtures and mocks.

Tracked separately from PR #149 to keep review and deployment risks small.
