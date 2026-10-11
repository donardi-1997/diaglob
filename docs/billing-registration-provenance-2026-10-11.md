# Billing origin on registration — direct and Shopify installation

## Problem solved

Prior to this block, new Cognito-provisioned Diaglob organizations were created with `billing_provider=NULL`. Since Plans & Billing now fails closed when the provider is unknown, normal direct signups could not reach Paddle checkout. Shopify installation starts at an unauthenticated public `?shop=` hint and must never be treated as a verified subscription.

## New registration contract

The authenticated `POST /api/register/provision` accepts `registration_channel` with exactly two permitted values; omitted defaults to `direct`. The field only applies to the **creation of a new organization**; existing memberships and invitation acceptance continue to return the original organization unchanged, including its billing provider and paid entitlements.

| Registration origin | Initial onboarding channel | Initial billing provider | Billing UI |
|---|---|---|---|
| Direct portal signup | `direct` | `paddle` | Existing Paddle plans/checkout |
| Shopify-initiated install return path with a valid untrusted shop hint | `shopify_install` | `NULL` (pending) | No Paddle checkout until Shopify ownership confirmed |
| Legacy pre-existing org | `NULL` | **unchanged** | Existing provider preserved, unspecified remains blocked for review |

Do not infer Shopify ownership or pricing from the registration channel, frontend return URL, `shop` query, HTTP headers, or a merchant's email domain. The frontend sets a **provisional** origin only if its preserved, validated return path matches `/shopify/install?shop=VALID.myshopify.com`.

## Provider finalization after OAuth

The only path that calls `confirm_shopify_install_billing` is the Shopify OAuth callback following the HMAC check, one-time state claim, shop/domain match and successful credential exchange + connection commit.

This separate database transaction locks the organization when supported, and requires **all**:

- Immutable signup origin is `shopify_install` and `billing_provider` is still `NULL`.
- Organization is active and has only a `none` or `trial` plan; active/paid plans never get switched.
- No Paddle billing customer/subscription/price ID or pending paid plan.
- Exactly one Shopify connection belonging to that organization, with `status=connected`, and an active, non-deleted Store belonging to the same organization.
- Connection ID provided by the verified OAuth transaction must match exactly.

Only then set `billing_provider=shopify`. This **does not** grant a plan, authorize payment, create a Shopify App Pricing contract, or mutate Paddle subscriptions. The existing Shopify Partner API validation of shop GID, approved handle, interval, USD price and plan still governs later read-only billing reconciliation. Actual activation remains hard-disabled.

If Shopify API token exchange fails, the callback cannot promote the organization. If an already-paid Paddle organization connects Shopify as a commerce integration, its Paddle billing provider stays unchanged.

## Database migration

`f8a9b0c1d2e3` adds nullable `organizations.billing_onboarding_channel` after `e7f8a9b0c1d2`. It does **not** backfill or overwrite legacy organization providers and requires no billing credential change.

## Test/release gate

Backend synthetic tests cover direct/new registrations, invalid origin values, trial-state verified OAuth promotion, strict legacy Paddle/customer/subscription/price ID exclusion, paid plans, duplicate/revoked connections, foreign organization ID and public install handoff. Frontend tests cover valid and invalid install return paths.

CI must pass both backend shards, frontend lint/tests/build and Alembic single-head before merge, followed by production deployment verification.

## Remaining commercial and product requirements

- New Shopify installations still need a Diaglob store selected/created and OAuth completed. This block does not automate store creation.
- Existing unassigned legacy organizations must be **audited individually** before migration. Do not globally coerce `NULL` to Paddle or Shopify.
- Existing direct/Paddle customers entering via Shopify App Store should not be silently converted. Define the external App Store contracting/migration policy before offering their transition.
- Verify live installation and Shopify-hosted plan selection on the independent development store `diaglob-poc.myshopify.com`. Do not use Bakatá's Shopify connection for Diaglob billing.
- Complete approved Shopify App Pricing catalog, hosted billing lifecycle, multistore rules, privacy fulfillment and real transactional entitlements before enabling paid grants.
