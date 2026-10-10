# Shopify privacy request inbox — development implementation

Status: **durable encrypted request intake implemented**, but **privacy processing is not complete**. This feature must not be represented as Shopify data-subject request fulfillment.

## Data flow

1. Shopify sends an app-level `customers/data_request`, `customers/redact` or `shop/redact` HTTPS callback.
2. FastAPI validates Shopify HMAC over the original raw request body and the topic.
3. The handler validates the Shopify shop identity and retains only minimum subject/order selectors.
4. The selectors are encrypted using DIAGLOB's existing `SHOPIFY_TOKEN_ENCRYPTION_KEY` before entering the database.
5. A unique SHA-256 receipt ID is derived from topic + shop ID/domain + Shopify `X-Shopify-Webhook-Id` header. If Shopify omits that header, a canonical payload-hash fallback is used, which can coalesce genuinely distinct legacy requests with identical content.
6. The database transaction commits an immutable request record before sending an HTTP 200 acknowledgement. Parallel duplicate delivery is handled by a unique constraint plus `IntegrityError` recovery.
7. If an active Shopify connection resolves exactly to the callback shop domain, store and organization numeric IDs are copied to the receipt. If it doesn't, the request is stored with null tenant binding. **Do not infer tenant ownership from email, phone, arbitrary domains, or unverified store names.**
8. Status starts at `pending_policy_review`; NO automatic export or deletion occurs.

A valid request returns a PII-free receipt; the API never returns decrypted selectors. Signature failures receive 401. Storage or encryption failures receive non-2xx so Shopify can retry; logs must never include a raw subject.

## Persistence

Table: `shopify_privacy_requests`; migration: `a4e5f6a7b8c9` (after `b4d5e6f7g8h9`).

Important: The receipt must survive merchant disconnects. This table deliberately has no ON DELETE CASCADE on organization/store references. Identifiers are nullable on uninstalled/unknown shops; missing tenant mapping needs human review before executing any privacy operation.

The OAuth token-encryption key is reused for the selector blob. Provision it through existing approved secret management. Do not check the key into the repository or log it. Encryption/key rotation and retention of receipts themselves require separate lifecycle validation.

## Remaining blockers

- Implement a **durable worker** and administrative review interface restricted to authorized personnel. Persist state transitions, attempts, failure codes and timestamps transactionally.
- Produce **controlled subject data export**, and selective **redaction/erasure** with shared-customer checks for other stores. Handle all configured data processors, backups, reingestion and accounting/legal holds.
- Validate all retention periods and jurisdiction-specific exceptions. Owner-approved policy is only provisional and authorizes **synthetic-data development**, not real customer deletion.
- Reconcile orphaned/unknown-shop receipts after uninstall only with trusted store identity evidence.
- Register the mandatory privacy topics on the **existing Shopify app** at app level; `shopify.app.toml` is not yet linked or deployed.
- Verify migration up/down with an isolated DB; run backend test suite and current-head CI.
- The endpoint must not be activated for live Shopify review until the fulfillment workflow is real and legal requirements are met.

Related: PR #149, stacked PR #150, issue #148.
