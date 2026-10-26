# Shopify privacy — phase 3 evidence traceability review

**Review date:** 2026-10-26
**Result:** **NOT CLOSED** — 0 approved, 2 pending, 29 blocked.
**Scope:** repository evidence-pack review only. No production systems, external evidence vault, provider account, legal approval, or backup environment was inspected or changed. No deletion, export, restore, or other real operation was performed.

## Review method and evidence limits

The backend control registry defines 31 controls: 6 retention, 16 processor, 6 backup/replay/restore, and 3 delivery controls. All 31 names were compared against `backend/app/services/shopify_privacy_controls.py` and are present in `docs/shopify-privacy-evidence-pack-2026-10-26.md`. Each row below records a required evidence item, a proposed responsible role, and an acceptance criterion.

Status terms are deliberately separate:

| Status | Meaning in this review |
| --- | --- |
| **Documented** | The evidence requirement is described in the local pack. This is not proof that the operational control works. |
| **Collected** | The source artifact is in an identified, restricted evidence store and its digest is registered. No artifacts were supplied or made available to this repository review, so every control is `NO / NOT PROVIDED`. This does not assert that no evidence exists elsewhere. |
| **Reviewed** | An authorized reviewer inspected the source artifact independently of its author. None was presented for review. |
| **Verified** | The acceptance criterion was met for the actual applicable scope and signed off by an authorized reviewer. None is verified. |

The evidence vault/location was not identified or made available. Therefore access restrictions, audit logging, retention, artifact integrity, and correspondence between any stored artifact and its registered digest **could not be assessed**. No artifact or digest is included in this repository. Hash existence alone would not establish truth or successful operation.

Every row has the same evidence lifecycle at review time: **Documented: YES; Collected: NO / not provided; Reviewed: NO; Verified: NO**. “Owner” names are proposed role assignments, not confirmed named owners; they must be assigned before evidence collection.

## Control-by-control traceability matrix

**Classification:** `PENDING` means the evidence can be prepared through a bounded internal/synthetic review, but has not been collected. `BLOCKED` means acceptance depends on legal authority, an external provider, real infrastructure configuration, an actual isolated restore, or safeguards that are not implemented. Neither classification means the control has passed.

| Control | Required evidence missing | Proposed responsible owner (assignment) | Acceptance criterion | Current state |
| --- | --- | --- | --- | --- |
| `customer_contact` | Approved scope, purpose/legal basis, retention trigger, deletion rule, exception and expiry | Privacy counsel — unassigned | Authorized counsel approves the decision for relevant jurisdiction and request type; legal holds are explicit | **BLOCKED** — approval missing |
| `financial_orders` | Field-level minimization decision, legal/contract basis, restricted access, expiry/review date | Legal + finance — unassigned | Specific obligation and minimum retained fields are approved; no generic country-based period | **BLOCKED** — approval missing |
| `shipping_and_returns` | Recipient/label/return/tracking data map and disposition/exception decision | Legal + operations — unassigned | Category map, ledger separation, exceptions and expiry are approved | **BLOCKED** — approval missing |
| `conversations` | Treatment for messages, attachments, transcripts, redaction/deletion and exceptions | Privacy counsel — unassigned | Authorized counsel accepts coverage of free text and attachments for applicable scope | **BLOCKED** — approval missing |
| `automations_and_ai` | Data-flow map for prompts, responses, derived data, indexes and queues; unlink/delete and replay rules | Privacy engineering + privacy/legal reviewer — unassigned | Actual surfaces are mapped, residual attribution gaps accepted by authorized reviewers, and exceptions documented | **BLOCKED** — legal/review decision missing |
| `logs_and_audit` | Log-field inventory, access/retention settings, purge evidence and pseudonymous-ID policy | Security + legal — unassigned | Minimized fields, access, expiry and incident/legal exceptions are independently accepted | **BLOCKED** — approval and operational evidence missing |
| `shopify_admin_api` | Applicable data-flow/terms and case evidence distinguishing Shopify source data from DIAGLOB copies | Shopify integration owner + privacy reviewer — unassigned | Actual scope reconciled; applicable provider/source disposition evidence reviewed; exceptions recorded | **BLOCKED** — external/source evidence missing |
| `nuvemshop_admin_api` | Actual activation/data-flow, terms, applicable request and provider response | Commerce integration owner + privacy reviewer — unassigned | Applicable store scope and provider disposition independently reviewed; no activation inferred from counts alone | **BLOCKED** — provider evidence missing |
| `dropi_supplier` | Supplier data flow, terms, deletion/retention request and provider response | Supplier integration owner + privacy reviewer — unassigned | Applicable data and provider response/exception confirmed from original evidence | **BLOCKED** — provider evidence missing |
| `cj_supplier` | Forwarded recipient/order data, terms, request and provider disposition | Supplier integration owner + privacy reviewer — unassigned | Applicable scope and provider response/exception independently confirmed | **BLOCKED** — provider evidence missing |
| `advertising_meta` | Actual account/conversion data flow, terms and any provider disposition; Pixel applicability check | Advertising integration owner + privacy reviewer — unassigned | Actual flow reconciled; Pixel is not claimed active without evidence; applicable response reviewed | **BLOCKED** — external evidence missing |
| `google_workspace_apis` | Connected account/data scope, imported source/derived files, revocation and provider terms | Google integration owner + privacy reviewer — unassigned | Organization scope and relevant source/derived-copy disposition independently reconciled | **BLOCKED** — account/provider evidence missing |
| `whatsapp_provider` | Actual provider identity, message/recipient flow, terms and provider response/exception | Messaging integration owner + privacy reviewer — unassigned | Actual provider and applicable data disposition confirmed from original evidence | **BLOCKED** — provider identity/response missing |
| `telegram_messaging` | Bot/provider identity, message/recipient flow, terms and provider response/exception | Messaging integration owner + privacy reviewer — unassigned | Actual provider and applicable data disposition independently confirmed | **BLOCKED** — provider evidence missing |
| `instagram_messaging` | Account/app scope, message/recipient flow, terms and provider-side disposition | Messaging integration owner + privacy reviewer — unassigned | Actual scope and applicable provider disposition independently confirmed | **BLOCKED** — provider evidence missing |
| `email_delivery` | Actual transactional email vendor, secret-redacted configuration, terms and retention/disposition evidence | Platform/email owner + privacy reviewer — unassigned | Vendor identity is established from authoritative configuration and applicable terms/response are reviewed | **BLOCKED** — manual confirmation required |
| `mercado_pago_payments` | Payment fields/flows, terms, provider response and financial-retention exceptions | Payments owner + legal/finance reviewer — unassigned | Provider scope and financial/contact data separation are independently accepted | **BLOCKED** — provider/legal evidence missing |
| `nequi_payments` | Payment/webhook fields, terms, provider response and retention exceptions | Payments owner + legal/finance reviewer — unassigned | Provider scope and any required financial retention are independently accepted | **BLOCKED** — provider/legal evidence missing |
| `paddle_billing` | Subscription/invoice contact scope, terms, and separation from Shopify buyer data | Billing owner + privacy reviewer — unassigned | Organization billing data is reconciled and not conflated with store-buyer data; exceptions reviewed | **BLOCKED** — external/configuration evidence missing |
| `aws_bedrock` | Region/service config, ingestion/derived-content lifecycle, terms and deletion/retention evidence | AI/Knowledge owner + security/privacy reviewer — unassigned | Actual service scope and derived-data handling are independently reconciled with provider terms | **BLOCKED** — infrastructure/provider evidence missing |
| `files_and_object_storage` | Bucket/version/replication/lifecycle configuration and object/derivative disposition | Storage owner + security reviewer — unassigned | All relevant copies/versions and retention/deletion behavior are evidenced without exposing object keys | **BLOCKED** — infrastructure evidence missing |
| `carrier_logistics` | Actual carrier list, label/recipient/tracking flow, terms and per-provider disposition | Logistics integration owner + privacy reviewer — unassigned | Applicable carriers and their provider-specific disposition/exceptions are independently confirmed | **BLOCKED** — provider inventory/evidence missing |
| `async_automation_queues` | Queue inventory/retention, pause/drain/replay procedure and synthetic replay test outcome | Queue/automation engineering owner — unassigned | Synthetic test covers all queue/retry paths and independently shows suppression/idempotency behavior | **PENDING** — internal evidence not collected |
| `provider_replay` | Webhook/provider retry inventory, idempotency controls and synthetic duplicate/replay test | Integration/webhook engineering owner — unassigned | Test demonstrates retries cannot silently recreate suppressed data across applicable integrations | **PENDING** — internal evidence not collected |
| `database_backups` | Actual backup inventory, encryption/access, retention/expiry and restore evidence | Infrastructure/DB owner + independent reviewer — unassigned | All copies and retention periods are reconciled and an authorized restore test is reviewed | **BLOCKED** — real infrastructure/restore evidence missing |
| `object_storage_backups` | Version/replica/backup inventory, lifecycle/expiry, access and restore evidence | Storage/infrastructure owner + independent reviewer — unassigned | Versions, replicas and provider-managed copies are covered by actual configuration and restore evidence | **BLOCKED** — real infrastructure/restore evidence missing |
| `restore_reconciliation` | Pre-restore external checkpoint, isolated restore result, post-restore comparison and ingestion gate proof | Independent restore operator + security reviewer — unassigned | Checkpoint predates restore, origin/custody is independently verified, mismatch handling is demonstrated, and ingestion stayed blocked until pass | **BLOCKED** — no real isolated restore evidence |
| `tombstone_offsite_ledger` | Ledger access/append-only evidence, key custody/recovery, retention and recovery test | Security/key-custody owner + independent reviewer — unassigned | Expected checkpoint is demonstrably independent of the tested backup and recoverable through key/restore procedures | **BLOCKED** — custody/access evidence missing |
| `merchant_identity` | Verified merchant recipient and authority bound to exact organization/store/case | Privacy operations owner + independent identity reviewer — unassigned | Recipient identity and authorization are verified for the precise scope without cross-tenant ambiguity | **BLOCKED** — verified delivery workflow/evidence absent |
| `secure_delivery` | Implemented threat model, authenticated encrypted transport, expiry, single-use access, revocation and purge tests | Security/engineering owner + independent reviewer — unassigned | All delivery safeguards are implemented and independently tested before any live export | **BLOCKED** — production delivery workflow is not enabled/verified |
| `closure_audit` | PII-minimized audit design and test evidence for delivery/disposition, exceptions and expiry | Security/privacy operations owner + independent reviewer — unassigned | Audit proves the reviewed outcome without recording PII, secrets, or export contents | **BLOCKED** — implementation and review evidence missing |

## Summary and evidence-handling result

| Classification | Count | Controls |
| --- | ---: | --- |
| Approved / verified | **0** | None |
| Pending | **2** | `async_automation_queues`, `provider_replay` |
| Blocked | **29** | All 6 retention, all 16 processor, 4 backup/restore, and all 3 delivery controls |

- **Inventory integrity:** 31/31 backend control names are represented. Each row has an evidence requirement, proposed responsible role, acceptance criterion, and status. Role assignment itself remains outstanding.
- **Evidence lifecycle:** all 31 are documented in the checklist only; no evidence was provided to this review, and none is marked collected, reviewed, or verified.
- **Sensitive evidence:** no artifacts were added to Git. Because the evidence vault was not available, restricted access, audit trail, retention, and digest-to-artifact integrity remain **unassessed**, not passed.
- **Third parties/legal:** applicable controls remain blocked until the authorized counsel/provider evidence is obtained and independently reviewed. `not_detected` activation does not establish non-use or non-disclosure.
- **Backups:** no backup/restore control is verified without evidence from the actual system and a reviewed restoration. The local HMAC utility or a caller-supplied digest alone is insufficient.
- **No real actions:** this review performed no customer deletion/export, provider request, production backup/restore, production configuration change, or production deployment.

## Closure rule

Do not close phase 3 on the basis of this matrix or the existence of the package. A control may move to `COLLECTED` only after a redacted artifact is placed in an identified restricted evidence store and its digest is registered. Move to `REVIEWED` only after a different authorized reviewer inspects the source. Move to `VERIFIED` only when that reviewer records that the row's acceptance criterion is met for the actual scope. Legal, provider, backup, secure-delivery, and Shopify PCD gates remain blocked until their specific external dependencies are satisfied. Keep application fulfillment and execution flags fail-closed throughout.
