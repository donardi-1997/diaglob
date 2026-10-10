# Shopify mandatory compliance webhooks — app-level configuration

Status: **code prepared; not deployed, not verified in the Shopify Dev Dashboard, and not yet compliant.**

## Why

Shopify's mandatory `customers/data_request`, `customers/redact`, and `shop/redact` subscriptions must be defined on the **app**, not created for each merchant using GraphQL Admin API `webhookSubscriptionCreate`. The current application is **DIAGLOB**, existing Shopify app ID **416524435457**, Partner organization **5148778**. Do not create or link a different Shopify application.

Shopify documentation:
- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/build/cli-for-apps/app-configuration
- https://shopify.dev/docs/api/webhooks/unstable

## Configuration to add to the EXISTING Shopify app

The `shopify.app.toml` is **not** currently tracked in this repository. Do not fabricate a complete app config with unknown `client_id`, redirect URLs, scopes or embedded settings.

1. In a development environment with Shopify CLI installed and authenticated to the appropriate Shopify developer account, use `shopify app config link` and **select the existing DIAGLOB application**. Preserve its already-deployed settings.
2. In the linked `shopify.app.toml`, keep the existing `[webhooks]` section and `api_version`; add this subscription block (exactly once):

```toml
[[webhooks.subscriptions]]
compliance_topics = ["customers/data_request", "customers/redact", "shop/redact"]
uri = "https://api.diaglob.tech/api/webhooks/shopify/compliance"
```

3. Verify that the linked configuration's **app ID, scopes, redirect URLs, embedded setting and API version** match the existing DIAGLOB Dev Dashboard configuration. In particular, verify that the HTTPS webhook receiver route is deployed and can validate HMAC signatures before registering the app-level subscription.
4. After explicit owner approval for updating the active Shopify app configuration, use `shopify app deploy` to publish a version. Do not execute it as part of a code-only PR.
5. Inspect the deployed **app version** and compliance subscriptions in Shopify's Dev Dashboard, then test invalid HMAC (must reject), valid HMAC, supported topics, merchant/store identity and retry behavior.

Existing order webhooks continue to use per-shop GraphQL subscriptions at `/api/webhooks/shopify`; mandatory compliance webhooks use `/api/webhooks/shopify/compliance`.

## Current limitations — NOT READY FOR APP STORE SUBMISSION

The backend callback in the draft PR #149 currently **acknowledges and logs an event digest only**. It does not durably enqueue or fulfill export, redaction or store deletion requests. A passing HTTP 200 or CI test does **not** show lawful handling of data-subject requests.

Owner approved a provisional retention policy **for development on synthetic data only**, recorded in issue #148; this is not legal sign-off or permission to erase production data. Privacy request persistence, processing, tenant isolation and retention exceptions must be completed and tested. Shopify subscription deployment, production backend deployment, merchant billing and real-data destructive operations each require explicit approval.

## Acceptance tests

- Connecting/reconnecting a test Shopify store **does not** issue `webhookSubscriptionCreate` for any of the mandatory privacy topics.
- Order-topic registration continues to list/retain/create exactly the necessary shop-specific order subscriptions.
- The existing DIAGLOB Shopify app (not a new one) has the three mandatory topics in its **deployed** app configuration and the callback matches the HMAC-verified backend receiver.
- The privacy data export/redaction workflow passes synthetic-data E2E tests before changing the readiness matrix to PASS.
