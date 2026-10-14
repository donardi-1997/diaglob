# Shopify protected customer data: verification matrix (2026-10-14)

## Source-of-truth findings (main at audit start)

- OAuth requested scopes in `backend/app/shopify_oauth.py`: `read_products`, `read_inventory`, `read_customers`, `read_orders`, `write_orders`, `write_draft_orders`, `read_merchant_managed_fulfillment_orders`, `write_merchant_managed_fulfillment_orders`.
- A single privacy receiver already exists at `POST /api/webhooks/shopify/compliance` in `backend/app/api/shopify.py`. Do not add competing handlers.
- Raw-body Shopify HMAC-SHA256 verification uses `verify_shopify_webhook_hmac`. Invalid signatures return 401. The receiver enforces a 256-KiB request limit.
- `backend/app/services/shopify_compliance_webhooks.py` handles all three mandatory topics: `customers/data_request`, `customers/redact`, `shop/redact`. It records encrypted selectors and prepares durable work items; duplicate receipts are checked.
- **Not yet certified:** fulfilling Shopify data-access requests, verified deletion across structured records, AI content, external processors, backups, and final legal retention checks. The current processing module explicitly reports `fulfillment_complete: false`.

## Configuration validation before Shopify submission

1. In Shopify Partners, compare the installed app ID, active API URLs, redirect URL, and configured webhook subscriptions with the active production deployment. Do not infer configuration from the example in the CLI documentation.
2. Verify subscriptions for all three topics point to `https://api.diaglob.tech/api/webhooks/shopify/compliance`. Confirm production deploy and TLS routing; a Python route alone does not register Shopify subscriptions.
3. Compare actual installed token grants with the source OAuth scopes, paying particular attention to `read_customers` and `read_orders`. Reauthorization might be required after changing grants. Never print actual tokens or app secrets.
4. In Partners, declare **Gestión de la tienda** and **Funcionalidad de la app** only for operations using identifiable customer/order data. Add **Atención al cliente** only when connected Conversations/AI Agents query Shopify buyer data. Do not declare marketing, profiling or analytics without evidence of use.
5. Request protected **name, email, phone, address** fields individually only if the production code consumes each one for order handling, fulfillment or support. Avoid blanket approval requests.
6. Run `python scripts/audit_shopify_privacy_configuration.py` and repository tests. This is **source-only** inspection, not a live Shopify webhook delivery test.
7. Exercise synthetic HMAC-invalid and properly signed test deliveries against a staging installation and confirm 401 for invalid signatures, durable receipt + deduplication for valid deliveries, no PII in logs, and retriable non-2XX when persistence fails.
8. Verify a complete subject-access, customer-redaction and shop-redaction case with store-scoped evidence, lawful retention exceptions, processor coordination and controlled closure. Do **not** mark privacy fulfillment complete just because requests were acknowledged.

## Release gate

The submission remains **blocked** until actual subscription registration, granted scopes, deployment parity and end-to-end privacy fulfillment are evidenced. Do not expose internal privacy control endpoints or any secret in this evidence.
