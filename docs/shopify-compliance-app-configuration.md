# Shopify mandatory compliance webhooks — app-level configuration

Status (2026-10-14): **HMAC-verified receipt and automatic review-work-item handoff implemented in draft PR #223; not deployed, not verified in Shopify Dev Dashboard, and not yet fully compliant.**

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

## Runtime contract — PR #223

The signed receiver `POST https://api.diaglob.tech/api/webhooks/shopify/compliance` checks Shopify's base64 HMAC-SHA256 over the exact raw request bytes. A missing or invalid HMAC receives **401**, an unrecognized compliance topic **400**, and an oversized body **413**. A valid payload is stored as a minimal encrypted-selector receipt with a signed audit trail; it is assigned ten durable review work items before the server returns **200**.

The signed receipt, signed-audit event and ten blocked review tasks now commit in one fast database transaction without customer-data assessment. Transaction failures receive HTTP 500 with no partial receipt; Shopify may retry. Existing authenticated receipts missing tasks are repaired idempotently. The five-second delivery deadline remains a production latency verification requirement (https://shopify.dev/docs/apps/build/webhooks/verify-deliveries). This is not data export or erasure fulfillment.

The receiver does **not** delete customer data on receipt. `customers/data_request` creates a blocked secure-delivery item, while `customers/redact` and `shop/redact` create blocked reimport-suppression items. Legal retention, processor copies, offsite recovery, independent authorized export and real production erasure are still gated. The live production code, GDPR processing policy, Shopify app-version configuration, and live signed-delivery behavior must be independently verified.

### Safe go-live sequence

1. Merge/deploy the tested backend and database migrations; confirm environment variables `SHOPIFY_CLIENT_SECRET` and `SHOPIFY_TOKEN_ENCRYPTION_KEY` are securely available. Do not print them.
2. Link the **existing** Diaglob Shopify application and add the TOML subscription block above without replacing existing settings.
3. Use `python -m app.shopify_app_config_audit --path /path/to/shopify.app.toml --expected-app-url https://<existing-app-url> --expected-mode embedded|standalone` with the *actual* existing app settings; passing local TOML does not mean a version was published.
4. After owner approval, deploy a new existing-app version through Shopify CLI or the Dev Dashboard; confirm its activated version lists all three mandatory compliance topics and the exact callback URL. Trigger synthetic delivery for each topic with the Shopify CLI and verify results.
5. Inspect only privacy-safe processing status and counts: one durable receipt and ten review items per delivery ID, HMAC failures rejected, replays idempotent, no customer IDs, emails, phones, tokens or signed bodies in logs.
6. Complete an independently approved customer export, erasure and retention procedure; verify third-party copies, backups and a restoration drill before declaring compliance complete.

Do **not** publish another app, fabricate a full TOML file with guessed client ID/scopes, or assume GitHub CI deploys subscriptions to the active Shopify app.


## Acceptance tests

- Connecting/reconnecting a test Shopify store **does not** issue `webhookSubscriptionCreate` for any of the mandatory privacy topics.
- Order-topic registration continues to list/retain/create exactly the necessary shop-specific order subscriptions.
- The existing DIAGLOB Shopify app (not a new one) has the three mandatory topics in its **deployed** app configuration and the callback matches the HMAC-verified backend receiver.
- The privacy data export/redaction workflow passes synthetic-data E2E tests before changing the readiness matrix to PASS.
