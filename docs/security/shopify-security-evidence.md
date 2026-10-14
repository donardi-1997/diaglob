# Shopify App Store data-protection evidence inventory

Status: **not attested**. The 16 completed Shopify Partners questionnaire answers are assertions, not automatic verification.

| Shopify declaration | Evidence to collect | Current assessment |
|---|---|---|
| Data minimization, purpose and merchant notices | Field-to-feature map, privacy policy versions, onboarding/consent capture | Needs operational review |
| Consent, opt-out and significant automated decisions | Data-flow map, user controls, test cases and applicability analysis | Needs validation; use "Not applicable" only where justified |
| Retention | Approved schedule, deletion job and reconciliation proof | Not verified; privacy execution incomplete |
| Encryption at rest / transit | TLS scan, RDS/storage/KMS settings, encryption key access policies | Not inspected in deployment |
| Encrypted backups | Actual backup configuration, encryption and restore drill | Not inspected |
| Production/test segregation | Environment inventory, separate credentials and data | Not inspected |
| DLP and least privilege | IAM roles, tenancy tests, access reviews and alerting | Not verified end to end |
| Team password requirements | Identity provider policies and MFA enforcement | Not inspected |
| Access logging | Evidence of data-access audit events and centralized retention | Needs proof |
| Incident response | Approved runbook, ownership, rehearsal and notification process | Draft plan only; Shopify answer should remain "No" until implemented |
| External audit/security certification | Third-party report, dates, auditor and authorized publication | Not located or independently verified |

## Evidence collection controls

Store references, sanitized screenshots, audit artifact SHA-256 and reviewer/date. **Do not** store actual Shopify tokens, secrets, raw protected customer data, backup contents, or privileged session credentials in this repository.

## Release checklist

- [ ] Incident plan approved with responsible parties, exercised and accessible.
- [ ] Retention schedule approved and effective erasure/export verified using synthetic cases.
- [ ] Encryption and backup claims verified against production configuration.
- [ ] Consent and automatic-decision answers matched to real features.
- [ ] Claimed September 2026 security reviews supported by signed findings/reports; otherwise remove the claim.
- [ ] Shopify Partners answers reconciled with evidence and requested protected fields.
- [ ] Separate reviewer signs off before protected-data access review submission.

This checklist does not change Shopify Partners settings or itself provide third-party certification.
