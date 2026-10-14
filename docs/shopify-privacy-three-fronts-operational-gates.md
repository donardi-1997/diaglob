# Shopify privacy: manual ingress, retention decisions, external processors and restore gates

Date: 2026-10-14. This is an **implementation/runbook**, not a legal opinion,
proof of processor deletion or Shopify App Store certification.

## 1. Alternate ingress and queued executions

The HMAC-keyed tombstones remain **staged** until a separate authorized
production erasure mechanism is approved. Production activation is not
implemented. When active tombstones exist, these code paths now re-evaluate
the original store-bound customer/profile/phone/email/order identity:

| Path | Enforcement |
|---|---|
| Shopify order webhook | Existing signed-webhook suppression check before writes |
| Draft order creation | Reject before local intent and external Shopify mutation |
| Chat-based Shopify COD order | Reject before local intent and external Shopify mutation |
| Flow Builder queued recipient | Re-check after lease claim, before sending WhatsApp/calls/tools |
| Legacy WhatsApp automation | Re-check at send time |
| CJ automatic fulfillment enqueue | Re-check before enqueueing supplier job |
| CJ automatic fulfillment execution | Re-check before supplier lookup/transmission |

A remote Shopify customer ID is resolved only via the exact local
`CustomerStoreProfile` for that store. If no remote ID exists, the checker
uses only the customer email/phone as potential HMAC tombstone matches, not
as permission to merge identities. It refuses to process fully unresolved
identities when active tombstones exist. Existing queued recipient executions
are marked failed with `privacy_suppressed` to prevent provider contact;
supplier jobs are skipped with the code `PRIVACY_SUPPRESSED`.

**Not all ingress is covered.** Direct WhatsApp/Instagram message ingestion,
agent tool calls, supplier-provided updates, other commerce platforms,
historical exported file artifacts, and custom manual database writes still
require an audited entrypoint inventory and suppression enforcement. Do not
declare replay prevention complete.

## 2. Retention and legal-hold decisions

Shopify asks apps to fulfill compliant requests within **30 days**, but
redaction has a statutory-retention exception:
https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance

Colombian personal-data law (Ley 1581 de 2012) regulates deletion, security
and the duties of processors:
https://normograma.dian.gov.co/dian/compilacion/docs/ley_1581_2012.htm

Specific fiscal evidence may require preservation under applicable tax rules
(including article 632 of the Estatuto Tributario); this is **not** a generic
five-year rule for all buyer data:
https://normograma.dian.gov.co/dian/compilacion/docs/oficio_dian_9040_2026.htm

The new `shopify_privacy_controls.py` exposes a decision matrix requiring
review by legal/finance/security/operations, **not** hardcoded retention dates.

| Record group | Proposed treatment pending legal review |
|---|---|
| Customer contact and delivery PII | Delete/anonymize fields if no valid hold |
| Financial orders / audit trail | Separate tax/financial proof from unnecessary identity |
| Shipping, refunds and returns | Preserve only evidence needed for active obligations |
| Conversations and attachments | Remove content and linked identifiers after review |
| Marketing/automations/AI derived data | Deactivate jobs, remove derived personal data, enforce source linkage |
| Operational logs and backups | Minimize access, prevent replay, define expiration/erasure controls |

Required **external human decision** for every category: controller/processor
role, jurisdiction, legal ground and document class, hold status, precise
retention start/end if applicable, anonymization strategy, exceptions,
approver identity, and evidence held in a controlled location.
No legal authorization is created by submitting an artifact reference.

Internal authenticated API (no subject PII):

- `GET /api/internal/shopify/privacy/cases/{request_id}/controls`:
  all category controls, owner roles, external and backup checklist, open flags.
- `POST /api/internal/shopify/privacy/cases/{request_id}/controls/{control}/evidence`
  with JSON body `{"artifact_sha256":"<64 lowercase hex>"}`:
  append an **unverified** external proof reference. This does not set
  `retention_approved`, `closure_ready` or `fulfillment_complete`.

## 3. Third-party and restore evidence

External-provider controls are intentionally marked **verification required**
until the responsible processor provides actual erasure, retention or
non-possession evidence. The candidate surfaces include WhatsApp, Instagram,
email, CJ and Dropi suppliers, Meta, Amazon Bedrock, files/object storage,
and internal queues. Not every candidate provider is necessarily connected
for a given store: record non-applicability with a reviewed justification.
Never claim an external provider has deleted data from a local unit test.

Backup/restore controls: automation queue replays, supplier replay, database
backups, object-storage backups, tombstone offsite ledger, and restoration
reconciliation. Do not put raw buyer selectors, emails, orders, or decrypted
payloads in evidence records or CI logs.

### Independent tombstone checkpoint

The service `shopify_privacy_restore.py` creates an HMAC over ALL staged and
active tombstones, including tenant/store scopes, original-domain digests and
status. The checkpoint itself is opaque and *pseudonymous*, not an approval
token or proof that AWS/provider backups have been deleted.

An operator can capture it before backup/recovery:

```bash
cd backend
python -m tools.shopify_privacy_restore_check snapshot
```

Persist `checkpoint_hmac` and `total_records` **outside** the same database
and all snapshots being checked, in a write-once, separately access-controlled
location (future integration: immutable S3 Object Lock or equivalent). Record
timestamp and database version alongside the external artifact. Do not copy
private signing keys to that ledger.

**After restoration and before enabling write traffic**, retrieve the
external checkpoint from the independent ledger and verify:

```bash
cd backend
python -m tools.shopify_privacy_restore_check verify \
  --expected-hmac "<independently retrieved HMAC>" \
  --minimum-records <independently retrieved row count>
```

When available to the backend deployment, also set
`SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC` and
`SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS` **from that external source**, not
from the restored database. These activate fail-closed checks before Shopify
webhook and local order/automation ingress. A restored snapshot lacking even
staged tombstones fails verification.

Key rotation, mismatched rows and altered suppression state also fail closed.
Updating the ledger/checkpoint after staging a new tombstone must be
controlled and atomic with deployment policy. No startup-level mandatory
external ledger integration is implemented yet, so this is **not a guarantee
against all backup rollbacks in production**. Until the independent ledger is
operational, production tombstones must remain unactivated.

## Release gates (all currently blocked)

1. Legal approval for each field group, with documented retained subset
   and hold treatment (no arbitrary deletion of fiscal transactions).
2. Secure authenticated merchant delivery of customer access results.
3. Verified erasure/retention outcomes for all applicable providers,
   content stores, AI records, logs, queues, backups and reimports.
4. Offsite checkpoint ledger wired to deployment, startup and restore runbook,
   followed by an actual restore/replay disaster-recovery drill.
5. End-to-end signed Shopify privacy callbacks and 30-day SLA alerting.
6. Independent privacy officer authorization for destructive actions and
   completion-state transition.

Tests exercise these paths using synthetic SQLite fixtures; no live Shopify
orders are deleted and no customer information is sent to providers.
