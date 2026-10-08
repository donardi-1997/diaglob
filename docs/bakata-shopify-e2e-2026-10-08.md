# Bakatá Shopify integration — verified findings, 2026-10-08

Related issue: #146. This is a partial implementation and validation record;
the production integration is **not complete**.

## Production evidence

- Created Bakatá through Diaglob's official Stores UI with
  `0djnem-9x.myshopify.com`, CO, COP, Spanish and America/Bogota.
- Started the official OAuth flow. Shopify says DIAGLOB is under review and
  disables installation. No access token or persistent connection was obtained.
- Read-only Shopify connector: 12 products, 8 active, 4 drafts, 16 variants,
  zero orders. This connector access does not prove Diaglob is connected.
- All eight active variants have stock 0, `availableForSale=true`, tracked
  inventory and `inventoryPolicy=CONTINUE`. This allows backorders, but is not
  evidence of supplier stock. The eight draft variants have zero price.
- Copilot read-only request scoped to Bakatá failed to connect to its AI model.
- Public E2E preflight: 8 PASS, zero FAIL; API health reports database connected.
- Personal AWS account confirms `diaglob-prod` running in us-east-2. The
  configured default Nova 2 Lite inference profile exists and is ACTIVE. This
  does not verify the backend's credentials or effective IAM permissions.
  No Diaglob CloudWatch log group or SSM managed instance was available.

## Corrections

- A configured Shopify domain alone no longer marks the integration connected.
- Sync requires explicit Shopify availability, active product and positive
  price. Missing availability/status no longer silently means sellable.
- AI product tools return a conservative purchase flag and reason. Stock 0
  is `stock_not_verified` when Shopify allows backorders, not positive supplier
  availability. The platform's original availability flag remains stored.
- Draft order, POC, COD and conversational checkout reject inactive products,
  zero price, unavailable variants and insufficient locally verified stock.
- Draft orders check organization ownership and aggregate repeated variant
  quantities before checking stock.
- Blank API version configuration falls back to 2026-07, matching the default.
- OAuth regression tests cover bad HMAC, expired state, wrong shop, encrypted
  token persistence and replay refusal. Provider calls are mocked.

## Automated validation

- Related backend suite: 198 PASS (Shopify, AI tools, integrations,
  conversational checkout, Flow Builder and templates).
- Frontend: 88 PASS, lint PASS, build PASS.
- Backend Ruff and `git diff --check`: PASS.
- Static independent review: no critical/important regression identified.
- Full backend suite and PR CI are tracked separately; do not infer full-suite
  success from the related suite above.

## Flow Builder limitations

Five scenarios were submitted to the existing simulation service in an isolated
local harness. Store lookup was mocked; no database recipients, workers or
provider clients were created and no messages were sent.

| Scenario | Result | Evidence |
| --- | --- | --- |
| New order → internal notification | FAIL | No internal_notification node |
| Updated order → state update | FAIL | No order_updated trigger |
| Unavailable product → alert | FAIL | No product_unavailable trigger or internal notification node |
| Delivered shipment → post-sale follow-up | BLOCKED | Graph validates; simulation does not execute nodes |
| Recurrent customer → retention | BLOCKED | Graph validates; simulation does not execute nodes |

The current simulate endpoint validates graph structure and counts node types;
it cannot certify execution. These capabilities still need implementation and
execution tests. They are engineering gaps, not external authorization steps.

## Remaining implementation/verification limits

- Catalogue stores active/inactive, not distinct draft/archived states, and
  imports only the first image and first 100 variants per product. Variant
  pagination, stale/deleted variant reconciliation and sync partial failure
  reporting remain gaps. Existing variant currency is not refreshed.
- Existing order webhook tests cover signed create/update/cancel, duplicate
  events and stale state. Real subscriptions and delivery for Bakatá remain
  unverified until installation; do not report them as registered.
- Local stock has no freshness guarantee or reservation. No positive Dropi
  availability was verified; Dropify installation alone is insufficient.
- Production secret presence/encryption configuration and effective model
  permission require backend access. Secret values must never be logged.
- This change must not be merged/deployed as a completed E2E integration while
  approval or critical Shopify/AI/automation blocks remain.

## External actions

1. Resolve DIAGLOB's Shopify review/distribution eligibility; then authorize
   installation using the official Diaglob Connect Shopify flow.
2. Provide an authenticated AWS console session to inspect backend logs and
   runtime configuration without revealing credentials in chat.
3. Confirm Dropi/Dropify's authoritative stock semantics/access with supplier
   support before allowing stock-zero items to be purchased.
4. Review the PR. Merge requires approval, green CI and no critical blockers.

References: [Shopify inventory policy](https://help.shopify.com/en/manual/products/inventory/getting-started-with-inventory/selling-when-out-of-stock),
[app distribution](https://shopify.dev/docs/apps/launch/distribution/select-distribution-method),
[ProductVariant 2026-07](https://shopify.dev/docs/api/admin-graphql/2026-07/objects/ProductVariant),
[Dropi integrations](https://dropi.co/integraciones).
