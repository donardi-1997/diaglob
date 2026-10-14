# Diaglob — signed GDPR webhook E2E and OAuth scope parity, 2026-10-14

## Evidence from the live app version

The owner supplied a screenshot of the **active** Shopify Dev Dashboard version `diaglob-3` of existing app `416524435457`:

- Version: `diaglob-3` (active)
- `application_url = https://api.diaglob.tech`, `embedded = true`
- OAuth redirect: `https://api.diaglob.tech/api/shopify/callback`
- Webhook API: `2026-07`
- `customers/data_request`, `customers/redact`, `shop/redact` each point to `https://api.diaglob.tech/api/webhooks/shopify/compliance`.

**App-level subscription configuration is evidenced by the screenshot.** A successful delivery of a legitimate Shopify-signed event is NOT established by a screenshot or by HTTP 401 for a forged event.

The screenshot also shows these **active-version declared** Shopify scopes:

`read_customers,read_inventory,read_orders,read_products,write_orders,write_products`

The backend `app/shopify_oauth.py::SHOPIFY_SCOPES` instead declares:

`read_products,read_inventory,read_customers,read_orders,write_orders,write_draft_orders,read_merchant_managed_fulfillment_orders,write_merchant_managed_fulfillment_orders`

| Drift relative to active version | Scope | Impact |
| --- | --- | --- |
| Backend requests, active version does not declare | `write_draft_orders` | Draft-order creation may fail for an installed grant lacking this permission |
| Backend requests, active version does not declare | `read_merchant_managed_fulfillment_orders` | Fulfillment-order lookup is gated |
| Backend requests, active version does not declare | `write_merchant_managed_fulfillment_orders` | Shipment tracking → Shopify fulfillment creation is gated |
| Active version declares, backend OAuth does not request | `write_products` | Extra scope requiring confirmation of its customer-visible purpose and actual use |

**Do not** change the active app's scopes blindly: a change may require reauthorization and protected-data approval. Compare the *actual grant* held for each connected shop to both source and Dev Dashboard version before any new app deployment. In code, `shopify_fulfillment.py::missing_fulfillment_scopes` explicitly rejects missing merchant-managed fulfillment permissions. The current Shopify connector connected in this ChatGPT chat belongs to **Bakatá**, not `diaglob-poc.myshopify.com`, so it is not a valid source for Diaglob app grants.

## Signed HTTP round trip — isolated only

Test: `backend/tests/test_shopify_compliance_webhooks.py::TestShopifyComplianceWebhooks::test_complete_synthetic_signed_three_topic_delivery_and_idempotent_retries`.

Uses an in-memory SQLite test database, test-only HMAC secret and encryption key, Shopify-shaped payloads and FastAPI TestClient. Each topic receives a **valid synthetic HMAC**, is delivered twice with identical Shopify webhook ID, and then once with a forged HMAC.

Expected evidence for each topic:
- first POST: HTTP 200 `recorded`
- replay POST: HTTP 200 `duplicate`, stable `request_id`
- forged signature POST: HTTP 401
- exactly 1 encrypted privacy receipt, 1 `received` audit, 1 `processing_prepared` audit and **10 blocked/review-only tasks**
- no PII in HTTP receipt, encrypted store, or aggregate audit
- no data fulfillment and no production suppression activation.

For three events combined: **3 receipts, 30 work items, 6 audit events, 0 active suppressions**. Executing CI provides evidence that the implementation works in the synthetic environment, not that Shopify sent a live GDPR event.

## The external delivery test still required

There is **no isolated public staging webhook endpoint proven available**. Never send fake, validly signed Shopify privacy events to the production URI; doing so would pollute the privacy inbox and falsely imply real obligations.

To test Shopify transport with sample payloads, configure a **staging** HTTPS receiver and temporary isolated staging DB, then run Shopify CLI from the existing linked app project (logged in to the correct Diaglob developer account):

```sh
shopify app webhook trigger \
  --api-version=2026-07 \
  --address=https://STAGING_HOST/api/webhooks/shopify/compliance \
  --topic=customers/data_request

shopify app webhook trigger \
  --api-version=2026-07 \
  --address=https://STAGING_HOST/api/webhooks/shopify/compliance \
  --topic=customers/redact

shopify app webhook trigger \
  --api-version=2026-07 \
  --address=https://STAGING_HOST/api/webhooks/shopify/compliance \
  --topic=shop/redact
```

The CLI tool sends fixed sample payloads, does not retry failed events, and explicitly **cannot validate configured subscriptions**. The screenshot already addresses the active-version configuration. After real sample deliveries to staging, verify HMAC success, single receipt + ten tasks, and duplicate IDs on controlled retries. A true production operational check must use authentic Shopify-origin events and check `ShopifyPrivacyRequest` metadata and the audit safely; Shopify App Store compliance also requires legally approved fulfillment of legitimate access/redaction requests.

Docs: https://shopify.dev/docs/api/shopify-cli/app/app-webhook-trigger and https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
