# Shopify privacy — automated marketing linkage in customer access reviews

**Status: preview only, not data export or GDPR fulfillment.**
Engineering checkpoint: 2026-10-15.

## Gap

The existing `POST /api/internal/shopify/privacy/cases/{request_id}/local-export/inspect`
returned counts for profiles, orders/items, conversations/messages and
conversational checkouts, but **did not show marketing automation records**.
A privacy case could therefore look empty or small despite having campaign,
provider delivery and flow execution records tied to the same Shopify buyer.

## Change

The existing authenticated endpoint now includes an `automation` object with
counts for:

- campaign audience membership;
- campaign recipient execution;
- provider delivery attempts;
- flow recipient execution;
- flow node execution.

Counts come exclusively from the existing
`inspect_shopify_automation_privacy_impact` SQL aggregate queries. They join
through the **original campaign/run or flow run** with the signed request's
organization and store, and match the precise external Shopify customer ID
to one store-local profile. No email/phone guesses. No direct query of
rendered messages, provider identifiers, automation templates, customer
addresses, unstructured payloads or access tokens.

If Shopify/tenant attribution cannot be verified, the inspection fails closed
with `AUTOMATION_PROVENANCE_UNVERIFIED` instead of returning partial coverage.

Example **synthetic, counts-only** response fragment:

```json
{
  "automation": {
    "audience_members": 1,
    "campaign_recipients": 1,
    "delivery_attempts": 1,
    "flow_recipients": 1,
    "flow_node_executions": 1,
    "attribution": "verified_external_customer_id",
    "export_included": false,
    "coverage": "linked_records_only"
  },
  "complete": false,
  "merchant_delivery_allowed": false
}
```

## Verification

```bash
cd backend
pytest -q tests/test_shopify_privacy_automation_provenance.py tests/test_shopify_privacy_local_processor.py tests/test_shopify_privacy_case_assessment.py
```

The regression test includes a customer shared across two stores and a
separate organization, each with distinct automation rows. The signed
request's inspection counts only the correct store (1 of 3), returns
no PII, does not construct export ciphertext and does not mutate data.
Missing customer identity and provenance errors remain fail-closed.

## Not yet covered

- Data **export/redaction** of the automation rows is *not* implemented.
  These are impact counts for operator triage, not records delivered to a buyer.
- Legacy automation payloads, Copilot/AI text, orphan executions, attachments,
  provider-controlled WhatsApp/email copies and backups remain outside this
  attribution audit.
- Legal retention policy, verified recipient, independently approved delivery,
  production redaction, provider verification and backup restore/replay safety
  remain blockers.
- No new migrations, routes, AWS resources or production flags are introduced.

Official reference: https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
