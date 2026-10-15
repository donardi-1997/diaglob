# Shopify privacy escalation queue — engineering checkpoint (2026-10-15)

**Status:** read-only operational improvement. GDPR fulfillment is **NOT** completed, export and live redaction are not enabled, and this change is not proof of Shopify App Store approval.

## Problem

The existing privacy backlog summarizes cases and the generic case list is oldest-first. Operators need a dedicated high-priority view that cannot hide a case nearing Shopify's 30-day processing target behind a page of normal requests.

## Implemented

- `GET /api/internal/shopify/privacy/escalations?limit=20&offset=0` authenticates via the existing `X-Internal-Secret` **before querying**. This is an internal control, not a merchant or public API; do not put the secret in browsers or logs.
- A DB-side filter finds cases received **23 or more days** ago, unknown topics, missing/invalid tenant-store bindings, future timestamps and missing timestamps.
- Overdue cases (30+ days) and missing timestamps rank **critical** before high-priority cases; within a group they are oldest first. The filter and ordering run **before pagination**.
- Only safe metadata leaves the service: opaque request hash, recognized topic, age, priority, reason codes and an exact UTC monitoring target timestamp. No selectors, domain, shop/customer IDs, contact details, or raw payload are returned.
- Cases with a manually entered `completed` status are **still outstanding**; no executable GDPR fulfillment pathway exists yet. Neither the endpoint nor the service calls a processor, sends notifications, changes data or approves deletion.
- `read_only=true`, `fulfillment_authorized=false` and `fulfillment_complete=false` remain explicit.

## Validation

Run:
```bash
cd backend
pytest -q tests/test_shopify_privacy_escalations.py tests/test_shopify_privacy_case_queue.py tests/test_shopify_privacy_triage.py tests/test_route_contract.py
```

Cases cover: priority before paging, exact 23/30-day boundaries, malformed/unknown topic, future timestamp, unresolved tenant, status spoofing, invalid pagination, authorization before DB access and absence of PII.

## Operational handoff

- Use `/api/internal/shopify/privacy/backlog` for totals and `/api/internal/shopify/privacy/escalations` for cases needing immediate manual investigation.
- Ensure an operator periodically checks and acts on critical cases; there is **no scheduled notifier** in this change.
- Shopify requires an actual response to an authenticated privacy request within 30 days unless retention is legally required. An HTTP 200 to the webhook is only intake acknowledgement.
- Remaining engineering/legal release gates: complete customer export, independent merchant authorization and secure delivery; redaction policy and field-level ownership; provider/S3/AI/queue coverage; production suppression and off-site restore drills; authentic Shopify delivery E2E.

Official reference: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
