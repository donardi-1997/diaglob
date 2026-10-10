# Shopify privacy operational triage (development only)

This pure classification helper is **not** a customer data export, deletion service, scheduler, legal deadline calculator, or compliance completion mechanism.

`backend/app/services/shopify_privacy_triage.py` accepts trusted receipt metadata (opaque hashed request ID, topic, tenant/store IDs, timezone-aware intake and observation instants) and emits only operational priority, fixed reason codes, and unconditional `requires_manual_review=True` / `fulfillment_authorized=False`.

- All missing/unrecognized topics and tenant mappings receive high priority for investigation.
- Warning at 23 days and critical escalation at 30 days are **configurable operational thresholds**, not a promise of Shopify or statutory deadlines. Actual deadlines depend on the request and jurisdiction.
- Future-dated receipts and invalid input types are rejected/escalated to prevent invisible backlog.
- This helper is intentionally **not wired into an API endpoint or production worker**, because identity authorization, processor coverage and fulfillment controls are still pending.
- Regression tests cover threshold boundaries, UTC normalization, missing tenants, unknown topics, malformed request IDs, non-boolean evidence and rejection of naive timestamps.
- Running a classifier does not fulfill a request or authorize releasing or erasing customer data.

Before production use: define a verified intake timestamp policy (current persistence uses naive UTC in portions of the application), role-based access, validated data retention and legal exceptions, retries/alerting, complete subject provenance, and auditability. Never infer that receipt acknowledgement or a successful CI run constitutes Shopify GDPR compliance.

Related: PR #149 and issue #148.
