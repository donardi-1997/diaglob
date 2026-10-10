# Shopify install handoff — DIAGLOB

Status: **first merchant-facing handoff implemented, not Shopify App Store certification**. PR #149.

## Implemented workflow

1. Merchant opens configured App URL `https://api.diaglob.tech/api/shopify/install?shop=<domain>.myshopify.com` (or development HTTPS equivalent). This is a **public hint** only: the domain is untrusted and grants no access.
2. Backend validates a bare canonical `.myshopify.com` hostname, enforces a fixed configured HTTPS `FRONTEND_URL`, and redirects HTTP 303 with `Cache-Control: no-store` to `https://diaglob.tech/shopify/install?shop=<domain>`. It **does not** query or write the DB, create an installation, issue OAuth state, or consume Shopify scopes.
3. Frontend route requires a valid DIAGLOB authenticated session (and `stores.write` to proceed); a user not logged in is sent to `/login` and returned to this exact local route. The post-auth return route is restricted to `/app/*` or `/shopify/install`; outside locations stay blocked.
4. The merchant selects an existing active store within the current DIAGLOB organization. Stores configured for another Shopify domain are filtered out. A merchant with no existing stores must create one in `/app/stores`.
5. Only an explicit confirmation POSTs to the existing protected `/api/stores/{store_id}/shopify/connect`. This endpoint authorizes `stores.write`, verifies organization ownership, ensures no duplicate Shopify binding and creates short-lived unique OAuth state tied to the selected store.
6. Frontend validates the returned OAuth URL is an HTTPS `/admin/oauth/authorize` endpoint on the **exact requested shop**, with `state` and `client_id`. Only then does it navigate to Shopify's permissions screen. Shopify's callback still verifies HMAC and atomically consumes the matching tenant/store-bound state before exchanging any token.

## Deliberate security limits

- `shop` from initial App URL is **not authenticated** by this handoff. Neither the selected store nor merchant identity is established from the URL alone. Linking occurs only after a privileged DIAGLOB user selects their store, and Shopify authorization succeeds.
- The entrypoint is **not a complete Shopify-managed embedded installation**. If this app is embedded, Shopify App Bridge session tokens/token exchange and Partner Dashboard settings must be implemented and tested separately. Do not treat a legacy OAuth redirect as proof of approved embedded architecture.
- No automatic store creation, generic `return_to`, query-based organization IDs, credentials, access tokens, recurring charges, or real order/customer operations.
- Configuration assumes `FRONTEND_URL=https://diaglob.tech` (or other controlled HTTPS frontend origin). Non-HTTPS public origins and path/query-based frontend URLs fail closed.
- No public app launch may grant features beyond the authenticated tenant's role, approved scopes, verified Shopify billing state, protected customer data requirements or legal privacy controls.

## Tests and E2E evidence needed

- Backend: `backend/tests/test_shopify_install_handoff.py`, API route snapshot.
- Frontend: `frontend/tests/shopify-install.test.ts`, `frontend/tests/routing.test.ts`, TypeScript build.
- Actual dev-store E2E still needed: configure existing app's **App URL** and **allowed redirect URI** and confirm actual install → login → merchant selects existing store → Shopify OAuth approval → DIAGLOB connected UI; test refusal for wrong domain, cross-organization store, revoked token, retry/reinstall/uninstall.
- To verify Shopify App Store architecture, determine whether App URL is opened within Shopify Admin as an embedded app. If embedded, implement App Bridge authorization and prevent iframe/login problems. Confirm correct setup with the existing Partner Dashboard without creating a second app.

Related: `docs/shopify-oauth-callback-hardening-2026-10-10.md`, `docs/shopify-security-scopes-review-2026-10-10.md`.

Reference: https://shopify.dev/docs/apps/build/authentication-authorization
