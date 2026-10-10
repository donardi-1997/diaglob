# DIAGLOB — synthetic-only privacy export and redaction planning

**Status:** implementation of a controlled **partial export** and **non-destructive redaction plan**, not fulfillment of a Shopify compliance request. Do not mark Shopify privacy compliance PASS.

## What this adds

`backend/app/services/shopify_privacy_synthetic_processor.py` accepts a **durably stored, HMAC-authenticated** `ShopifyPrivacyRequest` receipt. The existing scope preview authenticates the linked tenant/store and original Shopify domain before any subject selection.

- `build_synthetic_customer_export`: builds a **partial** encrypted JSON export containing the matched Shopify store's customer-store profile, orders, order items, shipping fields, conversation previews, messages, and checkout delivery fields for the exact store-local Shopify customer ID. It matches by **Shopify external customer ID** in the original store, *never* by a guessed customer email/phone. It does not export the shared global `Customer` entity because its fields can be shared/merged across stores.
- `plan_synthetic_redaction`: computes aggregate candidate counts for customer or store redaction requests while flagging shared customer records protected from global deletion. **There are no UPDATE or DELETE statements**.
- Both functions require a running pytest test, an explicit synthetic-test opt-in environment flag, and an **SQLite database**. A production PostgreSQL connection is rejected even if the opt-in flag is accidentally set.
- `execute_synthetic_field_redaction` exercises actual field suppression **only** in the same opted-in pytest SQLite sandbox. On the target store alone it clears customer-store external IDs, order shipping address/free-text fields, conversation/message content and checkout name/phone/address/free-text fields; financial/order records and the organization-global `Customer` object remain intact. It flushes but does **not** commit, does **not** change receipt status, and always returns `complete=false`. Its purpose is to validate scoped mutation logic with fabricated records; it must never be wired to a production worker or endpoint.
- No FastAPI routes, cron/worker, external file storage, email delivery, billable Shopify calls, or authorization surface invoke these functions.
- Responses contain no plaintext PII. Export payload is encrypted using the existing Shopify Fernet secret, with limits on rows and payload size.
- Automated fixtures prove export/redaction excludes another store's order notes and conversational checkouts and protects globally shared customer records. Checkout financial/lifecycle fields are retained pending legal retention review.
- Merchant-facing Copilot chat is **not** automatically a customer's conversation. Copilot messages/tools/JSON may contain PII but cannot be attributed solely from a customer email or phone; they remain uncovered until exact subject provenance is implemented.

## Explicitly missing: required before live use

1. **Full inventory and legal schedule:** validate retention/holds, third-party processors, shared-customer provenance and Shopify jurisdictional handling.
2. **All customer data sources:** global profile, AI-derived records, automations, file attachments, S3, message delivery providers, operational logs and backups. The export is explicitly marked `complete=false`.
3. **Independent authenticated delivery authorization:** merchant identity/permissions, subject request correlation, signed download delivery, access expiration and no accidental disclosure in logs.
4. **Background processing:** transactional receipt state transitions, retry/dead-letter logic, retention exceptions and durable audit of actions. Do not acknowledge processing completion merely from a webhook HTTP 200.
5. **Actual selective redaction implementation:** correct field-level anonymization/deletion, shared-record protection, retention exemptions, re-ingestion prevention and backup restoration rules, followed by isolated synthetic E2E and legal review.
6. **Shopify app config:** ensure mandatory compliance subscriptions are deployed on the existing Shopify app via Shopify's app-level configuration, not per-store GraphQL.

## Security gates

The owner approved **development using synthetic data only** in issue #148. This does **not** authorize production data export, deletion, PII disclosure, production deployment, merchant charges or a merge to `main`.

This module is a baseline for engineering/test development only. The next PR will extend controlled subject discovery to all relevant tables and external processors, then design a retention-aware worker that remains disabled until later authorization.

Related: #148, #149.
