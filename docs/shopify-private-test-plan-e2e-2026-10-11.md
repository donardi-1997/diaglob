# Diaglob · No-charge Shopify App Pricing E2E

**Status: engineering prepared, NOT Partner-configured and NOT a live E2E pass.** No billing prices, entitlements or Shopify accounts were modified by this work.

## Confirmed Partner identifiers (operator-reported on 2026-10-11)

- Shopify Partner organization **DIAGLOB**, Partner org ID **5148778**.
- Existing Diaglob application numeric identifier **416524435457**.
- Operator reported **zero configured pricing plans; Shopify App Pricing disabled**.
- Do not assume the app's numeric dashboard ID is automatically the `gid://shopify/App/<id>` needed for `activeSubscription`. Verify using authenticated Partner API/GraphiQL and the existing app identity. Do not create a second app.

## Required external setup (authorized Partner owner, not performed)

1. Log in to the original DIAGLOB Partner organization and confirm the app's distribution is public-eligible. App Pricing might need an explicit opt-in; do not switch billing methods for existing paid merchants without checking legacy contracts.
2. Use **App distribution → All apps → Diaglob → Distribution → Manage listing → Published languages → Edit → Pricing content → Manage → Private plans**. Shopify documents a default USD 0 private test plan. If this is unavailable while Shopify App Pricing is disabled, follow the on-screen enablement/eligibility requirements first.
3. Restrict the private test plan to `diaglob-poc.myshopify.com`, but **only after** checking the shop is a development store under the eligible Partner organization. Do not include Bakatá. Do not create or publish the four proposed paid plans.
4. Under **Settings → Partner API clients**, an organization owner creates a client with **Manage apps** and saves the token securely. The store Admin API connector alone **does not** provide Partner API access. Never put credentials in PRs or chat.
5. Confirm the trusted app GID in the Partner API and `activeSubscription(appId:, shopId:)` shape. Verify `gid://shopify/Shop/<id>` from the OAuth-authenticated Shopify Admin token, not a URL parameter.
6. Install Diaglob on the approved development shop. Choose the authorized $0 private plan. Confirm redirect, interval and the Partner-reported contract. A private free plan may have a different shape from a no-charge copy of a paid plan; observe the actual response instead of inventing a paid price.
7. Test uninstall/reinstall, plan cancellation, duplicate callback and cross-organization checks. Do not run a real paid merchant charge or change production entitlements.

Shopify references:
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing/plans
- https://shopify.dev/docs/api/partner/latest/queries/activeSubscription
- https://shopify.dev/docs/api/partner/latest

## Safe owner-only diagnostics prepared in code

After an owner has independently verified `diaglob-poc.myshopify.com` eligibility and provisioned the actual Partner credentials, operators may optionally enable **only this diagnostic** by setting both server-side variables:

```dotenv
SHOPIFY_BILLING_TEST_PROBE_ENABLED=true
SHOPIFY_BILLING_TEST_SHOP_DOMAIN=diaglob-poc.myshopify.com
```

These variables are **NOT** configured by the code changes. Keep these commercial flags OFF:

```dotenv
SHOPIFY_BILLING_ENTITLEMENTS_ENABLED=false
SHOPIFY_BILLING_SCHEDULER_ENABLED=false
```

An authenticated Diaglob **organization owner** whose tenant has exactly one verified connected Shopify store can GET:

`/api/billing/shopify/development-probe`

The endpoint refuses requests unless the authorized tenant's installed store matches the configured test shop. It queries the trusted store identity, then fetches Partner `activeSubscription` read-only. It never accepts a caller-supplied store ID or handle and never creates an invoice, subscription, transaction, entitlement, proposal or evidence row.

Possible `status` values:

- `no_active_contract` — no Partner subscription found
- `zero_usd_contract_observed_no_grant` — active, single-item flat-rate USD 0 contract with a supported period
- `nonzero_contract_observed_no_grant` — active positive-price single-item contract, **not** a grant and not authorization to charge
- `unrecognized_contract_no_grant` — free-plan or unusual/multiple-item shape that requires human review

Every result has `commercial_entitlements_granted=false`, `applied=false` and `requires_review=true`. The response omits handles, store IDs, tokens, provider payloads and amounts. The diagnostics do **not** independently establish the Shopify development-store classification or paid billing eligibility.

When test operations are finished, disable `SHOPIFY_BILLING_TEST_PROBE_ENABLED`.

## GO/NO-GO

- Current state: **NO-GO for commercial charges and entitlements**.
- Technical gate: no real partner token, no approved app GID, no verified Partner test contract.
- Commercial gate: prices, per-store billing model and quota enforcement require explicit approval.
- Operations gate: hourly watch and alerting need independent verification of scheduled tick and incident delivery.
