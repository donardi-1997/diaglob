# Paddle checkout environment routing (2026-10-11)

## Issue corrected

The DIAGLOB direct-signup checkout uses Paddle. Previously `frontend/src/pages/PlansPage.tsx` always initialized Paddle.js with `environment: "sandbox"` even though `backend/app/paddle_client.py` uses `PADDLE_ENVIRONMENT=production` to call the live Paddle API. A live API transaction ID cannot be redeemed in a sandbox frontend session.

## Safe fix — no live activation

The frontend now validates the client-side token and an explicit build-time `VITE_PADDLE_ENVIRONMENT` setting:

| `VITE_PADDLE_ENVIRONMENT` | Client-side token prefix | Result |
|---|---|---|
| omitted / `sandbox` | `test_` (valid token) | Initialize Paddle.js sandbox |
| omitted / `sandbox` | `live_` | **Block** checkout initialization |
| `production` | `live_` (valid token) | Initialize Paddle.js production |
| `production` | `test_` | **Block** checkout initialization |
| invalid value / invalid token | any | **Block** checkout initialization |

Paddle expects tokens matching `^(test|live)_[a-zA-Z0-9]{27}$`. Do **not** use a Paddle server API key as a client token. The actual token is never printed in browser logs.

**Importantly, this PR does not change `frontend/.env.production`, `PADDLE_ENVIRONMENT`, client tokens, AWS/production secrets, actual checkout URLs or paid-entitlement flags**. No live payments or real customer charges were attempted.

## Operator go-live verification (separate commercial approval required)

1. Check Lightsail's private `PADDLE_ENVIRONMENT` **without printing its API key**; it must be `sandbox` while testing and `production` only after commercial signoff.
2. Check the `PADDLE_API_KEY` environment matches the backend mode. Sandbox Paddle keys contain `_sdbx`; production keys don't. Never print the key. If unsure, validate against a read-only Paddle API endpoint.
3. For sandbox, `VITE_PADDLE_CLIENT_TOKEN` must contain a real test client token; leave `VITE_PADDLE_ENVIRONMENT` unset or `sandbox`. Complete no-charge sandbox test checkout and inspect webhook consumption.
4. For a later live launch, first confirm Paddle live-account approvals, webhook destination/signature secret, domain approval, and live price IDs; **only then** set `VITE_PADDLE_ENVIRONMENT=production` in the frontend **build environment**, and use the corresponding `live_` client token, with the backend `PADDLE_ENVIRONMENT=production` and matching live API key.
5. Rebuild/deploy frontend and run controlled operator-approved end-to-end checks. Avoid real charges until explicit approval.
6. Shopify App Store-originated installs and organizations identified as `billing_provider=shopify` continue to use hosted Shopify App Pricing, **never** Paddle checkout, regardless of this change.

Official sources:
- https://developer.paddle.com/paddle-js/about/client-side-tokens
- https://developer.paddle.com/sdks/libraries/paddle-js-wrapper
- https://developer.paddle.com/sdks/sandbox/
