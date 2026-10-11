# Diaglob · Shopify-hosted billing and guarded entitlement application (2026-10-11)

## Architecture and provider of record

- **Shopify App Store merchants:** Shopify App Pricing, merchant plan choice and charges hosted by Shopify. Do not call legacy `appSubscriptionCreate` or Paddle for these accounts.
- **Direct Diaglob accounts:** Existing Paddle checkout and webhooks remain unchanged.
- Bakatá is the **commerce OAuth E2E pilot**; do not use it as a Diaglob application-billing sandbox.

## Delivered integration

### Hosted pricing navigation

`GET /api/billing/shopify/hosted-plan-selection` requires owner/manager and a verified, single Shopify-managed tenant. It confirms the OAuth-installed store identity through Shopify Admin API and constructs a Shopify Admin hosted pricing URL with operator-configured `SHOPIFY_APP_STORE_HANDLE`. The shop and app handle can never be taken from a client-supplied redirect or query parameter. This endpoint does not charge merchants or change plans.

`GET /api/billing/shopify/capabilities` exposes no credentials and returns only provider UX availability booleans. The Shopify billing workspace displays the hosted-plan link; it never mounts Paddle checkout.

### Explicit, replay-safe application of an actual paid subscription

`POST /api/billing/shopify/transition-proposals/{review_id}/apply`:
1. Owner-only and **disabled by default** (requires exactly `SHOPIFY_BILLING_ENTITLEMENTS_ENABLED=true`, set only after launch authorization).
2. Requires a previously staged `pending_review` with latest ≤10-minute-old tenant evidence, intact original installation identity, a single merchant binding and no legacy Paddle references.
3. **Recontacts** Shopify Admin for the canonical shop GID, and Partner API for a currently active subscription. Validates the operator-approved item handle, billing interval and USD fixed amount against `SHOPIFY_APP_PRICING_HANDLES_JSON`. Missing, changed, canceled-scheduled, inactive, mixed or ambiguous contracts cannot authorize the change.
4. Locks the organization/review/shop binding/store and checks **all** installation/tenant/plan/evidence fields again after provider I/O. Concurrent changes and replay are rejected.
5. In one DB transaction, sets `Organization.plan`, `billing_period_months` and `subscription_status=active`, and closes the staged review as `applied`. Existing Paddle references are prohibited. Replaying an already applied review is an idempotent no-op if the current plan still matches.
6. No Shopify order, charge, subscription creation, cancellation, invoice or customer message occurs in this route.

## Remaining live gates — NOT approved by code merge alone

- Shopify Partner owner must confirm the **existing Diaglob app identity**, approve final public/private plan prices, test intervals/handles and explicitly set protected Partner credentials. The price catalog must match live Shopify amounts. **Never** enter a merchant subscription amount in a UI to authorize a grant.
- Validate hosted plan selection, welcome return redirect, fresh verification, installment/reinstall, upgrade/downgrade and replay in a development shop owned by the appropriate Partner organization at no charge. Do not switch the user's Shopify connector away from Bakatá.
- **Lifecycle gap:** Shopify App Pricing does **not** send billing change webhooks after April 28, 2026. Subscription cancellation/freeze can happen outside redirect. Until a separate periodic Partner state checker plus audited access revocation is implemented and approved, enablement must remain OFF. The apply endpoint refuses absent or cancellation-scheduled subscriptions but cannot by itself revoke an *older* active grant.
- Free plans and no-charge development subscriptions require a documented, separate price-verification policy; current strict positive-price grant path deliberately rejects $0 as a paid entitlement.
- Multi-merchant organizations remain fail closed. Decide whether Diaglob pricing is per Shopify shop or per Diaglob organization before opening this gate.
- Privacy/compliance and Shopify App Store review remain independent P0 gates; see #148.

## Operational environment (never commit values)

- `SHOPIFY_PARTNER_ORG_ID`
- `SHOPIFY_PARTNER_APP_GID`
- `SHOPIFY_PARTNER_ACCESS_TOKEN`
- `SHOPIFY_APP_PRICING_HANDLES_JSON` (actual plan handle → plan/interval/exact approved amount)
- `SHOPIFY_APP_STORE_HANDLE` (actual Shopify app listing handle)
- `SHOPIFY_BILLING_ENTITLEMENTS_ENABLED` (default **OFF**)

## Rollout

1. Review CI/backend/frontend/tenancy negative tests and exact release SHA.
2. Confirm successful Shopify App Pricing plan setup and live Partner API responses in authorized **development-only** environment.
3. Build and verify subscription cancellation/freeze background enforcement and approved cross-shop policy **before enabling any production paid entitlement writes**.
4. Explicit operator go/no-go for enabling production, with rollback and monitoring.
5. Only then set the gate and complete merchant billing E2E.

Source: https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
