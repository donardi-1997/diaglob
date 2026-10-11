# Shopify App Pricing — audited subscription checks

**State:** Implementation proposal in PR; not a live billing grant. Shopify-hosted plans, configuration, reviewed retention and development-store E2E remain incomplete.

## Existing source of truth

`GET /api/billing/shopify/reconciliation-preview` verifies the authenticated current installation via Shopify Admin API, then the current subscription via Partner API `activeSubscription`. The service checks an operator-approved plan handle, interval and exact USD flat-rate price. It returns a **non-authorizing** preview. It does not call the legacy Billing API, create charges, set `Organization.plan`, update `subscription_status` or modify the Paddle contract.

## New safe reconciliation evidence

- `POST /api/billing/shopify/reconciliation-check`: authenticated owner/manager only. No request body: the organization comes from the session and the Shopify shop comes from its **single** connected merchant binding. The endpoint invokes the same live Partner/Admin verification as the existing GET preview, then writes one operational evidence row after re-reading tenant, store and installation fields.
- `GET /api/billing/shopify/reconciliation-history?limit=20`: authenticated owner/manager only, bounded limit 1–50, filters by the current membership's organization ID, most recent first. Never includes another organization's records.
- The `shopify_billing_verifications` table records only internal org/store/connection IDs, the installation `connected_at` epoch, a fixed status code, current/target canonical plan and billing interval, and an audit timestamp. **No Shopify Shop GID, merchant domain, plan handle, price, token, customer or raw provider response is stored.**
- Row locking when supported, identity-map refresh, exact installation epoch comparison, organization billing-provider/plan recheck, store membership and active-state recheck, and another full Shopify-binding count all run **after** the network call. If the connection was reinstalled/disconnected, org plan/channel changed, second merchant added or store deactivated during verification, return `409 SHOPIFY_BILLING_STATE_CHANGED` without an audit row.
- Unavailable/malformed Partner API data still fails closed through the preview endpoint (typically HTTP 503 or 409). A failed check does not receive a successful audit record, so the history is evidence of completed checks, not a complete log of HTTP attempts.
- Both a verified unchanged plan and a plan transition still require manual review. An inactive Partner subscription can be recorded as `subscription_inactive_requires_review` but **cannot revoke access automatically**.
- Concurrent checks may record distinct evidence rows; these rows are deliberately **not** a freshness-based access cache, payment receipt or idempotent entitlement transition. An access grant requires a future separate transactional feature with its own replay-safe version control and policy approval.

## Migration

Alembic revision `d6e7f8a9b0c1` creates the minimal append-only `shopify_billing_verifications` table after `c5d6e7f8a9b0` with indexes for organization, store and time. No changes to existing customer/order/billing tables. Rollback drops only the new evidence table.

## Permissions and tests

Automated synthetic SQLite tests verify:

- Owner/manager checks and tenant-scoped history; unauthorized roles blocked before DB/provider calls
- Active subscription verified, target plan recorded, no plan/price/token changes
- Inactive subscription cannot silently remove an existing plan
- Merchant reinstall or org plan switch during the Partner call invalidates the check
- Second (including paused/revoked) Shopify connection rejects the check before the provider
- Missing/incorrect provider payload never creates entitlement evidence
- History contains no Shopify shop ID, domain, plan handle or credentials

## Still needed before live Shopify-managed access

1. Access to the **correct Diaglob Shopify Partner application**, Partner API client token and approved plan handles/amounts/intervals (do not reuse Bakatá's connection).
2. Shopify's actual hosted plan selection and trial/downgrade/cancellation E2E using a Diaglob development shop, with no real merchant charges.
3. Owner-approved mapping for merchants with multiple stores/Shopify subscriptions and Paddle coexistence.
4. Transactional entitlement activation only after current Partner subscription and shop identity are confirmed, with concurrent install/uninstall guarantees and periodic re-verification.
5. Completed legally approved privacy fulfillment, retention and source/processor coverage.

Official: https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
