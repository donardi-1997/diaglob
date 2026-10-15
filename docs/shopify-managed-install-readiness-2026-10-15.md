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
