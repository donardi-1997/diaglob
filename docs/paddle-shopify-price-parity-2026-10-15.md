# DIAGLOB — Paddle / direct app / Shopify price parity (2026-10-15)

## Approved commercial matrix for the direct SaaS app

| Plan | Monthly USD | Annual USD | Active stores per direct organization |
|---|---:|---:|---:|
| Starter | 19 | 190 | 1 |
| Growth | 49 | 490 | 2 |
| Pro | 99 | 990 | 3 |
| Scale | 199 | 1990 | 5 |

- All direct subscriptions (catalog, public checkout and upgrades/downgrades) support **1 or 12 months only**. Quarterly and semiannual plans have been removed before the first sale.
- All new merchant trials use **3 days**; existing already-started trial end timestamps must NOT be retroactively shortened.
- Each Paddle recurring price has a 3-day **free trial**. Confirm that all eight are actually configured in the correct Paddle account/environment.
- Price tax inclusivity is controlled in each Paddle price/account; confirm it separately. App list prices alone do not prove tax treatment.
- **Scale remains direct-only**. Shopify App Store public plan verification intentionally supports Starter, Growth and Pro.
- A DIAGLOB organization's multi-store allowance is NOT a Shopify multi-store subscription grant. Each Shopify shop is billed by Shopify; existing single-shop verification fails closed for unsupported multi-shop cases.

## Paddle price ID integration (received from vendor screenshots)

The eight `pri_...` identifiers are **public catalog identifiers, not API keys**.
They are now version-controlled in `backend/app/billing.py` as
`PADDLE_PRODUCTION_PRICE_IDS`, with the following plan/interval mapping:

| Plan / frequency | Expected USD | Live catalog Price ID | Optional deployment override |
|---|---:|---|---|
| Starter monthly | 19 | `pri_01m50gxt8wr6cqgndwk271zbs2` | `PADDLE_PRICE_STARTER_1M` |
| Starter annual | 190 | `pri_01m50gz7anwanpkww0sgp1f9nz` | `PADDLE_PRICE_STARTER_12M` |
| Growth monthly | 49 | `pri_01m50h13qwafmqfqcnsmykzrfz` | `PADDLE_PRICE_GROWTH_1M` |
| Growth annual | 490 | `pri_01m50h2054mvwjynacwrs1g122` | `PADDLE_PRICE_GROWTH_12M` |
| Pro monthly | 99 | `pri_01m50h3z0mtsjj4vnzs5c7z164` | `PADDLE_PRICE_PRO_1M` |
| Pro annual | 990 | `pri_01m50h4wa2m3tgbdy1q18448v0` | `PADDLE_PRICE_PRO_12M` |
| Scale monthly | 199 | `pri_01m50h5z54txa8zsepx3nfyr35` | `PADDLE_PRICE_SCALE_1M` |
| Scale annual | 1990 | `pri_01m50h6r57qvj1pr80czvjnev4` | `PADDLE_PRICE_SCALE_12M` |

**Resolution order:** explicit `PADDLE_PRICE_{PLAN}_{PERIOD}M` environment
value (or existing monthly legacy override), local CSV override if present,
then the reviewed catalog **only when `PADDLE_ENVIRONMENT=production`**.
If the environment is `sandbox` (the backend default), there is **no live-ID
fallback**. The ignored local `backend/paddle-period-prices.csv` is not committed
and existing local overrides may take precedence; clear stale values before
deploying. Do not copy these IDs into a sandbox account.

The screenshots identify Price IDs and their labels, but **do not verify Paddle
API environment, USD amounts, trial duration, tax handling or active status**.
All eight price objects still need to be checked against the actual vendor API
using the matching workspace and a secure API key (not committed to Git). Do not
activate checkout on unverified objects. `PADDLE_API_KEY`,
`PADDLE_WEBHOOK_SECRET` and `VITE_PADDLE_CLIENT_TOKEN` remain managed secrets
or deployment config. Price ID mapping alone does not configure the payment
provider, webhook endpoint or live checkout.

No subscriptions exist yet: the direct catalog, price lookup, proration and
checkout support **only 1M / 12M**. Any leftover 3M/6M environment variables
should be retired.

## Shopify App Pricing (different billing provider)

Shopify merchant subscriptions are charged ONLY through Shopify App Pricing and managed in Shopify Partner Dashboard. The backend validates verified plan handles against the operator-supplied `SHOPIFY_APP_PRICING_HANDLES_JSON`. Once actual Partner handles are known, configure the mapped `prices` in that JSON as follows:

- Starter: `EVERY_30_DAYS = "19.00"`, `ANNUAL = "190.00"`
- Growth: `EVERY_30_DAYS = "49.00"`, `ANNUAL = "490.00"`
- Pro: `EVERY_30_DAYS = "99.00"`, `ANNUAL = "990.00"`

Verify current Partner pricing BEFORE modifying `SHOPIFY_APP_PRICING_HANDLES_JSON`; never claim parity or grant access if Partner shows other amounts. Earlier Partner screenshots showed annual amounts different from the approved direct prices, so operator confirmation and update in Partner Dashboard are required. Shopify trial setting should be **3 days** and must be confirmed in Partner. Do not add Scale to the App Store contract. Never redirect Shopify App Store installations to Paddle.

## Validation / deployment

1. Apply/merge the existing **store-cap** branch before this stacked change (or retarget appropriately).
2. Run `cd backend && pytest -q tests/test_trial_service.py tests/test_billing.py tests/test_billing_checkout_periods.py tests/test_paddle_price_catalog.py tests/test_shopify_app_pricing.py tests/test_plan_store_caps.py`.
3. Run the frontend TypeScript build and verify that period selector offers only 1 month / 1 year.
4. Confirm new direct trial=3 days and confirm the store-activated trial and Paddle price trial cannot accidentally grant two sequential free periods.
5. Verify the eight catalog Price IDs in the actual Paddle production account, remove any stale environment/CSV price overrides, and test monthly/annual checkout for each direct plan plus signed Paddle webhooks. Confirm credentials and Paddle.js client token point to the same environment.
6. Align the annual amounts and trial settings in Shopify Partner, set verified `SHOPIFY_APP_PRICING_HANDLES_JSON`, and test Shopify plan approval/refusal/retry and developer store subscription lifecycle.
7. Verify tax-included behavior in BOTH channels independently. Do not assume Shopify and Paddle tax display semantics are the same.

**Deployment is not complete** until Paddle objects are checked against the provider API, Partner settings, environment credentials and end-to-end checkout evidence are verified. Price IDs have been recorded but no actual payment has been tested.
