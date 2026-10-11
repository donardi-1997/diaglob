# Shopify staged plan reviews — read-only currentness assessment

## Operational endpoint

`GET /api/billing/shopify/transition-proposals/{review_id}/assessment` requires an authenticated current-organization **owner or manager**. It accepts only an internal integer review ID and scopes all database queries by organization. Foreign records and nonexistent reviews produce a non-disclosing error.

It returns an operational preflight:

- `status`: `ready_for_manual_review` or `blocked`
- `ready_for_manual_review`: whether the current Diaglob database still matches the staged review
- `blockers`: stable, non-sensitive codes explaining review-state changes
- `checked_at`, `expires_at` and the review's internal ID
- `activation_allowed: false`, `applied: false`, `shopify_reverified_now: false`, and `requires_new_shopify_verification_before_activation: true` **always**

There is no call to Shopify Partner/Admin, no writes, and no entitlement transition. The endpoint is for diagnostics and safe human review. **A clear assessment is never permission to activate a plan or proof of payment**; a future activation must verify the merchant and current contract *again* and atomically update the plan against current installation and billing state.

## What gets invalidated

A staged `pending_review` is reported as blocked if its 10-minute window expires, its underlying verification is no longer the latest verification, its verification data differs, or the organization is inactive. The preflight also blocks if the organization's current billing provider/baseline plan changed, legacy Paddle references are present, any additional Shopify merchant binding exists (including inactive or revoked), the current installation was uninstalled/reconnected, or its store is inactive/deleted.

This fixes the discrepancy between the original history endpoint, which only calculates a date-based `stale` status, and the real Shopify/organization state that can change independently of time. The historical status remains an audit field; consumers should consult the new assessment for operational review state.

## Security and E2E boundary

- Reverification with Shopify must be fresh, not copied from the record; no auto-approval or live payment activation.
- No customer/merchant names, Shopify shop GIDs, domains, tokens, pricing secrets or raw Partner payloads are returned.
- Assessment does not lock rows: it is advisory and cannot prevent an organization changing immediately afterward.
- Synthetic SQLite regression tests cover permission/tenant isolation, known foreign review IDs, new Partner evidence, TTL, revoked/reinstalled connections, changed billing provider/plan, legacy billing references, multi-shop bindings, paused stores and complete refusal to grant access.

## Still pending

Shopify Partner Dashboard credentials and approved prices for the **Diaglob** app, live development-store billing E2E, decision on multistore pricing, cancellation/trial/downgrade policies, GDPR fulfillment, and a separate **locked transactional entitlement activation** path. There is intentionally no activation endpoint or feature flag for it.
