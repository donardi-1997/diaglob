# Shopify privacy scope preview — read only, synthetic tests

This module is a non-destructive discovery step for Shopify data subject requests. It is **not** data export, erasure, or compliance fulfillment.

`app.services.shopify_privacy_scope_preview.preview_shopify_privacy_scope` takes an already authenticated and persistently recorded privacy receipt. It requires organization/store IDs from trusted receipt intake, verifies the original Shopify domain through the stored store record or corresponding Shopify integration, and returns counts of the matched customer-store profiles, store-scoped orders, and conversations. For customer requests, it matches only the exact Shopify external customer ID associated with the source store.

If a customer is shared between stores, the preview counts protected cross-store customer profiles but **never** flags the global customer row for deletion. It does not read/export names, phone numbers or email addresses and has no database writes. No HTTP endpoint invokes this service.

Shop-level preview counts all records scoped to the exact tenant/store, never records of other tenants or stores. If tenant linkage, trusted store identity, customer ID, or encrypted subject selectors are missing, the preview fails closed or reports an unresolved subject for manual investigation.

Important limitations:
- Counts are not an exhaustive record of all PII. Automation state, deliveries, order metadata, messages, AI histories, attachments, logs and external processors require additional inventory.
- A subject may be linked through other sources or have records without a customer-store profile; the preview must not be relied on to fulfill Shopify's export/redaction requirement.
- No real-data deletions, changes to Shopify, or production deployment are authorized.
- Actual erasure requires retention/legal hold decisions, verified tenant-bound data inventory, a durable auditable worker, backup/re-ingestion controls and synthetic E2E coverage.

Tracking: issue #148 and draft compliance PR #149.