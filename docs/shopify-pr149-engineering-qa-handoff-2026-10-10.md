# PR #149 — engineering acceptance and QA handoff
Updated: 2026-10-10 · Owner of document: ChatGPT · Status: **implementation blockers; not approval to merge**

## Source-of-truth documents
- [Privacy inventory and exact ownership](shopify-privacy-inventory-ownership-review-2026-10-10.md)
- [Retention/fulfillment ADR — proposal requiring approval](shopify-privacy-retention-and-fulfillment-adr.md)
- [Security, scopes and Shopify checkout audit](shopify-security-scopes-review-2026-10-10.md)
- [Pricing contribution sensitivity](shopify-commercial-pricing-review-2026-10-10.md)
- [App Store listing and reviewer assets](shopify-app-store-publication-kit-2026-10-10.md)
- Prior branch work: `shopify-privacy-*`, `shopify-app-pricing-*`, `shopify-release-readiness.py`, issue #148

## P0 — Codex implementation tickets (must pass before Shopify App Store submission)
| ID | Task | Acceptance evidence |
|---|---|---|
| PRIV-01 | Per-source customer/shopping data lineage for all DB tables, queues, AI/KB, S3 and external processors | reviewed exhaustive field map with owner/store/subject lookup; missing category fails closed |
| PRIV-02 | Authenticated, encrypted and expiring actual data-request export | exact Shopify store + subject only; export delivery to authenticated merchant; no cross-tenant records; audited access and retry |
| PRIV-03 | Retention-aware redaction with shared-record protection and legal hold | only approved fields redacted; order/financial retention policy; per-source checkpoints, idempotence, reversible-dry-run to irreversible/live approval boundary |
| PRIV-04 | Re-ingestion and external-data coverage | test replay after delete, sync/campaign retries, restore; processors and object references verified or documented legally retained |
| PRIV-05 | Durable request lifecycle | HMAC 401 on invalid body, dedupe, dead-letter, SLA escalation, audit reason, no false terminal state |
| BILL-01 | Trusted Shopify-managed subscription state machine | shop GID verified via Admin API and Partner subscription; correct plan handle, interval, trial/cancel state; fail closed on unknown/missing |
| BILL-02 | Entitlements, isolation and merchant checkout | Shopify-hosted pricing + activated plan only after confirmation; Paddle unaffected on independent channel; multi-store mismatch blocked or explicitly resolved |
| OAUTH-01 | Install/reinstall/uninstall and app architecture | Shopify-owned install, OAuth immediately, correct UI, App Bridge ID tokens if embedded, revocation and shop binding tests |
| ORDER-01 | Checkout and order mutation compliance | map all order/COD/draft/fulfillment mutations, merchant authorization, checkout proof, no unsupported bypass |
| SECURITY-01 | Protected customer data scopes and secrets | minimal reviewed scopes, field-level handling, no token/PII logs, role and cross-tenant negative tests |

## P1 — ChatGPT reviewer gates
- Review PRIV-01 against schema registry (including JSON/free text), Copilot, automations, derived AI, files, external processors and backups; reject blanket “complete” declarations based on counters.
- Verify source-code changes and fixtures against the retention ADR with special focus on shared Customer, multi-store organization and restored deleted records.
- Verify Shopify hosted App Pricing and Partner API confirmation; independently review effects on existing Paddle organizations.
- Check final SHA CI backend/frontend/flow tests plus security E2E evidence; do not use an older green CI run as final-head proof.
- Approve accurate listing only when storefront demo and backend API behavior match words used. Update release evidence gate with approved artifacts but do not set TRUE based solely on docs.

## P1 — Owner decisions / account configuration
- Approve retention legal basis and exceptional categories with counsel; no legal periods are assigned in code today.
- Approve final list price, annual discount, trial, included usage, multi-store contract interpretation and commercial overage policy.
- Grant appropriate review-only Dashboard access/Partner API token via secret manager and authorize any paid test or real-data/production change separately.
- Approve final English listing, reviewer assets, release and formal Shopify submission.

## Test plan and evidence format
Every task must provide: unique ID, code path(s), synthetic fixture(s), exact before/after test result, CI URL and final HEAD SHA, negative isolation test, documented rollback/disable switch and audit of customer-/payment-impacting side effects. Production/configuration proofs additionally require time-stamped read-only observations. Reports may contain only synthetic IDs and redacted outputs.

## Release policy
- PR #149 remains **DRAFT**, no merge to main or deployment until required gates are met.
- Current work is review and documentation; do not publish paid plans, wipe customer data, run real orders or overwrite secrets.
- CI green is necessary but not sufficient for security/privacy/Shopify approval.
