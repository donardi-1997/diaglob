# Shopify organization billing: merchant-binding audit guard

**Scope:** No-charge, read-only billing reconciliation. No entitlements are applied and no Shopify/Paddle charges are created by this change.

## Finding

The existing `GET /api/billing/shopify/reconciliation-preview` filters to stores with `Store.active=True`, `Store.deleted=False` and `CommerceConnection.status=connected` **before counting Shopify installations**. A tenant with two Shopify merchants could appear to be a one-shop tenant if another merchant's Diaglob store was paused/deleted or its connection was errored/revoked. Shopify App Pricing is merchant-specific, but Diaglob's legacy `Organization.plan` is organization-wide: incorrectly collapsing multi-shop provenance could lead to granting organization entitlements based on the wrong merchant.

## Change

- Count **all Shopify connection records belonging to the current organization**, including deleted, paused, errored and revoked bindings. Use `LIMIT 2` because the guard needs only `0 / 1 / >1`.
- If the count is not exactly one, return HTTP 409 `SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED` **before contacting Shopify**.
- If exactly one exists, independently ensure the associated Store still belongs to the same tenant, is active and not deleted, and the installation connection remains `connected`. Otherwise return HTTP 409 `SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED`.
- Preserve the underlying Partner + Admin read-only verification and existing owner/manager authorization requirements, plus `requires_review=true`, `applied=false`.
- No automatic subscription activation or Paddle migration. No new API route, migration, permission or secret required.

## Tests and merge criteria

`backend/tests/test_shopify_billing_binding_guard.py` uses in-memory SQLite and an externally mocked billing verifier. It covers active + paused, active + deleted, active + revoked, active + errored, two active stores, a lone ineligible shop, one eligible shop, cross-tenant isolation and unauthorized membership.

Merge only if complete backend CI and lint are green at the exact head SHA. Production deployment will follow normal `main` deploy with no change to billing entitlements.

## Still blocked

Real Shopify App Pricing merchant-plan mapping/plan catalog, partner API configuration, live subscription events and multi-shop policy remain unverified and are deliberately **not enabled** here. Shopify App Store publication still requires privacy fulfillment, consent/retention decisions and development-store E2E.
