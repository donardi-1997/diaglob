# Shopify privacy backlog operational monitor

**Status: development-only, read-only observability. NOT proof of legal
compliance, request fulfillment, or readiness for Shopify App Store review.**

The intake path stores authenticated Shopify compliance requests with encrypted
subject selectors. This module aggregates unresolved request ages and the number
of events whose original shop/organization cannot currently be resolved.

### Authenticated internal endpoint

`GET /api/internal/shopify/privacy/backlog`, requiring the existing
`X-Internal-Secret` internal backend secret. Rejects absent/incorrect secret
with HTTP 401 **before** any database query. Do not expose the secret in UI,
public docs, logs, GitHub, URLs, or browser code.

Returns only aggregated counts per Shopify topic:
- Total outstanding requests.
- Requests older than the **nominal 30-day** Shopify deadline.
- Requests within the seven-day warning window.
- Requests whose tenant/store mapping was unavailable at intake.
- Unexpected topic receipts requiring manual data-integrity review.
- Age (days) of the oldest unresolved request.

No customer names, domains, emails, Shopify shop IDs, receipt identifiers,
encrypted selectors or database rows are returned. SQL `COUNT/SUM/MIN` are
used; the endpoint does not decrypt fields, fetch customer profiles,
perform exports, approve retention exceptions, remove records or update
request statuses.

Until an authenticated, audited real fulfillment workflow exists, **every**
receipt remains outstanding, even if a database status field is set to
"completed", "exported" or "redacted". Unknown topics are included in totals
and counted separately, without exposing the topic value. Pending policy
review, manual review and legal holds always remain outstanding. A legal
retention exemption must be assessed and documented separately. The 30-day timer is only a
**monitoring threshold** from receipt time. Real legal deadlines and owner
responsibilities require independent approval.

Shopify reference:
https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance

### Future operational steps (blocked)

- Set up authorized internal monitoring and alerts for overdue requests.
- Classify legal holds and jurisdiction-specific retention evidence.
- Implement authenticated export delivery, full data-source coverage, real
  tenant-safe redaction, backup/processor handling, anti-reingestion and
  auditable completion before enabling live processing.
- Verify production deployment and three app-level compliance subscriptions
  against the existing Shopify app; never create a replacement app.

This change uses no migration, sends no notifications, and changes no
billing or Shopify installation configuration. Associated issue: #148.
