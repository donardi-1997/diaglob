# Shopify privacy — retention and secure delivery release criteria

Status: **NOT APPROVED / NOT IMPLEMENTED FOR LIVE DELIVERY**.

This document describes the gates for `customers/data_request`. It does not
establish legal retention periods, certify Shopify compliance, authorize
erasure, or activate a production data-delivery channel.

## Retention and legal-hold decisions

Before processing live customer information, legal/privacy and the data owner
must approve a category-by-category register with:

- Identified purposes and applicable lawful basis by jurisdiction;
- Minimum retention, maximum retention, start event, and exceptions;
- Which financial/order records are preserved with PII minimized;
- Which shipping, support, chat, AI, and marketing records can be exported;
- Whether a legal hold exists, owner, review date, and release mechanism;
- Specific disposal for short-lived exports and recovery from backup;
- Signed evidence stored outside the app; DIAGLOB stores only an opaque digest.

No retention period is inferred from a store's country, or from a webhook date.
Submitting a SHA-256 evidence reference is not legal approval.

## External processors and recovery

Inventory all configured processors (including email, WhatsApp, Meta, supplier
integrations, Bedrock, logs, object storage, execution queues and backups).
For each, record whether subject-linked data exists, export/deletion mechanism,
request identifier, outcome, retention exceptions, and anti-reimport behavior.
An empty or unavailable provider response is a review blocker, not success.

## Secure customer-access export delivery

A production design must implement and independently test **all** controls:

1. Authenticate the merchant recipient using an identity separate from an
   untrusted incoming webhook or caller-supplied email.
2. Bind authorized recipient, organization, shop, subject and opaque request.
3. Produce complete scoped, encrypted artifact without unrelated tenant data.
4. Store only ciphertext with restrictive authorization and encryption keys.
5. Deliver via a short-lived, single-use, revocable authenticated mechanism,
   without embedding PII or raw tokens in logs/URLs.
6. Audit access, recipient, revocation and delivery without recording PII.
7. Enforce expiry, delete the artifact and validate backup/reingestion behavior.
8. Record delivery confirmation separately from file creation and Shopify ACK.

The current internal API returns **status and blockers only**; it never returns
ciphertext or links. It must stay that way until a separately reviewed delivery
implementation passes staging E2E tests. `fulfillment_complete` remains false.

## Production go/no-go

Live delivery or case completion must remain disabled unless all fields and
child associations are covered, the signed scope and Shopify order selectors
are resolved, legal retention and processor evidence are independently
approved, the recipient is verified, access is expiring and revocable, and a
staging test proves isolation, expiration, deletion and audit behavior.

Implementation approval is **not** granted by this checklist or by an artifact
whose status is manually changed to `verified`.
