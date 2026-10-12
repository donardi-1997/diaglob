# Shopify Meta Pixel — verified prelaunch gate, 2026-10-11

## Verified production baseline

- PR #202 (per-store Pixel settings) deployed.
- PR #204 (staged Web Pixel SDK + inert GraphQL provisioning) deploy #38191212011 succeeded.
- **No Shopify CLI-generated extension UID** in this repository. No released Partner app extension, no confirmed `write_pixels` / `read_customer_events` on a connected Diaglob POC installation.
- No collector endpoint deployed at `/api/web-pixels/collect`, no per-tenant CAPI credentials, no Meta Events Manager receipt.
- Consequently **NO real Meta Pixel/CAPI events are active or verified**. Flags stay OFF and stores not allowlisted. Never infer merchant consent or API permissions.

## Corrections in this follow-up

1. `webPixelCreate` now sends a **JSON object** in `WebPixelInput.settings`, matching Shopify 2026-07 GraphQL docs, instead of sending JSON serialized as a string.
2. `GET /api/stores/{store_id}/meta-pixel/verify-remote` performs a read-only Shopify Admin query by known WebPixel GID, validates remote `pixelId`, `sourceId`, `trackingEnabled=false` and collector URL, fails closed and never leaks token/settings. The UI explicitly says **verified but inactive**. Requires normal tenant/store permission plus a dev-store allowlist.
3. For `checkout_completed` only, the browser event dedup ID is `shopify:order:<id>` when Shopify provides `checkout.order.id`, allowing matching to the HMAC-verified `orders/create` payload later. Otherwise retain `shopify:<event.id>`. **Neither ID nor unauthenticated browser data proves a sale or consent.**
4. Missing checkout monetary values are omitted, not silently treated as amount 0.

## Release acceptance, not yet checked

- Use **existing Diaglob Shopify app** in Shopify Partner/Dev Dashboard. Link locally using Shopify CLI: `shopify app config link`. Verify existing app/client ID against Partner record; no second app.
- Generate extension: `shopify app generate extension --template web_pixel --name diaglob-meta-pixel`. Copy `shopify/web-pixel-staging/src` into the CLI-generated extension, retaining the Shopify-generated UID in the real `shopify.extension.toml`.
- Apply `shopify/web-pixel-staging/shopify.extension.toml.template` settings to the generated TOML; ensure `runtime_context=strict` and customer privacy. Confirm `write_pixels,read_customer_events` approved and updated in both config and installed dev store; OAuth reauthorization must preserve merchant consent.
- `shopify app deploy --no-release` first. Inspect preview and app ownership. Only publish/release after privacy/security review and affected installations assessed.
- Only for `diaglob-poc.myshopify.com`, after release: explicitly allowlist and set `META_WEB_PIXEL_SHOPIFY_PROVISION_ENABLED=true` and `META_WEB_PIXEL_EXTENSION_DEPLOYED=true`. Confirm `webPixelCreate` yields a GID and `verify-remote` returns `VERIFIED_INERT`. It still **does not emit events**.
- Implement separate privacy-respecting collector and merchant-owned per-store Meta CAPI credential storage before switching **any** `trackingEnabled` flag. A public `source_id` is NOT authentication. Do not forward untrusted/browser-reported Purchase directly to CAPI or treat it as a confirmed order. Only Shopify-HMAC-verified orders can establish sale authenticity; marketing consent must be verified separately. Do not reuse Diaglob acquisition Pixel.
- Test POC in Shopify Customer events and Meta Events Manager: denied/granted consent, two shops/tenants, duplicate source detection (especially Shopify Facebook & Instagram app), checkout sandbox only, consistent event IDs, storefront/checkout, uninstall/reinstall, zero PII leakage.

## Go/no-go

**App extension code and deployment guard:** integrated. **Real Meta tracking:** NO-GO due Shopify Partner CLI/extension app state and Meta token/privacy/E2E gates.

Shopify references:
- https://shopify.dev/docs/apps/build/marketing/build-web-pixels
- https://shopify.dev/docs/api/admin-graphql/2026-07/mutations/webPixelCreate
- https://shopify.dev/docs/api/admin-graphql/latest/queries/webPixel
- https://shopify.dev/docs/api/web-pixels-api/pixel-privacy
