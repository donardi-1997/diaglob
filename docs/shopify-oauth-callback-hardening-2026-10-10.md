# Shopify OAuth callback hardening and installation E2E boundary

Status: **implemented callback safety slice**; **not a complete Shopify-owned install flow**. PR #149.

## Code now implemented

- `backend/app/services/shopify_oauth_callback_validation.py` rejects absent required parameters, repeated query keys (including security-sensitive `hmac`, `shop`, `state`, `code`), invalid characters, control chars and excessive query/value size before HMAC or token exchange.
- `GET /api/shopify/callback` caps raw query at 4096 bytes **before** creating a parsed query set; then passes the unique parameter mapping to the existing `verify_shopify_hmac` mechanism.
- `backend/app/services/shopify_service.py` atomically claims a matching, unused, unexpired Shopify OAuth state in SQL with conditional UPDATE, commits before network token exchange, and refuses reuse. This prevents parallel callbacks from both exchanging a token using the same state.
- A transient Shopify token-exchange failure consumes the state deliberately. Merchant must re-initiate OAuth; retries with the same state do not authorize duplicate exchange.
- Regression files: `backend/tests/test_shopify_oauth_callback_validation.py` and `backend/tests/test_shopify_oauth_state_claim.py`. Both use synthetic values and do not contact Shopify.

## Remaining installation E2E blockers

1. The current OAuth entry point is `POST /api/stores/{store_id}/shopify/connect` behind DIAGLOB `stores.write` membership. It assumes an already authenticated DIAGLOB user, organization and store. A Shopify-initiated installation URL with a `shop` parameter is **not implemented as an authenticated installation journey**. Never link a shop to an arbitrary organization based on shop URL or signed callback alone.
2. Resolve existing app distribution (embedded vs standalone) in Shopify Partner Dashboard; build a secure bootstrap from Shopify-owned install to trusted logged-in DIAGLOB organization/store or Shopify App Bridge token exchange as appropriate. **Do not make a bare public GET URL that claims the shop solely from untrusted `shop`.**
3. Verify Shopify app settings (allowed redirect URI exact match, mandatory webhooks, scopes, app URL, install URL), HTTPS domain, and reviewer account using a development shop. Distinguish Partner-dashboard/app setting evidence from repository code.
4. E2E must demonstrate install → OAuth HMAC + one-time state → trusted shop identity → first usable UI → reconnect/uninstall/reinstall and revocation.
5. Uninstall webhook should revoke/disable connection, suppress scheduled syncs, and preserve legitimate privacy receipts without enabling retention-exempt claims. Confirm webhook subscription registration for compliance topics.
6. Do not request unrestricted customer/order data or bypass Shopify Checkout. Public scope requests and pricing/entitlements remain gated under Shopify approval and owner configuration.

## Verification requirements

The exact final HEAD SHA must have green backend tests, Ruff and route contract. Run synthetic concurrency/replay/oversized-query tests and a development-store OAuth trace; no production tokens or customer data in CI logs. Do not claim E2E from a mocked callback test.

References:
- https://shopify.dev/docs/apps/build/authentication-authorization/authenticate-standalone-apps
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
- docs/shopify-security-scopes-review-2026-10-10.md
