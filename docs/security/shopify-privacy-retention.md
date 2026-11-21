# Shopify privacy requests: processing and retention gap register

Status: **review required**. No general retention period has been approved, and no customer-data erasure or delivery is certified by this document.

## Current code behavior

- `backend/app/api/shopify.py` authenticates webhook payloads by raw-body HMAC and forwards the three privacy topics to the durable intake.
- `shopify_compliance_webhooks.py` records encrypted minimal selectors, deduplicates receipts and prepares case work items.
- `shopify_privacy_processing.py` explicitly marks fulfillment incomplete and requires manual review.
- `shopify_privacy_local_processor.py` constructs an incomplete in-memory encrypted export or deletion manifest; it **does not** execute deletions or deliver a complete export.
- `shopify_privacy_controls.py` collects evidence hashes but does not declare legal approval, processor compliance, or completed redaction.

## External restore checkpoint prerequisite

Before enabling `SHOPIFY_PRIVACY_PROCESSING_ENABLED=true`, operators must
establish the signed suppression checkpoint outside the database **and** outside
the backup/restore boundary. Supply the independently authenticated
`SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC` and
`SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS` from that ledger. When live processing is
enabled and the checkpoint is absent, Shopify re-ingestion now fails closed,
even when the restored database has no tombstones. A checkpoint computed from
the restored database does **not** prove recovery safety.

Refresh the external checkpoint and deployment values as a controlled part of
each local redaction; validate the restored snapshot against the latest
independent checkpoint before restarting any ingestion or campaign worker.
This gate does not itself verify legal holds, offsite ledger durability,
third-party deletions, or complete Shopify privacy fulfillment.

## Data classes to inventory

| Area | Verification required |
|---|---|
| Customer identity and store profiles | Scoped lookup, cross-store isolation, anonymization targets |
| Orders and financial records | Legal/tax retention, redaction/minimization of contact fields |
| Conversations, AI prompts and messages | PII discovery, redaction and retained embeddings/KB context |
| Automation jobs and logs | Pending retries, event replay suppression, log retention |
| Suppliers, logistics and processors | Contractual deletion/access request propagation and confirmation |
| Database backups, objects and archives | Retention windows, purge feasibility, restore/reingestion safeguards |

## Completion criteria

1. Reconcile customer/shop IDs, verified merchant installation, requested order identifiers and store boundaries.
2. Confirm legal basis and retention exceptions per data class and country, with responsible reviewer.
3. Generate complete access bundle securely, authorize delivery to an authenticated requester and audit it.
4. Execute actual deletion/anonymization with transactionality, minimal retained tombstones and reingestion suppression.
5. Coordinate external processor actions, archive evidence, and handle backup expiration/restoration.
6. Independently validate no unintended cross-tenant deletion, produce case closure evidence, and reconcile outstanding webhook requests.

**Blocker:** the current code supports intake and planning but not the full verified execution workflow. Do not mark Shopify privacy cases or App Store data-protection compliance completed on the basis of this document.
