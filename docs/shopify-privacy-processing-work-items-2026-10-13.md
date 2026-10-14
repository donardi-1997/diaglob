# Shopify privacy: persistent processing work items (2026-10-13)

## Implemented in this change

The existing verified-HMAC webhook handler persists durable, encrypted Shopify
privacy requests for `customers/data_request`, `customers/redact`, and
`shop/redact`. This change adds an **operational processing work queue**.
The queue is deliberately non-destructive and never exposes customer payloads.

For a case identified by its SHA-256 receipt ID:

- A signed-intake audit event is required before the work queue can be created.
- The stored organization/store boundary is verified using the existing
  scoped privacy assessment. The customer's Shopify ID is used when available;
  email/phone are never used to infer a match across stores.
- Ten source-specific tasks are recorded in one database transaction.
- Task uniqueness is `(request_id, area)`; retries do not duplicate audits.
- Identity verification is recorded as evidence, NOT as export/delete approval.
- Missing subject provenance, legal retention approval, backup coverage,
  processors or secure delivery remain explicit blockers.
- No work item changes `ShopifyPrivacyRequest.status`, sets
  `completed_at`, mutates buyers/orders, delivers PII or calls a provider.

## Internal operations (restricted)

Requires `X-Internal-Secret` with the configured `DIAGLOB_INTERNAL_SECRET`.
Do not expose this credential in browser code, logs, issue comments or
documentation examples. Use only over TLS and an approved internal environment.

- `GET /api/internal/shopify/privacy/backlog`: aggregate 30-day work queue.
- `GET /api/internal/shopify/privacy/cases`: redacted case list.
- `GET /api/internal/shopify/privacy/cases/{request_id}/assessment`:
  signed receipt, scope and coverage validation.
- `POST /api/internal/shopify/privacy/prepare-pending?limit=20`:\n  prepare at most 20 outstanding signed cases in a bounded batch (max 50);\n  cases with existing tasks are skipped and failures return opaque IDs/codes.\n- `POST /api/internal/shopify/privacy/cases/{request_id}/prepare`:
  prepare ten work items; idempotent and auditable.
- `GET /api/internal/shopify/privacy/cases/{request_id}/processing`:
  return work items and blocker codes only.

`prepare` requires signed receipt evidence; it does not require that a Shopify
customer can be resolved. Unresolved/after-uninstall cases are explicitly
blocked for investigation rather than silently ignored or cross-linked.
The read endpoint may return an empty work-item list for cases not yet prepared.

## Required work before live fulfillment

**This PR does not fully fulfill Shopify privacy requests.** Retention and
subprocessor decisions cannot be inferred from successful automated tests.
Never report a receipt as fulfilled or assert App Store GDPR compliance based
on a prepared work queue. The full workflow needs, in order:

1. Approved per-field legal retention and legal-hold decisions for financial,
   logistics and communications records.
2. Verified subject provenance for each local table, especially shared
   `customers`, order-only IDs, merchant Copilot sessions, automation payloads,
   messages, attachments, KB embeddings and AI-derived records.
3. Certified connectors or documented/manual evidence for WhatsApp/Instagram,
   email, AI providers, suppliers, advertising, object storage, logs and backups.
4. Tested export/redaction implementation with store-scoped access, encryption,
   role-based merchant delivery, irreversible deletion gates, and a suppression
   ledger preventing reimport, replay, and backup-restoration resurrection.
5. End-to-end Shopify development-store tests with the actual deployed webhook
   subscriptions; signed delivery tests do not prove subscription registration.
6. Independent final verification, request completion audit, merchant delivery
   receipt and SLA monitoring. The existing outstanding backlog correctly
   counts all requests until end-to-end evidence is available.

Shopify currently requires processing within 30 days, except where legally
required retention prevents deletion. Refer to:
https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance

## Verification

Run:
```bash
cd backend
pytest -q tests/test_shopify_privacy_processing.py
ruff check app/model_domains/shopify_privacy.py app/models.py app/services/shopify_privacy_processing.py app/api/shopify_privacy_backlog.py tests/test_shopify_privacy_processing.py
```

Run migrations in a test environment first and validate the revision graph.
Until approved, do not turn on automatic customer-data redaction or claim any
prepared case is complete.


## Local customer-data processing block

The service `backend/app/services/shopify_privacy_local_processor.py` adds
two distinct operations for **verified HMAC-received requests**:

1. `build_encrypted_local_customer_export(db, request_id=...)` reads only
   the exactly matched Shopify customer-store profile, its linked orders and
   order items, conversations/messages, and conversational checkouts. A
   Shopify-provided `orders_requested` list restricts the selected orders.
   Unknown referenced orders count as unresolved; the service never uses
   email, phone or human-visible order numbers as a substitute identifier.
   Ambiguous/missing customer IDs, multiple profiles, unauthorized stores,
   invalid selectors, oversized rowsets and missing signed intake fail closed.
   The response includes ciphertext encrypted using
   `SHOPIFY_TOKEN_ENCRYPTION_KEY` but is available only inside trusted
   Python services; **no current HTTP endpoint or database table receives
   the payload**. The export is incomplete by design: global identity,
   agents, automations, processors, files and legal retention remain uncovered.
   The service does not log, persist or deliver the export.

2. `build_local_redaction_manifest(db, request_id=...)` identifies the exact
   affected local row counts and candidate PII fields, including a restricted
   `orders_to_redact` subset when supplied. It preserves shared customer
   identity and never alters, deletes or commits any record. Unknown order
   IDs in an explicit redact request are blocked rather than broadening scope.

Only approved internal callers may invoke the following metadata-only routes:

- `POST /api/internal/shopify/privacy/cases/{request_id}/local-export/inspect`
  returns counts and an unresolved-order count, not ciphertext or SHA-256.
- `GET /api/internal/shopify/privacy/cases/{request_id}/local-redaction/manifest`
  returns field names and row counts, not PII, and always
  `mutation_allowed=false`.

Both endpoints require `X-Internal-Secret` before invoking the processor.

**Remaining requirements before real deletion or disclosure:**
a legal hold and fiscal-retention decision per field and record; clear
provenance for global identities and message contents; suppression of future
Shopify imports/automation replay; deletion workflows covering providers and
backups; identity-verified merchant delivery; a completion evidence trail.
The existing SQLite synthetic redaction test service is still restricted to
pytest and cannot operate against production PostgreSQL.

New contract tests:
`pytest -q tests/test_shopify_privacy_local_processor.py`.
