# Shopify privacy — sealed automation data extraction fixture (2026-10-15)

**Engineering-only prototype. This is NOT live customer-data export, legal authorization or Shopify privacy fulfillment.**

## Previously closed

PR #258 added PII-free counts for five marketing-automation surfaces to the
existing authenticated operator inspection: audience memberships, campaign
recipient executions, delivery attempts, flow recipient executions and node
executions. These counts do not include an exportable data snapshot.

## What this change adds

`build_encrypted_shopify_automation_fixture(...)` demonstrates the next
piece of the pipeline **only for an in-memory SQLite test database**:

1. An explicit `fixture_authorized=True` flag and `sqlite:///:memory:`
   database are required *before* any case or buyer records can be loaded.
2. Require an exact 64-character signed receipt identifier, HMAC-verified
   intake audit, unchanged shop/store mapping and one unambiguous local
   `external_customer_id` to one global Diaglob `customer_id`.
3. Require a `customers/data_request` case not marked completed. Missing
   subject identifiers cannot be guessed from email/phone, and historical
   completed status is not treated as actual fulfillment.
4. Select buyer-linked rows using explicit organization/shop joins through
   campaign → run → recipient and flow run → recipient → node. Do not project
   merchant-wide campaign message templates or flow trigger contexts.
5. Compare the number of source records against the existing PII-free
   `inspect_shopify_automation_privacy_impact` SQL aggregate; discrepancies
   block export.
6. Serialize only a bounded (max 250 rows per source / 1 MB of JSON) payload;
   encrypt the exact request-bound envelope with Fernet in memory. Nothing
   is stored or delivered by this service and no HTTP route is exposed.

The encrypted fixture may include fabricated recipient messages, JSON
`template_data`, provider reference IDs and node `extra_data` from the
isolated test DB. Plaintext must **never** be sent to merchant endpoints, logs,
third-party processors or production artifact tables.

Tests with two stores sharing one Diaglob customer and a third store in a
separate organization check exact tenant/store isolation and absence of
unrelated campaign/flow data. Tests also cover missing signed intake,
email-only selector, duplicate external subject, unsafe SQLite URL, unapproved
fixture flag and count drift.

```bash
cd backend
pytest -q tests/test_shopify_privacy_automation_provenance.py tests/test_shopify_privacy_local_processor.py tests/test_shopify_privacy_secure_delivery.py
```

## Next release blockers

- Production-grade verified subject-to-record coverage, including orphan
  automation executions, organization-wide datasets and external message
  provider copies;
- Legal retention, approved erasure/exception policy, independent delivery
  approval and a fully authenticated recipient;
- Actual production encryption-key management, immutable audits, time-limited
  merchant delivery, backup restore/reimport tests and external processors;
- Real Shopify GDPR webhook subscription/processing and end-to-end review.

`fixture_only=True`, `delivery_authorized=False` and
`fulfillment_complete=False` are intentional invariants. No database
migrations, AWS infrastructure, live export APIs, jobs or mutations are added.
