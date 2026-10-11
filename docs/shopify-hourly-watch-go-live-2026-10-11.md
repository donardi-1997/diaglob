# Diaglob · Shopify App Pricing: audit, scheduled monitoring and launch gates

## Verified 2026-10-11

- AWS account `765761474007`, region `us-east-2`: Lightsail `diaglob-prod` running. No SSM-managed nodes, EventBridge Diaglob billing schedule, or relevant SSM parameters/Secrets Manager names in the listing. **This does not mean Shopify secrets are absent from `/etc/diaglob/diaglob.env`.**
- GitHub Actions production deployment succeeded for merged PR #177, commit `3aa2660624a00be15884f40c8ae6d89e1558a5f3`, run #38140687616 (Validate, Deploy, Notify all succeeded).
- The actual Diaglob Shopify Partner application identifiers and approved plan prices are **not** available through the accessible Shopify storefront connector. No Shopify Partner Dashboard changes or authenticated merchant billing E2E were performed.
- Shopify says development stores can subscribe at zero charge. Such contracts **must not** authorize commercial paid access in Diaglob; synthetic negative tests protect that invariant.

## New automatic audit & scheduler

`.github/workflows/shopify-billing-hourly.yml` runs every hour (minute 17 UTC), and can also be triggered manually by a permitted GitHub operator. It:

1. Connects to the **existing** deployment SSH target and existing GitHub Actions production secrets, without creating an AWS resource or saving keys in the repository.
2. Reads the server environment file under `sudo` and prints only **present/missing** for Partner configuration keys, never their values.
3. Requires both `SHOPIFY_BILLING_ENTITLEMENTS_ENABLED=true` **and** new independent `SHOPIFY_BILLING_SCHEDULER_ENABLED=true`. Until both are set, the action skips subscription API calls and billing DB writes successfully. The latter flag is intentionally **not** set by this change.
4. If explicitly authorized, verifies required Partner configuration is present, then invokes `python -m app.shopify_billing_recheck --page-size 50 --max-pages 1000` on production. The existing command scans all eligible tenants and returns a failure code if any check fails or is truncated.
5. Uses GitHub Actions concurrency control to prevent overlapping billing watchers. A failed GitHub run triggers a Telegram alert using the **already used** GitHub repository secrets. Never logs access tokens, shop domains or Partner API responses.

**No installation of systemd timer is required.** GitHub Actions is the scheduler for this implementation; it relies on available Actions minutes, GitHub scheduling and the existing SSH credentials. Scheduled workflow jobs can be delayed. Review usage/cost, login permissions and any existing Actions policies.

### Read-only production preflight

The `Deploy Production` workflow now includes `Audit Shopify Partner configuration on production (read only)`. Following a successful deployment, inspect this job's logs for presence/absence of environment keys and two gate states. It does **not** print secret values, call Shopify, modify billing or fail the entire deployment solely because Partner billing isn't configured yet.

## Go/no-go policy

**NO-GO remains in effect** until an authorized Partner operator verifies:

- Exact Diaglob public application ID, organization ID, app handle, approved plan handle, billing interval and canonical USD prices in Shopify Partner Dashboard.
- A `Manage apps` Partner API token for that application; store securely in the running server environment, not Git.
- Correct test store: `diaglob-poc.myshopify.com` should be checked for development-store and **same Partner organization** eligibility; Bakatá remains reserved for ecommerce OAuth, **not billing tests**.
- Paid subscription selection on a no-charge development store, live `activeSubscription` response, redirect `plan_handle` validation, monthly↔annual changes, cancellation, replay, reconnect, and account isolation. Shopify effective price `0` in dev is **not** an approved production paid entitlement.
- Operational acceptance of a schedule that relies on GitHub Actions; confirm Telegram alerts and production SSH are working.
- Separate privacy request fulfillment and Shopify App Store readiness.

Only after operator-reviewed validation should both environment gates be enabled and an explicitly authorized paid entitlement run performed. No real charges, plan publication, app submission or merchant mutations are part of this change.

Docs: https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing and https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing/plans
