# Shopify Partner — pricing setup handoff for Diaglob (2026-10-11)

## Status and authority
This is a **draft setup specification**, not price approval or evidence that public plans exist in Shopify. The Shopify storefront connector does not grant access to the organization's Partner Dashboard. The AWS production deployment audit on Oct 11 confirmed the five `SHOPIFY_PARTNER_*` / handle configuration keys were missing, and both entitlement and scheduler gates were off. Do not activate live paid contracts without merchant consent and owner approval.

Shopify official:
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing/plans
- https://shopify.dev/docs/api/partner/latest

## Shopify App Store review catalog

For the Shopify App Store review path, DIAGLOB exposes exactly **three public tiers**. Scale remains a direct/Paddle or future enterprise tier and must not be created as a public Shopify plan.

| Shopify plan | Monthly USD | Annual USD | Free trial | Billing periods |
|---|---:|---:|---:|---|
| Starter | 19.00 | 190.00 | 3 days | Monthly / Annual |
| Growth | 49.00 | 490.00 | 3 days | Monthly / Annual |
| Pro | 99.00 | 990.00 | 3 days | Monthly / Annual |

These prices are the current DIAGLOB review target from `docs/shopify-commercial-pricing-review-2026-10-10.md`; Shopify Partner remains the billing authority. Do **not** create a Scale public plan, a 3-month plan or a 6-month plan in Shopify.

Do **not** claim Shopify App Store multi-store allowances of 2, 5 or 10 at launch. The existing product global organization limits reflect historical direct SaaS tiers; the Shopify App Pricing reconciliation deliberately rejects multi-installation tenants. Never promise unlimited AI calls or usage-billed overages: live quotas and marginal inference costs need evidence.

## Partner operator workflow (not completed)

1. Sign in to the **original Diaglob Partner organization**, not the merchant store. Partner Dashboard > **App distribution > All apps > Diaglob > Distribution > Shopify App Store listing > Manage listing > Published languages > Edit > Pricing content > Manage**. Confirm whether the existing app can opt into Shopify App Pricing and if its distribution is public/draft.
2. Check the approved app, organization numeric ID and `shopify.app.toml` app handle. Don't create a duplicate Diaglob app or publish a new listing as a workaround.
3. Ask the product owner to approve actual prices, annual discounts, trial, feature copy, merchant support and any multi-store policy before creating **public** plans. If only connectivity needs testing first, Shopify offers a private no-charge test plan and development stores can test eligible paid plans for free.
4. Create exactly three public plans — Starter, Growth and Pro — each with **3 free-trial days** and monthly + yearly pricing. Record the **actual Partner plan and subscription item handles** returned by the active contract; don't guess handles from the display title. Do not create Scale or 3/6-month Shopify billing periods.
9. Configure each plan's welcome/redirection link to the DIAGLOB billing workspace (`/app/plans`). Shopify appends `plan_handle` (and, for external links, `shop`). DIAGLOB treats those values only as a signal to re-query Shopify; they never authorize a plan.
5. Under Partner Dashboard > **Settings > Partner API clients**, an organization owner creates a new least-privileged API client with **Manage apps** permission; record the token in an approved secret store, never Git, chat or PR text. Make sure the `gid://shopify/App/<id>` used by `activeSubscription` actually belongs to this app and matches the existing verified OAuth client identity.
6. Confirm `diaglob-poc.myshopify.com` is a Shopify development store in an eligible Partner organization before selecting plans; Bakatá is the ecommerce OAuth pilot, not a billing sandbox.
7. On the development store, authorize Diaglob; select a draft or private test plan; confirm the Shopify redirect and then query Partner API `activeSubscription(appId:, shopId:)` against its **Admin-verified Shop GID**. A zero effective recurring price is *not* commercial entitlement proof.
8. Validate monthly, yearly, cancellation, upgrade/downgrade, trial, reinstall and unknown-plan scenarios, plus cross-tenant prevention and Paddle isolation.
9. Configure the production `SHOPIFY_PARTNER_ORG_ID`, `SHOPIFY_PARTNER_APP_GID`, `SHOPIFY_PARTNER_ACCESS_TOKEN`, `SHOPIFY_APP_PRICING_HANDLES_JSON` and `SHOPIFY_APP_STORE_HANDLE` by approved secure operator access. First exercise **read-only** verification with both gates OFF.
10. Only after privacy and commercial approval, turn on `SHOPIFY_BILLING_ENTITLEMENTS_ENABLED` and `SHOPIFY_BILLING_SCHEDULER_ENABLED` in a controlled launch, with rollback and alarms confirmed.

## Operator catalog schema

Existing single-period handles remain supported:

```json
{
  "actual-monthly-handle": {
    "plan": "starter",
    "interval": "EVERY_30_DAYS",
    "amount_usd": "19.00"
  },
  "actual-annual-handle": {
    "plan": "starter",
    "interval": "ANNUAL",
    "amount_usd": "190.00"
  }
}
```

If Shopify produces the **same item handle** for monthly and yearly billing, use the new interval-aware schema to avoid a duplicate JSON key:

```json
{
  "actual-shared-handle": {
    "plan": "starter",
    "prices": {
      "EVERY_30_DAYS": "19.00",
      "ANNUAL": "190.00"
    }
  }
}
```

Both snippets use illustrative handle names and **unapproved example prices**. They are *not* production-ready configuration. The server verifies the Partner API subscription billing period and its exact positive USD amount before entitlement activation. Malformed/zero/unknown prices, unapproved intervals and mixed old/new schema fail closed. Never put `SHOPIFY_PARTNER_ACCESS_TOKEN` in this document.

## Known blocker
There is **no authenticated Partner Dashboard API/browser integration** in the currently connected Shopify store tool. A store Admin API session can't administer the Partner organization or create Partner API credentials. Live Partner App Pricing operations require authorized owner access; no Shopify bills were created in this work.
