# DIAGLOB — Shopify privacy data inventory and ownership (engineering review)
Audit: 2026-10-10 · PR #149 · Owner: ChatGPT (technical review) · **NOT a live-data compliance certificate**

## Scope and evidence
Reviewed the PR branch implementations in `backend/app/services/shopify_privacy_inventory_coverage.py`, `shopify_privacy_scope_preview.py`, `shopify_privacy_synthetic_processor.py`, `shopify_privacy_automation_provenance.py`, `shopify_privacy_copilot_impact.py`, `backend/app/model_domains/shopify_privacy.py`, `backend/app/shopify_oauth.py`, and existing privacy documents. This is a **code/schema inventory**, not a count of production records, AWS buckets, processors, or verified deletion capabilities. Existing ORM heuristic cannot detect personal data hidden in JSON, free text or derived AI output.

**Trust boundary:** Shopify request signed HMAC → immutable request digest and encrypted selector → original shop ID/domain and tenant/store verification → exact Shopify customer external ID (when present) → store-scoped linked rows. Never identify a customer by free-text matching of email/phone; some Shopify callbacks legitimately include only email, so require an explicitly approved fallback workflow rather than silently claiming complete fulfillment.

## Coverage matrix

| Data surface | Likely personal-data categories | Provenance / ownership | Existing capability on branch | Required completeness work |
|---|---|---|---|---|
| `shopify_privacy_requests` / `shopify_privacy_audit_events` | encrypted selectors, shop identifiers, action metadata | receipt surviving disconnect/uninstall | encrypted inbox, PII-minimal audit, backlog and review preview | retention of selectors, evidentiary access, audited terminal state, deletion of selectors after lawful period |
| `customers` | shared name, phone, identity | organization-wide, potentially shared across stores | **uncovered**; preserved in synthetic store redaction | customer-store provenance and safe per-source partial redaction, never global delete from one store request |
| `customer_store_profiles` | Shopify customer ID, counters and link fields | exact organization + store + external customer ID | partial synthetic export/redaction | field-by-field export and lawful disposal incl. anonymized foreign-key behavior |
| `orders` / `order_items` | shipping address, note, line items, external references | exact organization/store, customer via FK | partial synthetic export; financial records preserved | data-request order IDs, financial/legal retention categorization, free-text PII, logistics attachments |
| `conversations` / `messages` | buyer text, previews, provider message IDs | store + customer via conversation | partial synthetic export/redaction | all message payloads, outbound-provider copies, queue + retries |
| `conversational_checkouts` | shipping/name/phone/address, fulfillment/free text | store + customer FK | partial synthetic field suppression | linked delivery providers, failures/metadata, treatment of retained financial state |
| `automations`, campaigns, runs, node executions, recipient deliveries | message templates, recipient payloads, trigger context, provider IDs, errors | mixed store/campaign/recipient links | aggregate counts for some linked rows, **not export** | capture customer provenance at ingestion; queued/live and historical executions, replay prevention |
| `agent_chat_sessions`, messages/tool calls, approvals | merchant conversations containing copied buyer information | merchant actor and store, **not buyer-subject key** | store-wide possible-impact counts only | explicit typed subject lineage in tool results, structured redaction, no free-text matching |
| `knowledge_sources`, customer risk reports/disputes | uploaded files, embeddings, derived classifications | organization/shared/external | uncovered | object and processor inventory, provenance, export/delete API, shared-entity rights |
| `auto_fulfillment_jobs` / order logistics integrations | fulfillment recipient/shipping payloads | store/order plus external provider | uncovered | processor copies, retry queues and legal shipping records |
| S3/object storage and AWS knowledge ingestion | documents, cached exports, embeddings, artifacts | keys and ingestion lineage not verified | **outside ORM inventory** | inventory buckets/prefixes, access logs, TTL, deletion verification and reindex |
| Bedrock / model providers | prompts, retrieved context, inference traces | source and subject lineage not verified | outside ORM inventory | log retention, contract/data processing review, traces and derived data |
| WhatsApp/Instagram/email/provider delivery | phone and outbound contents | external message ID and receiver | outside ORM inventory | inventory processors and opt-out/erasure methods; receipts and provider retention |
| Dropi/supplier/shipping/carrier systems | buyer contact/shipping details | payload lineage and provider contract | outside ORM inventory | prove which personal fields transmitted; export/delete/hold evidence |
| Meta/TikTok/analytics | identity/events/consent tokens | channel and consent purpose | outside ORM inventory | actual deployment verification, consent mapping, processor transfers/retention |
| application logs, monitoring, backups, restores | possible PII in error traces or snapshots | operational infrastructure | outside ORM inventory | masking, TTL, snapshot inventory, deletion-on-restore |

## Non-negotiable subject coverage rules

1. Correlate signed Shopify callback, original `shop_id`, canonical `.myshopify.com` domain, organization and store. Fail closed on ambiguity, missing binding, cross-tenant joins, or different shop identity.
2. For customer requests use verified **external Shopify customer ID**. Shopify `orders_requested` / `orders_to_redact` must be reconciled against exact Shopify order identity; an unlinked order is an exception, never counted as resolved.
3. A global `customers` row linked to multiple stores cannot be deleted or exported in full just because one store customer identifier matched. Resolve source-level, store-local fields and shared legal basis separately.
4. Count-only, metadata-only and synthetic previews **cannot** close a real request. All unclassified tables, external processors, attachments, log/backup restoration and AI-derived fields are blocking until individually verified or documented out of scope with evidence.
5. Shopify `customers/data_request` response must reach the authorized store owner through an authenticated, encrypted, short-lived channel with an audit receipt; never return PII via webhook response or logs.
6. Use idempotent request receipts and a per-subject suppression ledger to prevent imports, automations, retries, KB re-ingestion and backup restores from recreating erased data. Do not keep plaintext customer IDs in suppression logs.

## Codex acceptance contract

- Produce **machine-verifiable mapping** `(table/processor, field, purpose, provenance, tenant, exact subject key, export path, redact path, retention, test)` for every item above; unknown classification blocks release.
- Add synthetic fixtures for same customer across two stores, another organization, missing/changed Shopify IDs, order-only selectors, shared Customer global identity, Copilot/automation JSON, queued provider messages, object-store references, and reinstall after uninstall.
- The sandbox worker must demonstrate complete store-local export plus reviewable legal holds and cross-store isolation; no production worker until all class coverage and legal approval are explicit.
- Reviewer can navigate from a hashed request receipt to evidence **without** access to decrypted customer data; audit must not contain payload or secrets.
- Run full backend checks and negative auth/tenant tests. Publish evidence path and exact SHA in PR #149.

## Blockers / owners
- **Codex:** field-level mapping, export/delete functions, restoration and subprocessor adapters, regression tests.
- **ChatGPT:** architecture review, independent coverage audit and PR/CI evaluation.
- **Owner + qualified legal reviewer:** approve each retention exception, responsibility/processor arrangements and live-data authorization.
- **Operations:** verify true runtime vendor inventory, object storage, backups and observability in approved read-only checks (not checked here).

Official reference: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
