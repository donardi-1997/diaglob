# Shopify privacy — acceptance gates for DIAGLOB

**Status: NOT READY FOR LIVE FULFILLMENT / NOT APPROVED.**
Engineering review updated 2026-10-14. This document is a release checklist, not a legal approval or Shopify review response.

## Regulatory and Shopify scope

Shopify requires signed callbacks and verified app subscriptions for:
`customers/data_request`, `customers/redact` and `shop/redact`.
Respond to authenticated callbacks with 2xx only after durable intake; invalid HMAC
requires 401. The substantive action is due within 30 days after receipt,
except deletion prohibited by an applicable legal record-retention obligation.
See https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance

The webhook response is **not** the customer-data export and is not evidence
that erasure/delivery or downstream vendor work succeeded.

## As-built, from repository code (not a live Shopify check)

| Area | Implemented | What the result does NOT prove |
|---|---|---|
| Signed webhook intake | Raw-body HMAC route, encrypted selectors, durable receipt, queue and idempotent retry | Active app-level subscriptions or fulfillment |
| Per-case assessment | Signed receipt, org/store mapping, opaque IDs, counts, coverage blockers | Exact ownership for unlinked/free-text records |
| Local access | Scoped partial in-memory ciphertext; separate counts-only operator inspection that never builds an export | Complete export or authenticated merchant delivery |
| Local erasure | Scoped field manifest; synthetic-only field suppression | Lawful production erasure or exceptions |
| Reimport prevention | Staged HMAC tombstones and selected ingress checks | Enabled suppression on every entrypoint and after restore |
| Processor evidence | Unverified opaque SHA-256 artifact references | Vendor deletion or export verified independently |
| Secure delivery | Short-lived single-use synthetic vault | Real recipient authentication, hosted artifact or merchant receipt |
| Deployment | Production endpoint and prior invalid-HMAC probes | Live subscribed Shopify deliveries and disaster recovery |

PR #249 strengthens identity mapping and cross-store order-item integrity,
and compares every requested shop ID/domain/tenant/store with prior
**HMAC-audited** requests. Any signed history conflict blocks scope preview
before customer selectors or records are read; a PII-free
`SHOPIFY_SIGNED_SHOP_HISTORY_CONFLICT` blocker appears in case assessment.
A history-consistent request is **not** proof of an independently verified
Shopify Admin shop ID. After an authenticated app/uninstalled webhook, a new
`shopify_privacy_shop_identities` ledger persists the signed Shopify shop ID,
domain, organization and store without a foreign key to the now-disconnected
store. Subsequent signed compliance requests recover the original tenant/store
ONLY when both Shopify identifiers match exactly and historical ownership has
not changed. The ledger is populated atomically with the GDPR receipt or
uninstall revocation, and stores no buyer selectors, merchant tokens or PII.
`store_connected=false` remains accurate after recovery, while
`store_identity_resolved=true` denotes an auditable historical link.
Missing mappings, store deletion, drift or unresolved subjects still block
data export, redaction and case completion. The bridge cannot recover a shop
disconnected before the first signed event without external historical evidence;
it never invents a link from email, phone or a matching domain alone.

## Release gates — ALL must be checked independently

1. **Subscription/version:** verify active Shopify app ID/version, exactly 3 compliance topics and HTTPS destination using Shopify Dashboard (not just TOML); test valid and invalid HMAC against isolated staging and document request IDs without PII. Note that `shopify app webhook trigger` does not verify active subscriptions.
2. **Identity/provenance:** for each request bind original signed shop ID/domain to an immutable install/store/tenant record; block missing, duplicate or rotated identity; respect order selectors. Email-only callbacks require an independently approved manual identity workflow, never automatic matching.
3. **Data surface completeness:** enumerate all table columns and external data sources, including global/shared customers, orders/items, attachments, conversations, automations, AI outputs/Copilot, provider queues, S3/KB, application logs and analytics. Unclassified or unlinked data blocks final completion.
4. **Legal retention:** approve region-specific field/category retention policy, financial exceptions, legal holds, purpose and deletion/anonymous-replacement semantics. Attach approved evidence from legal/finance/security; a SHA-256 digest is only a reference.
5. **Third parties:** for WhatsApp, Instagram, email, advertising, shipping/CJ/Dropi, AWS Bedrock, object storage and subprocessors, record actual data shared, supplier deletion/export capacity, API result or signed manual exception, and completion IDs. Absence of confirmation is not completion.
6. **Export:** authenticate merchant recipient independently (not caller-supplied email/webhook subject); bind authorization to exact shop/subject/case; encrypt artifact in a separate protected store, enforce one-use/revocation/short expiry, purge ciphertext, and log a PII-free delivery confirmation. Test unauthorized access, parallel redemption, replay, expiration and multi-shop boundaries.
7. **Redaction:** approve plan with field-level legal exceptions and independent authorization. Mutate only owned store-level fields, preserve legally required records, verify every source and child relation, prevent re-ingestion, and maintain a per-source retry/checkpoint trail. Never set completed just because the local DB was updated.
8. **Recovery:** identify database disk/snapshots/object versions, apply retention exceptions, keep HMAC suppression ledger outside the restored backup, run a restore drill, and verify that deleted data cannot reappear when queues and supplier events replay.
9. **Completion:** independent verifier checks evidence for every source and authorized delivery; only then move case to a terminal state with a PII-free audit event. Alert before the 30-day Shopify action deadline and escalate unresolved cases.
10. **Protected customer data:** request only the Shopify data/fields necessary for shipped features through Partner, with matching data protection details; development store permissions are not an App Store approval.

## Next engineering work (no AWS change needed now)

- Add explicit historical `shop_id` provenance to installation binding and a replay-safe after-uninstall resolution model; current store/domain-only verification is insufficient to authorize destructive processing.
- Implement subject-to-record provenance for merchant Copilot/free-text, KB documents, automation payloads, attachments, provider calls and logs. Do not infer a Shopify ID from phone/email similarity.
- Implement independent human sign-off + recipient authentication + secure encrypted delivery and redaction execution behind an operator-controlled release gate; prove with isolated fixtures before enabling any production path.
- Execute the three webhook topics end-to-end with signed staging deliveries and database assertions, then independently verify the active Shopify app version/subscriptions.

## Regression tests for PR #249

```bash
cd backend
pytest -q tests/test_shopify_privacy_scope_preview.py \
          tests/test_shopify_privacy_case_assessment.py \
          tests/test_shopify_privacy_local_processor.py
ruff check app/services/shopify_privacy_scope_preview.py \
    app/services/shopify_privacy_local_processor.py \
    app/services/shopify_privacy_synthetic_processor.py \
    tests/test_shopify_privacy_scope_preview.py \
    tests/test_shopify_privacy_case_assessment.py \
    tests/test_shopify_privacy_local_processor.py
```

**Operational constraint:** merging `main` triggers Lightsail deployment.
Do not merge a privacy change while SSH/restore is inaccessible. No new AWS
instance, snapshots, data migrations, real export or destructive operation
is authorized by this document. The reviewer must capture commit, workflow
URL and approved staging evidence before changing release flags.

Official references:
- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/launch/protected-customer-data
- https://shopify.dev/docs/apps/build/webhooks/subscribe
