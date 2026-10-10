# DIAGLOB — Shopify security, permission scopes, OAuth and checkout audit
Audit: 2026-10-10 · PR #149 · **Code-based risk assessment, not an E2E or penetration test**

## Reviewed evidence
`backend/app/shopify_oauth.py` defines eight static scopes:
`read_products`, `read_inventory`, `read_customers`, `read_orders`, `write_orders`, `write_draft_orders`, `read_merchant_managed_fulfillment_orders`, `write_merchant_managed_fulfillment_orders`.

`backend/app/services/shopify_app_pricing.py` resolves the trusted Shop GID with a connected Shopify token before querying Partner API; `shopify_app_pricing_reconciliation.py` performs read-only plan reconciliation, fail-closed on inactive Shopify connection, ambiguous plan/catalog and Paddle-associated records. Production subscription activation is NOT implemented. Historical listing readme states embedded App Bridge/token semantics and live installation E2E remain unverified.

## Findings (priority and action)

| Priority | Finding | Decision / assigned implementation |
|---|---|---|
| P0 | **No verified 30-day privacy fulfillment across all personal-data processors**, only receipt/audit/partial synthetic preview | Codex must implement complete verified export/redaction + legal hold logic after owner/legal approval; no App Store submission |
| P0 | `write_orders`, `write_draft_orders` and fulfillment writes may enable order mutation incompatible with merchant checkout expectations | Inventory each real mutation endpoint; prove buyer payment/checkout stays within Shopify; disable unsupported/COD shortcuts, escalate exceptions for policy review |
| P0 | Standalone DIAGLOB OAuth entrypoints and app install/reinstall experience not confirmed to comply with Shopify-owned installation + immediate OAuth | Codex must map app architecture and actual Partner Dashboard setting; test first install/uninstall/reinstall, auth immediately and redirect to usable UI |
| P1 | Protected customer data (read_orders, read_customers and name/address/phone/email) requires field-level purpose and Shopify approval | Request only indispensable fields and scopes; submit level 1/2 review as applicable; fail safely when fields redacted |
| P1 | Embedded-vs-standalone auth selection unknown; embedded cannot rely on third-party cookies/localStorage alone | If embedded, use App Bridge ID tokens and server validation / token exchange; if standalone, verify authorization code state/HMAC and Shopify-owned install entrypoint |
| P1 | Current scope constant always requests all eight permissions | Map permission to merchant-visible capability; remove default permissions not required for MVP, or use optional-grant strategy when supported; re-auth on scope changes |
| P1 | Shopify Billing read-only partner verifier is not a paid entitlement lifecycle | Codex: implement server-authoritative shop→org binding, Partner confirmation, lifecycle, periodic refresh, event handling and fail closed; preserve independent Paddle contracts |
| P1 | Readable PIIs in order notes, AI/copilot message bodies, automation JSON and provider errors | Define structured provenance/field-level minimization, redacted logs, access controls, and processor erasure |
| P2 | Production URLs, TLS, webhook deployment and app-level webhook subscriptions not verified from running environment | Validate read-only configuration, TLS and event registration before submission; do not assert live compliance from code |
| P2 | Shopify CLI self-review, real reviewer flow and listing demo not validated | Add to pre-submission evidence with final HEAD SHA and dated artifact links |

## Scope justification / decision matrix

| Shopify scope | Merchant-visible purpose under consideration | Default release recommendation |
|---|---|---|
| `read_products` | sync catalog and product availability | KEEP, subject to tested feature |
| `read_inventory` | read warehouse inventory, not supplier stock guarantee | KEEP only if inventory sync needs scope; verify API permissions |
| `read_customers` | customer association/order service context | CONDITIONAL — protected data review; try to avoid direct customer read if order-scoped IDs suffice |
| `read_orders` | order status, reporting and customer support | CONDITIONAL — protected order data review and 60-day/extended-order permissions if required |
| `write_orders` | direct order mutation | BLOCK until exact permitted use-case and checkout policy proof |
| `write_draft_orders` | draft order creation | BLOCK for public release until documented merchant-authorized flow plus compliant checkout evidence |
| `read_merchant_managed_fulfillment_orders` | fulfillment status/context | CONDITIONAL — show concrete feature and Shopify test |
| `write_merchant_managed_fulfillment_orders` | fulfillment mutation | BLOCK until explicit merchant-facing functionality, RBAC and policy sign-off |

Keep/remove decisions are recommendations, not actual scope changes. Scope removal can break legacy workflows; Codex must audit code usage and add tests before changing configurations. Product intent is to work for ecommerce merchants, not to bypass Shopify Checkout.

## Test contract for Codex

1. Build a routes→GraphQL mutations→scope matrix; include `shopify_cod_orders.py`, `shopify_orders.py`, `shopify_poc.py`, `shopify_sync.py`, agent tool executor, and conversational checkout.
2. Verify OAuth HMAC/state replays, one-time state consumption, shop-domain canonicalization, open redirects, uninstall/token revocation, reinstall reauth, cross-tenant connection reassociation and Shopify-owned install initiation.
3. Embedded app? Prove verified App Bridge ID tokens/no third-party cookie dependence in incognito. Standalone app? Prove documented authorization-code redirect and UI after OAuth.
4. Verify every backend order mutation and agent tool requires explicit merchant/role authorization, controlled idempotency and correct source of stock (supplier zero ≠ verified availability).
5. Prove protected-customer-data behavior when fields are redacted/unapproved; never assume a 200 GraphQL HTTP response means requested protected fields were delivered.
6. Confirm Shopify App Pricing checkout uses Shopify-hosted plan selection; only grant after authenticated Partner API confirmation and authorized organization billing channel.
7. Test internal-secret access for privacy endpoints, HMAC wrong/missing HMAC responses (401), request digest replay, sensitive logs and hardened async callback retry.

## Official references
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
- https://shopify.dev/docs/apps/launch/protected-customer-data
- https://shopify.dev/docs/apps/build/authentication-authorization
- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing

## Release verdict
**BLOCK** Shopify public submission / live personal-data fulfillment / automatic paid plan grants until P0 findings have test evidence and required owner/Shopify approvals. Existing passing CI verifies tested code, not live app configuration or legality.
