# Shopify privacy — sensitive-data surface coverage

Status: **read-only metadata inventory for engineering review, not a privacy compliance verdict**.

`inspect_shopify_privacy_coverage` inspects registered SQLAlchemy table
definitions. It **does not** connect to a database, select customer rows, create
exports, anonymize anything, or reach Shopify or external processors.

## Deliberately conservative treatment

Explicitly listed sources include shared global customer identity, store-local
profiles/orders/order items, conversations/messages, conversational checkouts,
Copilot sessions/messages/tool calls, AI agent approvals, customer risk reports
and disputes, knowledge sources, and fulfillment automation jobs.

- `partial` means the synthetic-only privacy export/redaction proof of concept
  includes **some** store-bound fields, not that a complete export, deletion
  policy, legal retention or merchant delivery process exists.
- `uncovered` means fields, tenant/store ownership, source provenance,
  retention and erasure are **not yet implemented**.
- A table with customer/email/phone/address/message/content/session/payload
  field names not present in the known registry is automatically included in
  `unclassified_sensitive_tables` for manual review.
- A known table that disappears from registered ORM metadata is reported in
  `missing_declared_tables`, rather than being ignored.
- A static `external_review_areas` inventory blocks any assumption that SQL
  metadata covers AWS S3, Bedrock, messaging providers, carriers, Dropi,
  analytics/ad platforms, logs, backups, restore/reingestion or legal holds.

**`ready_for_live_privacy_processing` intentionally remains False even if
all listed tables are found**. This scanner cannot establish personal-data
provenance, account cross-linking, Shopify subject identity, access to external
processors, lawful retention, or the ability to safely delete. A table that
lacks obvious sensitive column names can still contain PII in JSON, free-text,
encrypted blobs and linked provider data; human code review remains required.

## Next implementation gate

Expand each listed table with field ownership/provenance and retention rules,
then build corresponding synthetic fixtures proving source-store isolation,
shared customer protection, export completeness and deletion/idempotence.
Design legal holds and anti-reingestion controls before a production worker
exists. Add all external provider agreements and their disposal/export APIs.

There is no API endpoint, worker, permission change, merge to `main` or
production deployment associated with this inventory.

Tracking: issue #148 and Shopify privacy draft PR #149.
