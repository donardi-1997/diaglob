# Shopify OAuth-first installation — DIAGLOB (2026-10-11)

**Code readiness only; Partner Dashboard / test shop E2E NOT performed.**

References:
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
- https://shopify.dev/docs/apps/build/authentication-authorization
- https://shopify.dev/docs/apps/build/authentication-authorization/app-installation

## Why

Shopify App Store requirement 2.3.2 requires authentication before merchant-facing setup UI, including after reinstall. DIAGLOB's old `/api/shopify/install` forwarded to a DIAGLOB login/store selector before starting OAuth. That flow is unsuitable for a standalone public installation.

## Implemented flow

1. Shopify-owned app install sends `GET https://api.diaglob.tech/api/shopify/install?shop=...`. The backend validates a strict canonical domain, writes an expiring, unbound OAuth state, and 303 redirects immediately to Shopify's authorization endpoint. **No DIAGLOB account, organization, store selection or billable plan is involved.**
2. Shopify returns an HMAC-signed callback. The backend validates HMAC, domain and one-time state; atomically consumes state **before** exchanging the code, then verifies the shop identity using authenticated Shopify Admin GraphQL. If Shopify rejects the grant, nothing is linked to DIAGLOB.
3. The verified Shopify token is encrypted in a short-lived, unbound `shopify_pending_installs` database record; the browser receives a 20-minute Secure HttpOnly SameSite=Lax cookie containing a random grant secret (not a Shopify token), and goes to `https://diaglob.tech/shopify/install?authorized=1`.
4. Merchant logs into/registers for DIAGLOB, chooses a **pre-existing active authorized** DIAGLOB store, and explicitly confirms binding. `GET /api/shopify/install/pending` shows the verified shop from the cookie; `POST /api/stores/{store_id}/shopify/install/claim` checks role/permissions, organization, store assignment and conflicting connections. The grant is consumed once; ciphertext is moved to an authorized CommerceConnection, never a client response.
5. No plan handle, public shop hint, onboarding URL or grant cookie alone grants commercial access. Existing DIAGLOB-initiated store connection and reauth paths remain separate.

## Controlled rollout

- Default: `SHOPIFY_OAUTH_FIRST_ENABLED=false`. The public install endpoint now responds **503 fail-closed**, never redirects to a DIAGLOB portal before OAuth. The App Store install remains **unavailable until a supported Shopify mode is independently verified and activated**, so requirement 2.3.1 is **NEEDS LIVE REVIEW**, not PASS. Keep OFF for the existing embedded/managed installation until the correct ID-token + token-exchange onboarding is confirmed; do not turn on the authorization-code grant simply to silence the audit.
- Migrate production DB to Alembic head `f9a0b1c2d3e4` before enabling. Roll back the feature flag immediately if migration/verification fail. Do not downgrade a table containing pending merchant tokens without an approved disposal plan.
- Confirm `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, `SHOPIFY_REDIRECT_URI=https://api.diaglob.tech/api/shopify/callback`, frontend `FRONTEND_URL=https://diaglob.tech`, encryption key, HTTPS and proper CORS with credentials on the exact frontend origin. **Do not put secrets in GitHub or logs.**
- If the actual Shopify app is **embedded/managed installation**, the correct long-term implementation is App Bridge ID-token validation and Shopify token exchange. This authorization-code flow must NOT be enabled on an embedded/managed installation without verifying supported architecture. No Shopify app config is invented/committed here.
- Ensure app-level mandatory compliance webhooks and actual privacy fulfillment separately; this PR does not close those requirements.
- Create/reuse authorized synthetic DIAGLOB store in the reviewer organization after Shopify OAuth. Never auto-create a tenant based solely on `shop`; never use Bakatá for billing review.

## Required E2E on diaglob-poc.myshopify.com

**Architecture prerequisite:** Shopify declares DIAGLOB as embedded in `shopify.app.toml`; Shopify-managed installation is the default. First verify active Partner app configuration and implement/confirm ID-token exchange for managed installation. A standalone authorization-code grant is only valid if that distribution mode is supported for the active app. The gate must not be enabled blindly.

- [ ] App initiated on a Shopify-owned surface; OAuth grant screen before any DIAGLOB UI.
- [ ] Callback verifies signed shop identity and returns DIAGLOB UI even when no DIAGLOB account existed previously.
- [ ] Merchant signs in/registers and binds exactly one eligible store; app appears as installed in Shopify admin; catalog sync read-only works.
- [ ] Expired, used, mismatched-state/HMAC/shop/token and grant-cookie replay rejected.
- [ ] Restricted user cannot bind another member's store; duplicate domain or different linked provider rejected.
- [ ] OAuth reinstall / revoked installation repeats Shopify authorization and reclaims only through tenant-authorized association.
- [ ] Billing provider provenance remains pending or Shopify-verified without activating paid entitlements.
- [ ] Verify whether Shopify disallows a fresh OAuth redirect for already-installed apps; test idempotent reinstallation and retry.
- [ ] Deploy original app version, verify actual OAuth URLs and screenshot/record English review using real UI.
- [ ] Validate password/login, reviewer store data, privacy/terms/support pages, and production monitoring.

**NO-GO** until Partner app configuration and real merchant E2E confirm the mode and install path.

## Billing provenance hardening (2026-10-12)

Pending Shopify OAuth credentials are *not* commercial entitlements. Before claiming an installation, DIAGLOB now rejects direct/Paddle organizations even if their historical onboarding channel still says `shopify_install`, and refuses fresh claims with legacy customer/subscription/price references, a paid non-Shopify plan or a pending non-Shopify upgrade. Eligible new tenants must have pending Shopify onboarding with no legacy billing association, or already have verified `billing_provider=shopify` for a legitimate reinstall. Ineligible claims must leave the OAuth grant unconsumed and create no connection. This guards against mixed-provider billing; it does not turn on App Pricing or establish Partner plan approval.
