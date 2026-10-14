# DIAGLOB — Security incident response plan

Status: **draft for owner approval and tabletop exercise** (2026-10-14). Publishing this document is **not** proof that the incident-response program is operational.

## Scope and roles

Covers Diaglob APIs, Shopify integrations, customer/order records, automations, AI services, access tokens, backups, suppliers, and infrastructure. The accountable incident commander is the designated Diaglob operator; a backup and an on-call contact **must be assigned** outside this document before declaring operational readiness. Access to incident evidence must be restricted by need to know.

## Severity and triage

- **Critical**: confirmed widespread personal-data exposure, active unauthorized access to production secrets or destructive compromise.
- **High**: suspected customer-data leak, compromise of a privileged account, data-integrity violation, or sustained loss of security-critical services.
- **Medium**: limited exploitation attempt, isolated tenant issue, or vulnerability with credible impact.
- **Low**: blocked probe, minor vulnerability, or event with no established impact.

Treat ambiguous high-impact events as potentially high severity until evidence supports reclassification.

## Response workflow

1. **Detect and register**: capture UTC discovery time, reporter, affected systems, severity, shop/tenant identifiers (without raw PII), initial indicators, and an incident ID. Preserve relevant telemetry with controlled access.
2. **Contain**: revoke/rotate affected tokens, restrict ingress or permissions, quarantine compromised workers; avoid destructive evidence removal. Keep service continuity only when safe.
3. **Investigate**: establish earliest known compromise, affected stores, datasets, downstream processors and backups, root cause, and exposure timeline. Maintain evidence hashes and chain of custody.
4. **Eradicate and recover**: patch, rotate credentials, restore verified-clean infrastructure and data, validate webhooks and authorization boundaries, monitor for recurrence.
5. **Assess notifications**: legal/privacy owner determines obligations and applicable deadlines under relevant jurisdictions, Shopify terms, processor agreements, and merchant contracts. Record rationale and send notifications through approved channels; **do not assume a universal fixed deadline**.
6. **Close with evidence**: incident commander approves impact assessment and recovery; independent reviewer validates corrective actions and records a post-incident report. Never close an incident on log silence alone.

## Special handling

- Shopify signed privacy webhooks are data-subject workflows, not security incidents by default; failed requests or unintended disclosure can escalate to an incident.
- Secret material, access tokens, customer contact data and decrypted privacy exports **must not be copied into GitHub issues, CI logs or incident tickets**.
- Backups and external processors must be included in exposure and remediation scope.
- Preserve retention/legal holds and auditability during containment and deletion decisions.

## Evidence and readiness acceptance

Required before switching Shopify's 'incident response policy' answer to **Yes**: named accountable roles and reachable channel, versioned and approved plan, operator access to logs/runbooks, escalation drills, notification decision framework reviewed for applicable law, one tabletop exercise with follow-up actions, and evidence of closure for any critical gaps.

## Initial exercise scenario

Simulate a leaked Shopify token in a development log. Verify detection, scope determination, rotation, Shopify-store tenant isolation, downstream processor notification assessment, restoration, timestamps and exercise report. Use synthetic data and a non-production token only.
