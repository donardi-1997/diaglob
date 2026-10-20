# DIAGLOB — Shopify App Store pre-submission assessment (2026-10-20)

> **Decision: NO-GO for App Store submission.** This is an evidence-based review of GitHub `main` at `fc8baf1a402fbc2aa6d50b331e168c30a820fce7`, **not** a run of the official Shopify AI Toolkit, a Partner Dashboard verification, or a live merchant E2E test.
>
> No Shopify Partner settings, API permissions, merchant data, production infrastructure, billing plans or deployment were changed by this assessment.

## Scope and evidence

- Repository: https://github.com/donardi-1997/diaglob ; inspected branch: `main`.
- Shopify app configuration: [shopify.app.toml](../shopify.app.toml); eight source OAuth scopes: [shopify_oauth.py](../backend/app/shopify_oauth.py).
- The source-only preflight and tests exist: [shopify_review_source_preflight.py](../backend/tools/shopify_review_source_preflight.py), [test_shopify_review_source_preflight.py](../backend/tests/test_shopify_review_source_preflight.py). **They were inspected, not executed in this review session**.
- GitHub Actions for this SHA reported **Validate=success** and **Deploy DIAGLOB Production=success** in https://github.com/donardi-1997/diaglob/actions/runs/38920020011. Periodic billing recheck also reported success; those are not merchant billing E2E proofs.
- Operator screenshot dated 2026-10-20 shows **8/9 preliminary Shopify submission checks completed**, with AI self-review unchecked. This does **not** establish that the separate Partner listing, protected customer data and production E2E criteria were fulfilled.
- Several historical docs reflect earlier states: `docs/shopify-app-store-readiness.md` (2026-10-09/10), `docs/shopify-review-source-preflight-2026-10-14.md`, `docs/shopify-managed-install-readiness-2026-10-15.md` and `docs/shopify-app-store-12-issue-field-pack-2026-10-11.md`. Their old NO-GO notes should not be treated as independent evidence that today's Partner Dashboard still has the same listing gaps.

## Findings and dispositions

| ID | Requirement / check | Assessment on inspected code | Required closure evidence |
| --- | --- | --- | --- |
| R01 | Correct Shopify source configuration | **SOURCE-PASS (not live PASS)**. Tracked TOML declares embedded App Home, client ID, eight scopes, API version `2026-07` and the three mandatory privacy topics. Backend `SHOPIFY_SCOPES` matches the declared set. | Run source preflight/tests at release SHA; compare with the *active* app version, scopes and subscribed topics in authenticated Shopify CLI/Partner. |
| R02 | Modern Admin API | **SOURCE-PARTIAL**. Central `ShopifyGraphQLClient` posts to `/admin/api/2026-07/graphql.json`. This does not prove an exhaustive scan of all Shopify integrations, including extension code. | Run the official Shopify review/security check and inspect all Admin API callsites for deprecated REST requests. |
| R03 | Embedded App Bridge / session | **SOURCE-PASS, LIVE-UNVERIFIED**. `backend/app/api/shopify_embedded.py` loads Shopify App Bridge, retrieves ID tokens, and verifies authorization before rendering protected store data. | Browser E2E in Shopify Admin, including fresh install, mobile/iframe, incognito, expired token, invalid membership, uninstall and reinstall. |
| R04 | Seamless first-time Shopify merchant onboarding | **REVIEW-RISK**. The current embedded App Home directs a first-time merchant through a **10-minute code and separate DIAGLOB account/tab** before reaching the connected tenant. Verify this workflow meets Shopify's seamless install / embedded-UX requirements. | Test true first-time user without a prior DIAGLOB account and with reviewer credentials; simplify onboarding if necessary. |
| R05 | Protected customer data (PCD) request accuracy | **HIGH-PRIORITY RECONCILIATION**. The 2026-10-20 Shopify screenshot marks “No necesita acceso a datos de clientes protegidos”, whereas requested scopes include `read_customers`, `read_orders`, `write_orders`, draft orders and fulfillment. `shopify_cod_orders.py` manipulates phone, email and shipping address fields; these require determining the actual Shopify PCD levels/field approvals. The mismatch is a review risk, **not proof of Shopify's current grant status**. | Inventory actual customer/order fields read, written and stored; minimize scope/fields; if used, complete Partner PCD access request for Level 1 and, as needed, Level 2 name/address/email/phone fields. Reconfirm visible Partner declaration. |
| R06 | Mandatory privacy webhook intake | **SOURCE-PASS, LIVE-UNVERIFIED**. TOML lists `customers/data_request`, `customers/redact`, `shop/redact`; code implements signed receipt / durable queues. | Confirm deployed subscriptions and signed deliveries, 401 on invalid HMAC, retries and deduplication in an authorized test environment. |
| R07 | Actual privacy-request fulfillment / deletion | **CONFIRMED CODE GAP / P0**. `backend/app/services/shopify_privacy_processing.py` returns `fulfillment_authorized: False`, `fulfillment_complete: False`, `requires_manual_review: True`. Its documentation explicitly disclaims real production exports, erasure and recipient delivery, and other code limits some operations to synthetic SQLite fixtures. | Implement, review and test effective merchant delivery / deletion, subject identity, legal retention, processors, backups and reingestion safeguards, with verified workflow evidence. Do not mark compliance fulfilled merely on HTTP 2xx webhook receipt. |
| R08 | Shopify billing separate from Paddle | **SOURCE-PASS, LIVE-UNVERIFIED**. `shopify_hosted_plan_selection.py` validates Shopify-owned merchant/org and builds a Shopify-hosted plan link; `shopify_app_pricing.py` verifies Partner subscription data. Shopify organizations must not be charged through Paddle. | Confirm actual Shopify plans/handles, 3-day trial, price/interval in Partner and end-to-end selection, rejection, retry, upgrade, downgrade, cancellation and reinstall; verify no off-platform checkout is shown. |
| R09 | Scopes and write operations | **REVIEW-REQUIRED**. Tracked scopes include `write_orders`, `write_draft_orders`, and fulfillment write access. Source features use draft-order and fulfillment APIs, but each requested scope must be essential for the public listing's actual features. | Document exact feature/GraphQL operations for each scope; consider optional scopes for features not needed by all merchants. |
| R10 | App listing and reviewer access | **LIVE-UNVERIFIED**. The previous 12-item listing pack predates the current screenshot; this session cannot see Partner listing fields or credentials. | Confirm final category, localized text, authentic screenshots, support inbox, privacy/terms URLs, functional reviewer test account, English/English-subtitled screencast, and step-by-step testing instructions. |
| R11 | Verified shipping/checkout policy | **REVIEW-REQUIRED**. Source supports orders, COD/draft orders and fulfillment; Shopify prohibits bypassing the Shopify Checkout for a Shopify merchant. | Demonstrate supported flows with synthetic transactions only and document how DIAGLOB avoids off-platform checkout/payment processing for Shopify orders. |
| R12 | Build/CI evidence | **EXTERNAL-CI PASS ONLY** at the assessed SHA. GitHub Actions validate and production deploy checks succeeded. | Run official toolkit and record complete CI/test artifacts on the final release SHA, followed by production-equivalent E2E. |

## Priority order to reach review readiness

1. **P0 – Privacy fulfillment:** close R07 with lawful, scoped real export/redaction and documented retention/vendor/backup handling. Ensure signed intake does not masquerade as substantive completion.
2. **P0 – Protected customer data declaration:** reconcile the screenshot with actual `read_customers`, order/draft/fulfillment access and personal fields, as in R05. Obtain appropriate Partner approvals or reduce data usage/scopes where feasible.
3. **P0 – Fresh Shopify install and embedded UX:** demonstrate the first-time merchant/reviewer journey (R03/R04), including an accountless new merchant, expired/reused code, authorized store binding, merchant staff isolation, uninstall/reinstall.
4. **P0 – App Pricing E2E:** on authorized Shopify development shop, validate hosted plans, real Partner subscription, 3-day trial, accept/decline/retry, upgrades/downgrades and reinstalls (R08). No real merchant charges or test claims without evidence.
5. **P1 – Scopes, checkout and storefront-safe behavior:** close R02/R09/R11 with scope rationale and GraphQL-only code evidence.
6. **P1 – Listing and reviewer artifacts:** close R10 with genuine app footage/screenshots and a reviewer account securely provided in the Partner form.
7. **Final gate:** execute official Shopify AI Toolkit `/shopify-app-store-review` in a local checkout of the final `main` SHA; resolve findings, attach output, rerun build/CI and capture signed-off Partner checklist. Only then consider marking AI self-review completed and submitting.

## Repro commands (not executed in this session)

From a checkout at the assessed SHA, after installing project dependencies:

```bash
cd backend
python -m tools.shopify_review_source_preflight --config ../shopify.app.toml
python -m pytest -q tests/test_shopify_review_source_preflight.py tests/test_shopify_managed_installation.py tests/test_shopify_compliance_webhooks.py tests/test_shopify_billing_channel_guard.py
cd ../frontend
npm test
npm run build
```

> Check that these specific test paths and scripts are present and supported before running; use the project's actual CI commands as authoritative. No command in this document changes Partner configuration.

## Official references

- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
- https://shopify.dev/docs/apps/launch/app-store-review/pass-app-review
- https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review
- https://shopify.dev/docs/apps/launch/protected-customer-data
- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/build/ai-toolkit

**Assessment owner / outcome:** source review only; `NO-GO` until the explicitly external and functional gates above are evidenced. Shopify alone decides App Store approval.
