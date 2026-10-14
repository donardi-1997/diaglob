# Shopify embedded app authentication audit — 2026-10-14

Status: **confirmed implementation gap; migration required**. This is a read-only audit, not a certification of runtime behavior.

## Code inspected

- `shopify.app.toml`: `embedded = true` and application URL is `https://api.diaglob.tech`.
- `frontend/index.html`: no Shopify App Bridge CDN script and no `shopify-api-key` meta tag.
- `frontend/src/main.tsx`: boots the generic React/Cognito application without Shopify App Bridge initialization or an embedded-session bootstrap.
- `frontend/src/pages/ShopifyInstallPage.tsx`: merchant OAuth claim/create-store flow; this does not establish a Shopify ID token for all subsequent embedded requests.
- `backend/app/api/auth.py`: user provisioning and Cognito access-token validation; Cognito bearer tokens are not Shopify ID tokens.
- `backend/app/services/shopify_public_install.py`: signed OAuth state and encrypted access token; Shopify API access tokens are not user-authentication ID tokens.

## Required implementation plan

1. Resolve the real **App Home** URL and ensure Shopify iframe requests serve HTML, not an API-only JSON/redirect or Cognito-only login.
2. Add the **current App Bridge CDN script**, API key meta tag and appropriate frame/security policy to the *embedded-only* page HTML. Do not copy credentials from an example app.
3. In the embedded UI, obtain a fresh Shopify ID token through App Bridge and send it in `Authorization: Bearer` to dedicated backend endpoints. Do not store an ID token as a long-lived credential or confuse it with an Admin API token.
4. FastAPI verifies signature using the app secret, JWT algorithm, expiration/not-before, issuer/destination alignment, audience (client ID), and user subject. Enforce shop-to-tenant installation binding **after** verification and explicit local authorization; a valid Shopify token alone must never authorize an unrelated Diaglob tenant.
5. Integrate Shopify token exchange as applicable without exposing store tokens to the browser. Keep direct Diaglob/Cognito auth separately and test both login contexts.
6. Add unit tests for expired, future, wrong-audience, wrong-shop, bad-signature and cross-tenant tokens plus browser E2E inside Shopify Admin.
7. Deploy first to a development shop, validate App Bridge script and authenticated requests in Network/Shopify checks, then launch only after functional review.

## Current blockers

The generic frontend is separate from the configured Shopify app URL; integration cannot be completed safely by inserting a script into `frontend/index.html` alone. Confirm actual reverse-proxy/App Home routing, dedicated embedded entrypoint, and selected Shopify store before modifying authentication globally.

## References

- https://shopify.dev/docs/api/app-home/latest/apis
- https://shopify.dev/docs/apps/build/authentication-authorization/id-tokens
- https://shopify.dev/docs/apps/build/authentication-authorization/implement-token-exchange

**Do not mark Shopify's embedded-app/session-token checks completed until live validation passes.**
