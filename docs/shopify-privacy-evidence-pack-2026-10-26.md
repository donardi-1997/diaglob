# Shopify privacy — evidence pack and independent review checklist

**Status:** operational draft; **not** legal approval, independent verification, proof of provider deletion, or Shopify/PCD approval. See the [traceability review](shopify-privacy-traceability-review-2026-10-26.md) for per-control status and evidence gaps.
**Scope:** advance the evidence work for phase 3 without enabling real export, erasure, delivery, backup mutation, or production restore operations.

This pack maps the existing backend control registry to evidence that an authorized reviewer can collect and assess. A control stays open until the evidence is independently reviewed through an approved process. A document hash proves only that a particular file has a particular digest; it does not prove that the document is true, complete, current, or accepted by a provider.

## Rules for collecting and handling evidence

1. Do not place evidence artifacts, secrets, customer selectors, order details, message content, credentials, or unredacted provider screenshots in Git, tickets, chat, or CI logs.
2. Store source artifacts in an access-controlled evidence location with an owner, retention date, and audit trail. Store only the SHA-256 digest in the application evidence registry.
3. Prefer synthetic test evidence for implementation behavior. Synthetic evidence cannot prove production configuration, processor action, legal approval, or backup coverage.
4. Record the reviewer separately from the evidence author. For legal and provider confirmations, the reviewer must have the relevant authority and inspect the original source, not only its digest.
5. Preserve the backend's fail-closed result. Evidence submission currently returns `verified: false`; it does not approve retention, authorize deletion or delivery, clear blockers, or set `fulfillment_complete`.
6. For actual customer cases, use only the exact signed case and verified store scope. Minimize the evidence to what the reviewer needs; redact unrelated people and stores.

## Evidence register template

Create one row per control and per case/scope. Do not mark a row verified merely because a file or digest exists.

| Field | Required value |
| --- | --- |
| Case reference | Opaque Shopify privacy request ID; do not add customer name/email/phone |
| Control | Exact backend control name from the matrices below |
| Scope | Store or organization; identify the verified scope without copying personal data |
| Evidence artifact | Restricted location/reference; never a public URL |
| SHA-256 | Digest of the final, redacted artifact |
| Evidence author / date | Person or system that produced it and UTC date |
| Independent reviewer / date | Different authorized reviewer, or `PENDING` |
| Acceptance result | `PENDING`, `ACCEPTED`, or `REJECTED`, with a short non-PII reason |
| Expiry / next review | Date the evidence or provider configuration must be rechecked |
| Follow-up | Open exceptions, legal hold, provider response, or remediation reference |

## 1. Retention and legal-hold decisions

Backend control names come from `RETENTION_CONTROLS`. The proposed behavior in the code/policy is not an approved schedule. Counsel and the relevant business owner must decide scope, jurisdiction, legal basis, exceptions, and expiry before any real deletion or retention mutation.

| Control | Required evidence to collect | Reviewer / acceptance gate |
| --- | --- | --- |
| `customer_contact` | Approved decision for contact fields and addresses: purpose, legal basis, retention trigger, deletion/disassociation rule, exception and expiry | Privacy counsel accepts the decision for the applicable jurisdiction and case type |
| `financial_orders` | Decision separating personal fields from records that must be retained; minimum retained fields, legal/contract basis, restricted access, expiry/review date | Legal + finance confirm the specific obligation; no generic country-based retention period |
| `shipping_and_returns` | Retention/disposition decision for recipient, label, return, and tracking data; separation from financial ledger | Legal + operations accept the category map and exception handling |
| `conversations` | Approved treatment of message text, attachments, transcripts, and support records; redaction/deletion criteria and exception rules | Privacy counsel confirms the treatment covers free text and attachments |
| `automations_and_ai` | Data-flow map for prompts, responses, derived data, indexes, queued payloads, and automations; unlink/delete rule and replay prevention | Privacy engineering documents coverage; privacy/legal independently accepts residual gaps |
| `logs_and_audit` | Log-field inventory, access/retention configuration, purge evidence, and policy for pseudonymous identifiers | Security + legal accept minimization, access, retention, and incident exceptions |

**Acceptance checklist:** approval is attributable to an authorized reviewer; document version and effective date are present; case/store applicability is explicit; legal holds and unresolved exceptions are addressed; no blanket completion is inferred from local table processing.

## 2. External processor evidence

The manifest has 16 entries. Connection counts indicate possible activation only; `not_detected` is not proof that no data was shared, and organization-scoped services may be relevant to more than one store. For each applicable entry collect: current contract/DPA and service scope; actual activation/data-flow evidence; transfer/region details where applicable; deletion or retention request reference; provider response/confirmation (or documented inability to obtain one); residual backups/retention exceptions; and independent review. Do not submit a mock response as provider confirmation.

| Control | Processor / service | Scope | Evidence focus |
| --- | --- | --- | --- |
| `shopify_admin_api` | Shopify Admin API | Store | Relevant data flows and Shopify privacy webhook/case evidence; distinguish Shopify's source records from DIAGLOB copies |
| `nuvemshop_admin_api` | Nuvemshop Admin API | Store | Store connection, transferred order/customer fields, provider-side request and response where applicable |
| `dropi_supplier` | Dropi | Store | Supplier order/shipping data shared, deletion/retention request and provider response |
| `cj_supplier` | CJ Dropshipping | Store | Forwarded order/recipient data, fulfillment/tracking copies, deletion/retention confirmation |
| `advertising_meta` | Meta Ads | Store | Account sync and any actual conversion/advertising data flow; explicitly confirm Meta Pixel is not represented as active by this manifest |
| `google_workspace_apis` | Google Drive and Sheets APIs | Organization | Connected account scope, imported file/sheet inventory, revocation and source/derived-copy handling |
| `whatsapp_provider` | WhatsApp Business provider | Store | Provider identity, message/recipient data flow, retention/deletion request and provider response |
| `telegram_messaging` | Telegram Bot API | Store | Bot/provider identity, message/recipient data flow, retention/deletion request and provider response |
| `instagram_messaging` | Instagram Messaging | Store | Account/app scope, message/recipient data flow and provider-side disposition evidence |
| `email_delivery` | Transactional email provider | Manual confirmation | Identify the actual provider from deployment configuration, delivery logs/configuration with secrets removed, and provider terms/retention; detector does not infer activation |
| `mercado_pago_payments` | Mercado Pago | Store | Payment data fields and transaction references; distinguish required financial retention from removable contact data |
| `nequi_payments` | Nequi | Store | Payment/webhook data flow and provider retention/deletion response; distinguish financial record obligations |
| `paddle_billing` | Paddle | Organization | DIAGLOB subscription/invoice contact scope; keep app billing records distinct from Shopify buyer data |
| `aws_bedrock` | AWS Bedrock knowledge bases | Organization | Region/service configuration, knowledge-base ingestion and derived-content lifecycle, provider retention terms and deletion evidence |
| `files_and_object_storage` | S3 object storage | Organization | Bucket/version/replication/lifecycle configuration, object and generated-artifact disposition; never include object keys in public evidence |
| `carrier_logistics` | Carrier logistics network | Store | Actual connected carriers, label/recipient/tracking data, provider-specific disposition and exceptions |

**Important:** `PROCESSOR_CONTROLS` completeness is a code invariant, not proof that this is the complete legal vendor list. Reconcile the manifest against current deployment configuration, contracts, billing records, observability, support tools, and actual data flows. Add newly discovered processors through reviewed code and controls before claiming completeness.

## 3. Backup, replay, and restore evidence

The application does not operate or inspect the production backup systems. Obtain configuration and run evidence from the actual database, object-storage, queue, and provider operators. A successful suppression-ledger HMAC reconciliation covers only that ledger comparison; it does not prove that backups expired, customer data was erased from backups, or reingestion is safe.

| Control | Required evidence | Acceptance gate |
| --- | --- | --- |
| `async_automation_queues` | Queue inventory and retention; pause/drain/replay procedure; synthetic replay test showing suppression/idempotency behavior; timestamped outcome | Engineering reviewer verifies all production queue types and failure/retry paths are covered |
| `provider_replay` | Webhook/provider retry inventory; idempotency/replay controls; synthetic duplicate/replay test and operational response | Integration owner verifies no replay can silently recreate suppressed data |
| `database_backups` | Actual backup products/locations, encryption and access configuration, retention/expiry settings, deletion/expiry run evidence, and a restore test | Infrastructure owner plus independent reviewer confirm all copies and retention periods, not only the primary snapshot |
| `object_storage_backups` | Versioning/replication/backup inventory, lifecycle and expiration configuration, access boundary, deletion/expiry evidence, and restore test | Storage owner confirms versions, replicas, generated artifacts, and any provider-managed copies |
| `restore_reconciliation` | Pre-restore checkpoint from a separately controlled append-only ledger; restore timestamp/environment; drill result and post-restore comparison; reingestion gate evidence | Independent operator confirms checkpoint predates the restore and ingestion stayed blocked until reconciliation; the current endpoint labels origin caller-attested and is not independent verification |
| `tombstone_offsite_ledger` | Ledger location/control owner, append-only/access-control evidence, key custody/recovery procedure, checkpoint age and retention, and recovery test | Security reviewer verifies the expected checkpoint cannot be sourced from the backup under test and survives key/restore procedures |

**Safe drill sequence:** use a non-production restore target and synthetic data; isolate it from webhooks, queues, and provider sync; capture/confirm the external checkpoint before restore; restore; run the reconciliation utility; investigate any mismatch; prove suppression/replay handling before reopening ingestion; retain a redacted report. Do not perform a production restore or pause live processing as part of this checklist without explicit operational approval and a recovery plan.

## 4. Secure delivery controls and safeguards

These gates are separate from processor/backup evidence and are currently not implemented as a real production delivery workflow. Do not transmit actual customer exports while any gate is open.

| Control | Evidence required before design/enablement |
| --- | --- |
| `merchant_identity` | Independently verified recipient identity and authorization for the exact organization, store, and case |
| `secure_delivery` | Threat model and tested encrypted, authenticated, short-lived, single-use transport with revocation and purge |
| `closure_audit` | Audit design proving delivery/disposition and exceptions without logging PII, credentials, or export contents |

Required safeguards from `shopify_privacy_delivery_readiness.py`: `authenticated_merchant_recipient`, `recipient_tenant_and_shop_binding`, `encrypted_artifact_at_rest`, `short_lived_single_use_download`, `authenticated_access_and_revocation`, `minimal_audit_without_personal_data`, `scheduled_artifact_purge`, and `independent_delivery_confirmation`. Each needs an implementation reference and independent test/review before live delivery is considered.

## 5. Artifact hashing and backend recording

Finalize and redact the source artifact before hashing it. Example local commands:

```powershell
(Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
```

```bash
sha256sum /restricted/evidence/artifact.pdf
```

The internal evidence endpoint is:

```text
POST /api/internal/shopify/privacy/cases/{request_id}/controls/{control}/evidence
JSON: {"artifact_sha256":"<64 lowercase hex characters>"}
```

Use the internal secret only through an approved secret manager/runtime, never a checked-in file or shell history. Submit only after confirming that the request is signed and the control name matches the registry. The response is evidence bookkeeping (`recorded`, `verified: false`), not reviewer sign-off. Recheck the case controls/readiness afterward and preserve all unresolved blockers.

## 6. Status and phase-3 exit criteria

| Gate | Current honest status | Exit evidence |
| --- | --- | --- |
| Local inventory and processor/backup control registry | Implemented and deployed; code tests do not attest production configuration or completeness | Versioned code/test references plus a production-safe, read-only configuration reconciliation |
| Legal retention / holds | Approval pending | Signed decision by authorized counsel/legal owner for categories, jurisdictions, exceptions, and review dates |
| Processors | Independently unverified | Reconciled vendor list, applicable terms, case-specific provider disposition, and reviewer sign-off for each applicable processor |
| Real backups and expiry | External configuration/evidence pending | Complete database/object-store copy inventory, verified retention/expiry, and restore evidence |
| Offsite tombstone ledger and restore | Drill may reconcile a supplied checkpoint; checkpoint origin remains caller-attested until independently reviewed | Independent custody/access review plus isolated restore/replay drill and signed outcome |
| Secure export/delivery | Not authorized; production safeguards remain a release gate | Implemented and independently tested safeguards, verified merchant recipient, and approved per-case authorization |
| Shopify PCD / listing | Shopify decision pending | Current Partner Dashboard result and reviewer decision; repository artifacts cannot grant approval |

**Do not report phase 3 as externally closed** until the applicable exit evidence is independently reviewed. No evidence file or digest in this pack changes the service's fail-closed flags or authorizes real processing.
