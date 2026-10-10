# Shopify privacy — Copilot merchant-data impact and external processors

**Status: read-only store-scoped metadata inventory for internal engineering review.
This is not Shopify customer attribution, personal-data disclosure, deletion or
App Store compliance. It adds no HTTP endpoint, worker, migration or provider call.**

## Copilot / buyer identity distinction

A DIAGLOB `AgentChatSession` belongs to a **merchant user** and a selected
store. Its `AgentChatMessage.text/content`, `AgentChatToolCall.arguments/result`,
`AgentActionApproval.arguments`, session `context/pending_capacity` and tool
errors can contain **copied personal data of many buyers**; none of these
objects has a trustworthy foreign key to a Shopify data-subject customer.

`inspect_shopify_copilot_privacy_impact(db, receipt)` first checks the
received Shopify request's original store/domain/tenant identity. Then SQL
COUNT queries compute the number of sessions, messages, tool calls and action
approvals associated with that **store**. No message bodies, user names,
phone numbers, e-mails, tool payloads, tokens or receipt IDs are returned.

For `customers/data_request` and `customers/redact`, these numbers are
**store-wide possible review material**, NOT a count of records for the
customer who requested their data. An unknown Shopify customer ID yields the
same store-wide inventory; this is deliberate and cannot justify any export,
redaction or marking a request fulfilled. For `shop/redact`, counts indicate
candidate merchant/store-owned records needing legal retention and lifecycle
review, not permission to destroy them. Records in another store (including
another store in the same organization) are excluded.

No automatic matching against e-mail, phone, names, order numbers, chat
strings or JSON is allowed. Before real Shopify customer disclosure or
redaction, capture verified per-record provenance **at ingestion**, design
customer/merchant separation and document legal retention, backup copies
and provider disposal. Existing session permissions must not be bypassed.

## External processor review (all blocked)

| Data surface | Current code/evidence location | Missing customer data-handling requirement |
|---|---|---|
| AWS Bedrock / AI prompts and responses | `backend/app/services/bedrock_agent_chat.py` | Verify prompt logging/storage and per-subject provenance, provider retention and deletion |
| AWS knowledge/files/object storage | `backend/app/model_domains/knowledge.py` | Object/prefix inventory, subject lineage, KB re-ingestion, backup restoration |
| WhatsApp, Instagram and outbound messaging | `backend/app/model_domains/messaging.py`, `backend/app/integrations/instagram/client.py` | Provider IDs, lawful deletion/export capabilities, queued messages, retries |
| Supplier/drop-shipping integrations | `backend/app/integrations/dropi/provider.py`, `backend/app/integrations/cj/client.py` | Determine if buyer/shipping data is transmitted, provider retention and subprocessor deletion |
| Shopify/Nuvemshop and customer order sync | `backend/app/shopify_sync.py`, `backend/app/integrations/nuvemshop/client.py` | Per-shop origin, source-of-truth, deduplication, deletion tombstones |
| Analytics/ads and data exports | `backend/app/integrations/meta_ads/client.py` | Consent, event identifiers, retention/export and processor handling |
| App logs, metrics, archives and backups | Deployment/operational configuration review needed | Data minimization, erase-on-restore, tombstones, audit-only receipts |

The above are **review categories, not verified declarations of live data
transmission or processor guarantees**. No processor has been marked complete.
Do not claim Shopify privacy readiness until evidence of live coverage,
retention law review, subject-authenticated fulfillment and external processor
handling is accepted.

Related: #148 and draft PR #149.
