# ADR — Shopify customer data retention, export and redaction design
Status: **PROPOSED, NOT APPROVED** · 2026-10-10 · Applies to DIAGLOB PR #149 only

## Decision context
Shopify requires mandatory signed compliance webhooks `customers/data_request`, `customers/redact` and `shop/redact`. Shopify states that the action should be completed within **30 days from receipt**, except data legally required to be retained. The 30 days is a Shopify requirement, **not** permission for blanket deletion or an approved DIAGLOB retention schedule. The current handlers/inbox acknowledge/record but do not complete live fulfillment; the synthetic processor must remain test-only.

Source: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance

## Proposed retention principles, not numeric legal determinations
- **Minimize** collection by merchant-enabled purpose; record the data source, purpose, lawful basis, exact tenant/store, subject provenance, processor and classification at ingestion.
- **Separate classes**: (A) commerce/financial/order evidence potentially subject to mandatory retention; (B) customer-contact/shipping and support data; (C) AI/copilot/automation free text and derived records; (D) signed GDPR request selectors/PII-free audit; (E) external providers and backups.
- **No automatic retention duration** is accepted today for any class. Required approvals: applicable jurisdictions (merchant and buyer), statutory business/financial record retention, legal hold, vendor contracts, privacy policy, support and incident logs. Never invent a universal 30/90/365-day retention period for all data.
- For a valid redact case, remove or irreversibly de-identify only personal fields lacking an approved legal hold; if statutory order records must remain, retain minimum required fields under restricted access and log the **reason code + policy version**, not plaintext data. Evidence of exemptions is per category and reviewed, not one global exemption.
- **Provisional operational recommendation:** export links one-use and short-lived (target ≤24h after authorized creation); store exports encrypted separately and never in logs; purge temporary artifacts on use/expiry. Not a law or final policy.
- For pending privacy requests, track the Shopify 30-day action target with warning at day 23 and critical at day 30; high-priority unresolved/mismatched store identity cannot be silently marked complete. Route possible legal holds for manual timely resolution.

## Planned request state machine
`received_authenticated` → `tenant_and_subject_verified` → `inventory_reconciled` → `retention_reviewed` → `execution_approved` → `processing` → `verify_all_sources` → `fulfilled` **or** `retained_under_legal_obligation` with explicit evidence.

Any exception moves to `blocked_manual_review` (e.g. missing tenant, unavailable processor, unmatched Shopify order, missing subject ID, cross-store reference), with retry metadata, alerting and audit. `HTTP 200` acknowledgment, a reviewer click, or passing tests NEVER advances a request to `fulfilled`.

## Required invariants before implementation
1. Webhook: authenticate **raw body** HMAC in constant time; reject invalid HMAC with 401; establish stable request digest and dedupe idempotently.
2. Processing identity: signed receipt bound to originating Shopify app/shop and immutable organization/store relationship. A customer selector tied to another store must not cause reads or deletes.
3. Export: enumerate all subject-owned fields and processor copies; avoid naive free-text matching and reject incomplete enumeration. Deliver only to authenticated, authorized store-owner workflow with expiry and access audit.
4. Redaction: dry-run generates scoped counts and a sealed plan; legal hold review and **dual authorization** for destructive live changes; transaction boundaries, retry-safe per-source checkpoints, fail closed on errors. Do not hard-delete shared Customer rows or accounting records without retention clearance.
5. Re-ingestion: hashed/HMAC suppression key per source/shop/customer, not reversible plaintext. Check suppression before sync, webhook upsert, campaign render, KB retrieval/ingest, restore and retries; provide safe key rotation strategy.
6. External processors: record delivery/deletion ticket ID, vendor response and verification; queue and dead-letter processing before claiming completion; no unverified “fire and forget.”
7. Backups: map immutable backup lifecycle, restoration runbook and suppression replay; cannot promise immediate physical deletion where backup retention prevents it. Flag exceptions in disclosure and legal review.
8. Audit: append-only PII-free action events with request digest, actor, purpose, policy/version, source, row counts and result; restrict full data access and minimize error logs.
9. Controls: tenant RBAC, allowed-action roles, CSRF protections where relevant, rate limiting, secret rotation, encryption key separation, time zone UTC consistency and telemetry without PII.
10. Execute against synthetic data in dev and inspect actual production resources only with separate authorization. No live export, erase, store uninstall, billable calls or changes to production app configuration in this ADR.

## Proposed acceptance gates
- Both positive and negative HMAC tests; replay and duplicate/idempotency tests; subject ambiguity test.
- Full inventory coverage per `docs/shopify-privacy-inventory-ownership-review-2026-10-10.md` including all external sources and legitimate retention decisions.
- Cross-store and cross-tenant isolation, shared-record protection, failed-provider and dead-letter recovery; verified status cannot be forged or set by webhook receipt alone.
- Backups/restore can be replay-suppressed; processor deletion verified or documented legally exempt, not silently skipped.
- Authenticated export test proves only the correct merchant principal receives correct subject data and TTL is enforced.
- Internal QA authorizes staging test; legal reviewer + owner approve exact production policy and activation before any real customer data touched.

## Approval register (all OPEN)
| Approval | Owner | Current decision |
|---|---|---|
| Classes and statutory retention periods by jurisdiction | Legal + product owner | NOT APPROVED |
| Authorized requester and data delivery mechanisms | Product owner + security | NOT APPROVED |
| External processors, subcontractors and backups | Operations + legal | UNVERIFIED |
| Production destructive processing | Product owner | NOT AUTHORIZED |
| Shopify App Store “privacy compliance” statement | Security + product owner | BLOCKED |

This ADR is not legal advice, a privacy policy, a data-deletion claim or an authorization to enable execution.
