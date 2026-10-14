# DIAGLOB — Shopify mandatory webhooks + HMAC checklist (2026-10-13)

**Partner Dashboard observation:** Automatic checks passed install/authentication, redirect and TLS; failed mandatory privacy subscriptions and HMAC verification. This is **not** a Shopify App Store approval.

## What is implemented

- FastAPI endpoint: `POST https://api.diaglob.tech/api/webhooks/shopify/compliance`.
- The handler validates `X-Shopify-Hmac-Sha256` using the raw body and the app's `SHOPIFY_CLIENT_SECRET`; invalid/missing signatures get HTTP 401.
- The authenticated handler receives `customers/data_request`, `customers/redact` and `shop/redact` and records encrypted request selectors. **This records the request; it does not yet fulfill legal export/deletion.**
- The production deploy workflow probes HTTP 401 with an invalid signature. It does not prove that the webhooks are deployed in the active app version.

## Fix the original app's released configuration

1. In an authorized Shopify CLI project, run `shopify app config link`. **Select the existing Diaglob app**, not Create a new app. Internal app ID: `416524435457`; Partner ID: `5148778`. Compare the actual `client_id`, `embedded`, `application_url`, OAuth redirect URLs and scopes against Shopify Dev Dashboard.
2. The code repository intentionally does **not** contain an actual linked `shopify.app.toml`, so do not fabricate one with an invented client ID. Use the *real* file produced by `app config link`.
3. In the backend Python environment, set `SHOPIFY_CLIENT_ID` to the existing app's genuine Client ID (never an access token). Preview the safe patch:

   ```sh
   cd backend
   python -m app.shopify_compliance_config_prepare \
     --path /actual/path/shopify.app.toml \
     --expected-app-url 'ACTUAL_APPLICATION_URL_FROM_DASHBOARD' \
     --expected-mode standalone
   ```

   **Use `embedded` instead of `standalone` if and only if the Dev Dashboard states the app is embedded.** This tool refuses changes if OAuth/scopes/identity differ, and never creates the TOML or deploys the app.

4. If the tool returns `valid_local_config: true`, opt in to a local file change:

   ```sh
   python -m app.shopify_compliance_config_prepare \
     --path /actual/path/shopify.app.toml \
     --expected-app-url 'ACTUAL_APPLICATION_URL_FROM_DASHBOARD' \
     --expected-mode standalone --apply
   python -m app.shopify_app_config_audit \
     --path /actual/path/shopify.app.toml \
     --expected-app-url 'ACTUAL_APPLICATION_URL_FROM_DASHBOARD' \
     --expected-mode standalone
   ```

   The resulting config must subscribe to every topic **once** at this endpoint (the tool may add only a missing subset):

   ```toml
   [[webhooks.subscriptions]]
   compliance_topics = ["customers/data_request", "customers/redact", "shop/redact"]
   uri = "https://api.diaglob.tech/api/webhooks/shopify/compliance"
   ```

5. After independent checks and release authorization, run `shopify app config validate` and `shopify app deploy` **for that same existing app**. Confirm the **released** version in Dev Dashboard → Versions → Configuration → Webhooks lists the mandatory topics and correct HTTPS destination.
6. Confirm production `SHOPIFY_CLIENT_SECRET` matches the *same app's* API secret (never print it). Test valid signed synthetic deliveries (HTTP 2xx) and invalid signatures (HTTP 401) from a development store. Re-run Partner Dashboard automated checks.

## Still blocked after the automated checks turn green

- Actual privacy request handling: fulfillment within Shopify's required timeframe, exceptions for lawful retention, data held by subprocessors, and backups.
- Protected customer data review, pricing, app capabilities, reviewer walkthrough and integration E2E.
- Production deployment evidence, actual release identity, and a fresh Dev Dashboard result are necessary before declaring either failure fixed.

Official guidance:
- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/build/webhooks/subscribe
- https://shopify.dev/docs/apps/build/cli-for-apps/manage-app-config-files
