# DIAGLOB — Shopify App Pricing integration

Status: **read-only Partner API verifier implemented**, no active billing integration, no entitlements enabled by this code, no live paid plans activated.

## Authority and integration architecture

Shopify App Pricing is the supported subscription system for new public Shopify App Store applications. Pricing, trials, approval, invoices and charges are managed by Shopify's Partner Dashboard, **not** by creating legacy `appSubscriptionCreate` charges.

Official references:
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
- https://shopify.dev/docs/api/partner/latest
- https://shopify.dev/docs/api/partner/2026-10/active-subscription

The module `app.services.shopify_app_pricing` reads `activeSubscription(appId:, shopId:)` over Partner API v2026-10; it does not create, modify or cancel subscriptions or mutate DIAGLOB organizations.

Configuration required through secrets management (not yet provisioned):
- `SHOPIFY_PARTNER_ORG_ID`: organization ID from Partner Dashboard.
- `SHOPIFY_PARTNER_APP_GID`: Shopify App GID **verified from the linked existing DIAGLOB application**; do not assume the Partner Dashboard numeric app entry is automatically the correct API GID.
- `SHOPIFY_PARTNER_ACCESS_TOKEN`: token for a newly created Partner API client, scoped to the intended Partner organization with only the **Manage apps** permission for this read-only use case. Never paste the token into GitHub.
- Merchant `gid://shopify/Shop/<id>` must come from a trusted authenticated Shopify installation/verified Admin API response, NOT an untrusted redirect domain.

## Required before enabling features

1. Codex/browser operator verifies the existing Partner organization/app identity and current public-plan configuration in Shopify Partner Dashboard, **without changing prices or permissions**.
2. Owner authorizes creating a Partner API client with the minimum required permissions and supplying its token through secure secret storage.
3. Backend securely resolves and persists the exact Shopify Shop GID on a verified installation, with tenant-scoped ownership.
4. Confirm Shopify App Pricing plan and item handles from actual Partner API test responses. Never infer a paid plan from a redirect `plan_handle` parameter, display name, or price alone.
5. Implement a server-side allow-list mapping from verified subscription records to DIAGLOB entitlement plans, with fail-closed behavior for unknown/ambiguous handles; reconcile at login, periodic intervals, and lifecycle events.
6. Route App Store organizations to Shopify's **hosted pricing page** and prevent Paddle transactions for that contracting channel. Keep Paddle for independent DIAGLOB contracts when allowed.
7. Test on a development store with Shopify's no-charge plan testing. No live merchant charges without explicit owner approval.

**Do not** implement a Shopify adapter by naively satisfying Paddle's current `BillingProvider` interface; its `create_transaction`, `update_subscription`, `cancel_subscription`, and webhook assumptions are incompatible with App Pricing's Shopify-hosted plan lifecycle.

## Observability and safeguards

The read-only verifier raises `ShopifyAppPricingError` on absent credentials, invalid GIDs, transport failures, HTTP errors, GraphQL errors, or malformed responses. It never returns a paid entitlement on an unverified result. Tokens are used only in the `X-Shopify-Access-Token` header and must never enter logs.

Shopify App Pricing does not send legacy billing-update webhooks after April 2026: use authenticated redirect inputs **only as triggers**, and re-query Partner API to confirm current plan. For out-of-band cancellations/freezes, periodically query Partner API. Rate-limit requests and cache verified state only within an appropriate narrow window.

This work is independent of the draft privacy PRs #149/#150/#151. Tracking issue #148.
