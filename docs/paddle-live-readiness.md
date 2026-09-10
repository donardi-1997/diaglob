# Paddle live readiness

Diaglob keeps Paddle sandbox and live configuration separate. The application must remain in sandbox until the Paddle live account, domain, catalog, webhook and credentials are ready.

## Backend

Set these in `/etc/diaglob/diaglob.env` for live mode:

- `PADDLE_ENVIRONMENT=production`
- `PADDLE_API_KEY=<pdl_live_...>`
- `PADDLE_WEBHOOK_SECRET=<live notification destination secret>`
- `PADDLE_PRICE_STARTER_1M`, `PADDLE_PRICE_STARTER_3M`, `PADDLE_PRICE_STARTER_6M`, `PADDLE_PRICE_STARTER_12M`
- the equivalent `PADDLE_PRICE_GROWTH_*`, `PADDLE_PRICE_PRO_*`, and `PADDLE_PRICE_SCALE_*` variables
- `PADDLE_PRICE_AI_1000`, `PADDLE_PRICE_AI_5000`, `PADDLE_PRICE_AI_10000`

Live mode intentionally does not fall back to repository CSV price IDs. Every live price ID must be configured explicitly.

## Frontend

The Vite build needs:

- `VITE_PADDLE_CLIENT_TOKEN=<live_...>`
- optionally `VITE_PADDLE_ENVIRONMENT=production`

If `VITE_PADDLE_ENVIRONMENT` is omitted, Diaglob infers the environment from the token prefix. A `test_` token maps to sandbox and a `live_` token maps to live. Explicit mismatches are rejected before Paddle initializes.

For sandbox, use a `test_...` client-side token. For live, use a `live_...` token. Never expose `PADDLE_API_KEY` in Vite/frontend variables.

## Paddle dashboard cutover

1. Finish Paddle live account approval and domain verification for `diaglob.tech`.
2. Recreate all subscription prices and AI package prices in the live catalog.
3. Create the live notification destination pointing to `https://api.diaglob.tech/api/billing/webhook`.
4. Copy the live webhook secret and live price IDs into production configuration.
5. Create a live client-side token and make it available to the frontend build.
6. Set `PADDLE_ENVIRONMENT=production` only when all live values are present.
7. Rebuild the frontend after changing any `VITE_*` variable; Vite embeds these values at build time.
8. Perform a controlled real Starter purchase and verify the full transaction -> webhook -> subscription -> organization-plan flow.
9. Test an upgrade, cancellation, and one AI package purchase before opening sales broadly.

## Safety behavior

- Invalid Paddle environment values fail closed.
- Modern sandbox API keys cannot be used with the production API and modern live keys cannot be used with sandbox.
- Frontend `test_` and `live_` tokens are checked against the selected environment.
- API requests include `Paddle-Version: 1`.
- Live price resolution requires explicit environment variables.
