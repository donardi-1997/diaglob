# Shopify privacy — internal case assessment (development slice)

**Status:** code implemented in draft PR #149; no live privacy data export, deletion, delivery, or processing authorization.

## Interface

- `GET /api/internal/shopify/privacy/cases` lists bounded PII-free receipts.
- `GET /api/internal/shopify/privacy/cases/{request_id}/assessment` provides an evidence summary.
- Both endpoints require `X-Internal-Secret` matching server-owned `DIAGLOB_INTERNAL_SECRET` and reject unauthorized requests before reading any case.
- `request_id` is the opaque 64-character lowercase hexadecimal receipt digest. Invalid IDs return 400; absent cases return 404.
- Returns only signed-intake evidence, validated scope flag, count of store-bound matches, shared customer protection count, coverage gaps and named blocker codes.
- The assessment does **not** return customer IDs, emails, phone numbers, encrypted selectors, store domains, Shopify order IDs or free-text. No result includes raw order/message data.

## Defense in depth

1. A matching `ShopifyPrivacyAuditEvent` with `event_type=received` and `actor_type=shopify_hmac_verified` must exist before calling scope preview. Without it, the service does not decrypt subject selectors or count records.
2. `preview_shopify_privacy_scope` performs the original organization/store/domain checks and resolves exact Shopify customer ID through a store-scoped profile. Unknown/cross-store identities do not authorize results.
3. A "subject_unresolved" result cannot be interpreted as a verified scope. The status `scope_preview_only` expressly does **not** indicate legal approval or entitlement.
4. The ORM coverage inventory still marks table coverage incomplete, and external processors/backups/legal holds remain blockers even for perfectly signed receipts.
5. The request remains outstanding regardless of a stored `status` string. Every response sets `requires_manual_review=true` and `fulfillment_authorized=false`.
6. Read-only SQL evaluation with **no audit status mutation**, no webhook response, no external delivery, no background worker and no explicit live processing enablement.

## Tests and prerequisites

Regression fixtures cover one customer linked to two stores, an authenticated intake audit, missing audit (no subject probe), mismatched shop domain, unresolved subject, unmapped organization, invalid/missing request digest, secret enforcement, sanitized responses and absence of state mutation. The route registry snapshot is updated.

Before creating live fulfillment, obtain approved field/processor coverage and retention decisions, authenticated merchant export delivery, auditable customer-level lineage, replay/restore suppression and isolation tests. Do not use this assessment as legal compliance proof.

Tracked by issue #148 and draft PR #149.
