# Shopify privacy — durable audit and synthetic review state machine

Status: **development branch only**. This is a review/triage substrate, **not**
a complete Shopify privacy processor, delivery worker, or lawful deletion.

## Incoming authenticated event

The Shopify HMAC-verified intake (existing `/api/webhooks/shopify/compliance`)
now writes two records in **one database transaction**:

- `shopify_privacy_requests`: minimal encrypted customer/order selectors,
  original Shopify shop identity and optional trusted tenant/store association.
- `shopify_privacy_audit_events`: a PII-free `received` event referencing only
  the hashed request identifier, enum-like event/status fields and an actor type.

Receipt uniqueness continues to deduplicate Shopify delivery retries. A race
that violates uniqueness is rolled back, including the proposed audit event.
No raw Shopify payload, name, email, order ID or customer ID is stored in
the audit event table.

## Synthetic-only review transitions

`app.services.shopify_privacy_review_workflow.record_synthetic_privacy_review`
uses compare-and-set status updates and append-only audit events in the **same
transaction**. The operation is gated by ALL of: a running pytest invocation,
an explicit `DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS=1` environment flag and
the database dialect being SQLite.

Permitted review transitions:

| From | To |
|---|---|
| `pending_policy_review` | `scope_reviewed`, `manual_review_required` |
| `scope_reviewed` | `retention_review_pending`, `manual_review_required` |
| `retention_review_pending` | `blocked_external_coverage`, `manual_review_required` |
| `blocked_external_coverage` | `retention_review_pending`, `manual_review_required` |
| `manual_review_required` | `pending_policy_review` |

If the org or store was not confidently bound, `scope_reviewed` is prohibited.
Retries of the same transition are idempotent; racing/stale transitions fail.
Only fixed reason codes are accepted; arbitrary free text, which could contain
PII, is rejected. There is **no completed/erased/exported state** in this
review workflow.

## Explicitly outstanding for live Shopify compliance

1. Approved legal retention and hold rules per country and data category.
2. Complete discovery of shared/global customers, AI outputs, automations,
   attachments, external suppliers, logs, backups and Shopify-order links.
3. Authenticated merchant data export delivery with TTL, authorization,
   encryption and complete scoping; current export is partial synthetic only.
4. A durable worker with retry/backoff/dead-letter handling, full validation
   of deletion scope, field-level retention exceptions and anti-reingestion.
5. Authorized production review workflow (RBAC, dual-control where required,
   actor IDs, escalation and deadline monitoring); synthetic workflow must
   **never** be wired to production endpoints or scheduled jobs.
6. Operational evidence and E2E Shopify testing after app-level compliance
   webhook configuration has been deployed and verified.

The owner approved only **synthetic-data development**, not live erasure,
merchant disclosure, subscription charges, merging to `main` or deployment.

Related: draft PR #149, issue #148.
