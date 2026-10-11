# Shopify managed billing — staged plan transition reviews

**Scope:** auditable staging only. No Shopify charges, entitlement activation, plan updates or access revocation. This design is deliberately disabled for real grants until commercial/privacy decisions and live Partner credentials have been reviewed.

## Flow

1. Owner/manager calls `POST /api/billing/shopify/reconciliation-check` to record a fresh, provider-backed verification from Shopify Admin + Partner APIs (checks approved plan handle, period and price). It is non-authorizing.
2. **Owner only** calls `POST /api/billing/shopify/transition-proposals` with a numeric `verification_id` from that organization's audit history. The server never accepts a client-supplied target plan, amount, shop domain or billing provider.
3. A single database transaction locks the organization (PostgreSQL), loads verification scoped to that tenant, and requires the **latest** successful verification, `plan_transition_requires_review`, a recognized paid target plan, an existing distinct baseline plan and 1/12 month period. Evidence older than **10 minutes** or in the future is rejected.
4. The transaction revalidates: active organization, `billing_provider=shopify`, unchanged `Organization.plan`, no outstanding legacy Paddle customer/subscription references, exactly one Shopify binding (including revoked/paused binding counts), current active store, connected status, and **exact connection installation epoch**.
5. An expired pending review can be marked `stale` within the same transaction. A live pending review blocks a different verification. A unique verification index and a partial unique index on the organization's `pending_review` proposals prevent concurrent duplicate proposals. Same-verification retries return the original review.
6. The resulting row has `status=pending_review`. It stores only Diaglob internal IDs, baseline/target canonical plan, period, installation timestamp, expiry, and creation time; it stores **no** merchant domain, Shopify ID, sensitive contract payload or token.
7. Owner/manager may query `GET /api/billing/shopify/transition-proposals?limit=20`. Only this organization's rows are visible, with `requires_review=true` and `applied=false`. A pending proposal past its expiry is surfaced as `stale`; it cannot confer access.

## Hard security boundary

- **There is no HTTP endpoint to approve or activate a subscription, and no environment flag that turns on entitlement grants.** The `activate_shopify_plan_transition` implementation always fails with `SHOPIFY_ENTITLEMENT_ACTIVATION_DISABLED`, including in development/test.
- Creating or reading the proposal **never writes** `Organization.plan`, `Organization.billing_period_months`, `subscription_status` or an existing Paddle contract. Product entitlements continue to derive from existing organization state.
- This proposal is **not proof of a payment**. A future activation must reverify the Shopify subscription and its shop identity/plan/price at decision time, establish paid status, enforce the approved multi-shop model, and perform conditional versioned CAS plus audit under the same transaction as the entitlement write. Shopify uninstall/reinstall must invalidate such decisions.
- Partial unique indexes rely on PostgreSQL/SQLite; CI runs SQLite synthetic tests and the deployment uses Alembic migration `e7f8a9b0c1d2` after `d6e7f8a9b0c1`.
- No automatic downgrade or user-access termination upon observed cancellation. Legal data-retention and processor requirements remain separate.

## QA and release

Automated tests check exact-verification replay, expiry, latest-only checks, changed shop installation, merchant revocation, switched org plan/provider, second paused/revoked merchant, cross-tenant isolation, one pending proposal per org, replacement of expired proposals and explicit refusal to activate.

The PR must pass full backend validation, single Alembic head and route contract. Do **not** claim Shopify App Store compliance or production payment enablement from a green CI.

## What remains to enable real entitlements

Partner Dashboard access for **Diaglob's own** app (not Bakatá), operator-approved monthly and annual prices, identity/plan validation with a development shop, a formal multi-store pricing decision, billing cancellation/downgrade/trial policies, reviewed transactional activation protocol and the remaining GDPR privacy fulfillment.

Shopify reference: https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
