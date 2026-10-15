# DIAGLOB — Shopify managed installation verification (2026-10-15)

## Verified from real Shopify CLI output (no credentials)

- Shopify app `gid://shopify/App/416524435457`, client ID matched to source.
- Active Shopify version: **diaglob-4** (2026-10-14 18:48:28).
- Shopify app is **embedded** and App Home is `https://api.diaglob.tech/api/shopify/embedded`.
- Local TOML has 8 Admin API scopes, GDPR compliance topics and no CLI configuration errors.
- `remoteApp.grantedScopes` in the captured CLI output lists **protected customer-data categories**. It does not establish installed-shop Admin API grants. Verify separately in Shopify Partners and the test shop.
- CLI output does **not** prove that version diaglob-4 has the exact current local config or that a test merchant installed it, completed billing, or authorized privacy webhooks.

## Architecture decision

**Use Shopify-managed installation and embedded App Bridge token exchange.** Do not enable legacy `SHOPIFY_OAUTH_FIRST_ENABLED` solely to satisfy a static compliance audit. The standalone flow is not the default strategy of the current app.

- The public legacy `/api/shopify/install` fails closed with 503 while disabled; no portal redirect before authorization.
- Added `POST /api/shopify/embedded/managed-install/verify`. A valid Shopify App Bridge ID token is checked server-side; Shopify issues a short-lived **online** access token for verification and the server compares Shopify's authenticated shop identity to the signed JWT shop.
- Verification returns only `shopify_installation_verified`, `diaglob_link_required`, and the canonical shop domain. Tokens and Shopify staff subjects are **not returned, persisted, or logged** by this new flow. There is no tenant, billing, customer data, store binding, or other mutation.
- This check is **not a substitute** for a permanent **expiring offline token + refresh** storage design needed for background Shopify Admin API operations.
- The previous embedded authorization still requires an explicit DIAGLOB store/membership linkage before accessing tenant data.
- Fresh Shopify-managed installs with no DIAGLOB CommerceConnection still need the merchant onboarding/claim flow completed. The standalone OAuth callback may not be reused unmodified.

## Review gates

1. Open **diaglob-4** in the Partner Dashboard and verify embedded/managed install configuration and all live OAuth grants; do not redeploy the TOML spec blindly.
2. Open the installed app from Shopify Admin on `diaglob-poc.myshopify.com`; verify fresh App Bridge ID token and the new proof route using real Shopify credentials, without writing customer data.
3. Implement and E2E-test tenant-safe merchant onboarding for first-time Shopify-managed installs using expiring offline tokens, refresh credentials, and explicit membership/store claims.
4. Prove removal/reinstallation, revoked scope, invalid signature, expired ID token, duplicate shops, reviewer account, and tenant/store isolation.
5. Complete App Pricing and billing 1.2.1/1.2.2. A passing isolated install proof is **not App Store approval**.

## References

- https://shopify.dev/docs/apps/build/authentication-authorization/implement-token-exchange
- https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens
- https://shopify.dev/docs/apps/build/authentication-authorization/cli-app-authentication

**Status: verification endpoint under PR review; App Store 2.3.1 = NEEDS LIVE REVIEW. No Shopify CLI deploy or Partner changes.**

## Implementation update — managed first installation

- `POST /api/shopify/embedded/managed-install/stage`: with a **fresh signed App Bridge ID token**, request an **expiring offline token** (`expiring=1`), verify actual shop identity and minimum required scopes. Encrypt access + refresh credentials at rest in an expiring, unclaimed `ShopifyPendingInstall`; return only a high-entropy ten-minute single-use code.
- Shopify embedded App Home displays the one-use code only after explicit user interaction, never in browser URLs or storage.
- In a separately authenticated DIAGLOB session, `https://diaglob.tech/shopify/install?managed=1` accepts the code, verifies the verified shop, then lets an authorized member choose/create a compatible store; `POST /api/stores/{store_id}/shopify/install/claim-code` binds only an eligible shopify-install tenant. A code cannot assign paid entitlements.
- Backend atomically moves encrypted access/refresh credentials and expiry fields into the authorized CommerceConnection and destroys pending ciphertext. Code replay, expiration and cross-tenant reassignment are rejected.
- Shopify Admin API clients now use refresh-token rotation when expiring offline tokens are near expiry. Legacy non-expiring credentials remain backward-compatible. Rotating tokens are committed to the DB before reuse.
- Alembic migration `d9e0f1a2b3c4` adds pending-install refresh/expiry metadata only. No secrets are included in revision source.

**Important:** This is a testable code path, not a claim of a successful live Shopify installation, approved App Store requirement, or live Shopify billing. Real Shopify-issued token exchange, permission grants, responsive UI and installation/reinstallation on the test store must all be verified.

### Merchant E2E checklist

1. Confirm app `DIAGLOB`, app ID `416524435457`, active version `diaglob-4`, managed install and eight operational scopes in active Shopify configuration. Do not deploy a new Shopify app or edit Partner versions unnecessarily.
2. From `diaglob-poc.myshopify.com` Shopify Admin, install/open the Diaglob app. Confirm App Bridge provides a current ID token; the embedded page reports installation verified.
3. Select **Generar código de instalación**. Copy the short-lived code, open Diaglob in a separate secure tab, sign up/login as an authorized owner/admin for an organization with Shopify onboarding and choose `/shopify/install?managed=1`. Paste the code (never add it to a URL).
4. Verify the shop domain comes from the Shopify grant and create/select the correct store. Complete claim. Confirm no Paddle charge or off-platform billing, then reopen Diaglob inside Shopify Admin.
5. Verify the embedded **Resumen, Productos, Pedidos** work only for linked staff. Verify unauthorized Shopify staff/another DIAGLOB tenant cannot read data.
6. Verify expired code, second redemption, token scope mismatch, denied exchange, malformed shop, uninstall/reinstall and changed DIAGLOB store permissions. Confirm access is revoked after uninstall.
7. Verify automatic refresh/rotation when a synthetic expiring token approaches expiry; conduct a safe real refresh test after an hour only on the development store, with no production order mutations.
8. Capture installation E2E video for Shopify App Review, noting App Pricing remains separately blocked.

### Sources
- https://shopify.dev/docs/apps/build/authentication-authorization/implement-token-exchange
- https://shopify.dev/docs/apps/build/authentication-authorization/access-tokens
