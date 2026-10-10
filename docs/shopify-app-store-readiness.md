> **Release status update — 2026-10-10 (PR #149)**
>
> PR #147 was merged on 2026-10-10. This document's original audit matrix
> below describes the earlier b9e3c30 checkout and must not be read as a
> fresh certification of the current PR head. The PR now contains additional
> privacy backlog, synthetic export/redaction, review-workflow and billing
> reconciliation **preview** components. These do not provide an audited live
> privacy-fulfillment or subscription-activation workflow.
>
> The release-evidence evaluator in
> `backend/app/services/shopify_release_readiness.py` deliberately defaults
> to **NOT READY**. Tests enforce that missing, partial or non-boolean evidence
> cannot clear a release gate. Do not claim Shopify compliance, merge for
> production, deploy, charge merchants or submit the app based on passing CI
> alone. Independent verification of legal retention, all processors/backups,
> redaction/export, billing entitlements, OAuth E2E, scopes, checkout policy,
> live Partner Dashboard and final-head CI remains required.

# DIAGLOB Shopify App Store readiness

Audit date: 2026-10-09  
Scope: `shopify-compliance-prep` at local commit `b9e3c303` plus its current uncommitted regression fixes; `main` at `2c65900`; draft PR #147 reviewed separately.
This document is an engineering readiness record, not confirmation that Shopify has approved the app or that the live Partner Dashboard is configured correctly.

## Compliance matrix

| Requirement | Status | Evidence | Action |
|---|---|---|---|
| Public app distribution | BLOCKED | Partner listing still reports Draft and zero public plans in the supplied context; draft PR #147 says installation is disabled pending review. | Finish submission requirements and obtain Shopify review approval. |
| Shopify billing for App Store customers | FAIL | `backend/app/billing_providers/registry.py` registers Paddle only; existing billing orchestration is provider-neutral. Shopify policy requires Shopify App Pricing for new public apps. | Implement Shopify App Pricing subscription lifecycle as a separate provider; do not route App Store merchants to Paddle. |
| Paddle for independent customers | PASS | Existing provider remains the default for legacy organizations; contract tests assert that behavior. | Preserve Paddle channel and document organization/provider assignment before Shopify merchant onboarding. |
| Mandatory privacy webhooks | BLOCKED | The signed callback and subscription setup cover `customers/data_request`, `customers/redact`, and `shop/redact`. The handler only records an event digest and does not export, anonymize, or erase personal/shop data. | Define the data inventory, retention schedule, legal holds, and scope for each event; implement effective export/redaction; test against isolated fixtures; confirm subscriptions in Dev Dashboard. Do not claim privacy fulfillment until all applicable handlers act on data. |
| OAuth HMAC and state | PARTIAL | Existing OAuth service validates callback HMAC and one-use stored state; the backend regression suite passes on this checkout. The actual Partner Dashboard configuration and full live installation flow remain unverified. | Verify active Dev Dashboard callback/scopes and exercise install/reinstall in a development store after the app is distributable. |
| Token encryption | PARTIAL | `shopify_security.py` encrypts persisted access tokens with Fernet; configuration depends on production key. | Confirm secret rotation and key presence through approved secret management; no production credential was read or changed for this audit. |
| Embedded app/session authentication | FAIL / NOT VERIFIED | Existing platform uses DIAGLOB login and OAuth connection flow. No evidence of embedded App Bridge ID-token/session-token flow was found in reviewed entrypoints. | Confirm app architecture in Dev Dashboard; if embedded, implement App Bridge authentication without third-party cookies/localStorage dependencies. |
| Minimum API scopes | FAIL | `backend/app/shopify_oauth.py` requests order/draft-order and merchant-fulfillment write scopes plus customer/order reads. | Map each scope to a merchant-visible feature; remove unnecessary write scopes or make optional where supported. Explain Protected Customer Data need in the listing/review form. |
| Checkout/order compliance | BLOCKED | Existing COD and order creation paths include Shopify mutations; PR #147 addresses stock/product constraints but review of all order mutations and buyer checkout semantics is outstanding. | Verify every buyer transaction goes through Shopify checkout; document manual order creation/COD case against current policy before submission. |
| Accurate product availability | PARTIAL | Draft PR #147 adds explicit availability, active/positive-price filters and safeguards zero inventory from being treated as verified supplier stock. | Integrate/review #147 first; run its final-head CI before dependent work. |
| Uninstall and reinstall | PARTIAL | OAuth state and connection deletion paths exist. The mandatory `shop/redact` callback now acknowledges and records only; it does not clean stored shop data. | Implement lifecycle revocation/redaction after retention analysis; exercise reinstall and revocation in a development store. |
| Listing, demo and reviewer credentials | FAIL | No confirmed English listing package, screencast, or verified review account was found during this repository audit. | Use the prepared copy below; capture real interface/demo and supply functioning reviewer credentials in Partner Dashboard. |
| TLS / public links | NOT VERIFIED | Production domain details were supplied, but endpoints and terms/privacy content were not fetched in this run. | Verify `https://diaglob.tech/privacy`, `/terms`, frontend and API health externally before submission. |

## Verification on this checkout

- Backend: `pytest -q --tb=short` from `backend/` — **1388 passed**, 7413 warnings, 810.97 seconds. The working temporary directory was under `work/pytest-tmp`.
- Backend lint: Ruff on `backend/app` and `backend/tests` — **passed**.
- Route contract and compliance webhook regression tests — passed after adding the compliance route to the route snapshot and aligning the handler with the shared Shopify connection resolver.
- Frontend tests: `npm test` — **88 passed**. Frontend build: `npm run build` — **passed**; Vite reported existing large-chunk and ineffective dynamic-import warnings. Frontend lint: **0 errors, 156 warnings**.
- Frontend dependency installation used the committed `package-lock.json`; npm reported **2 high-severity dependency advisories**. No dependency upgrades were applied.
- Shopify CLI self-review — **not run**: Shopify CLI is not installed, and the package-manager launcher failed with Windows `EPERM` while resolving the frontend directory.
- GitHub Actions for the current checkout — **not run**: the branch has not been pushed. Existing PR #147 CI is separate and is not evidence for this branch.

## Billing design and plan catalog

Keep the provider-neutral orchestration and existing Paddle adapter. App Store organizations must have a Shopify-specific provider selected from trusted installation/channel provenance; legacy and directly contracted organizations keep Paddle. Provider selection must happen server-side and must not be user-editable through ordinary plan selection. The current `billing_provider` field is sufficient to select a provider but the Shopify adapter, webhook event state machine, identity mapping, and idempotency receipts are not implemented yet.

Do not create Shopify subscriptions or activate paid plans until the merchant approves the confirmation screen. Shopify App Pricing is the intended path for a new public app; use the current supported API and Partner Dashboard flow. Shopify’s current docs distinguish app pricing from legacy Billing API flows, so confirm feature availability for this app and account before implementation.

Current canonical backend limits (`backend/app/plan_limits.py`):

| Plan | Monthly USD | Annual USD | Active stores | Monthly customers | Members | Included AI responses/month |
|---|---:|---:|---:|---:|---:|---:|
| Starter | 19 | 190 | 1 | 1,000 | 2 | 1,000 |
| Growth | 49 | 490 | 2 | 5,000 | 5 | 5,000 |
| Pro | 99 | 990 | 5 | 20,000 | 10 | 20,000 |
| Scale | 199 | 1,990 | 10 | 50,000 | 15 | 50,000 |

The supplied historical audit says frontend/backend Pro and Scale store limits differed. Current frontend organization UI reads `active_store_limit` from the API; no duplicate local plan-limit catalog was found in the inspected frontend. This should be rechecked against PR #147/current default branch after integration rather than inventing another limit source.

### Shopify public plan setup (manual draft)

Shopify supports monthly and annual recurring pricing for App Store plans. Prepare these plan names/descriptions; configure the exact available intervals and values in the Partner Dashboard, then verify the public plan count changes before submission.

| Plan | Price | English description |
|---|---:|---|
| DIAGLOB Starter | $19/month or $190/year | Connect one store and manage up to 1,000 monthly customers, two team members, and 1,000 included AI responses. |
| DIAGLOB Growth | $49/month or $490/year | Connect up to two stores and manage up to 5,000 monthly customers, five team members, and 5,000 included AI responses. |
| DIAGLOB Pro | $99/month or $990/year | Connect up to five stores and manage up to 20,000 monthly customers, ten team members, and 20,000 included AI responses. |
| DIAGLOB Scale | $199/month or $1,990/year | Connect up to ten stores and manage up to 50,000 monthly customers, fifteen team members, and 50,000 included AI responses. |

The plan-limit phrasing above reflects repository values, not verified entitlements for features or overages. Do not advertise usage overages or unverified integrations.

## Protected Customer Data application draft (English)

**Name and email.** DIAGLOB requests customer identity data to associate Shopify orders and support merchant service workflows, order context, and the merchant’s configured customer conversations. The data is used only within the merchant’s DIAGLOB organization and is not used to sell customer profiles or for unrelated advertising.

**Phone.** Phone data may be present in Shopify order/customer records and is needed only where the merchant uses a phone-based messaging or order-support workflow. If a feature does not need phone access, DIAGLOB should not request or retain it for that feature.

**Address.** Shipping and billing address fields may be included in order data so the merchant can review fulfillment and order-support context. DIAGLOB must not use address data for unrelated purposes.

**Orders.** Order identifiers, line items, totals, status, timestamps, and associated customer fields support order synchronization, operational reporting, customer support, and automation configured by the merchant. Shopify checkout remains the checkout for buyers.

**Protection and access.** Shopify API access is scoped to the merchant-approved permissions. Persisted Shopify access tokens are encrypted by the backend using a configured Fernet key. Tenant data is associated with the DIAGLOB organization/store. Do not claim at-rest encryption for all customer fields, role-based access completeness, or a fixed retention period until separately evidenced.

**Retention and deletion.** Exact retention periods and deletion coverage are not yet verified. DIAGLOB records mandatory data-request/redaction callbacks without exposing personal data in logs. The redaction handler currently does not erase or anonymize source records; complete the data inventory and retention review before submitting a claim of deletion completion. Requests must be completed within Shopify’s required timeframe unless legal retention obligations apply.

**Access controls.** Access is intended for the merchant’s authorized DIAGLOB organization members and backend service processes. The application must continue validating organization/store boundaries for every customer/order query; cross-organization access must not be possible.

## App Store listing draft (English)

**App card subtitle**  
Connect store operations, orders, automations, and AI support in one workspace.

**Introduction**  
DIAGLOB helps ecommerce teams coordinate store operations from one workspace. Connect Shopify, review synced products and orders, and use DIAGLOB’s operational tools and AI assistant with the data available to your team.

**Detailed description**  
DIAGLOB brings ecommerce operations into a shared workspace. Connect a Shopify store, review synchronized catalog and order information, coordinate work with your team, and configure operational automations. DIAGLOB also includes an AI assistant that can use the context and tools enabled for your organization. Product availability depends on the information Shopify and connected providers make available; supplier inventory is not guaranteed by a Shopify inventory value of zero. DIAGLOB does not replace Shopify checkout.

**Key features**

- Sync Shopify products and order lifecycle information into your DIAGLOB workspace.
- Review store operations with organization-level access and plan limits.
- Configure operational automations using supported integrations.
- Use an AI assistant with the available store context and enabled tools.
- Keep Paddle billing for independent DIAGLOB contracts; Shopify App Store subscriptions are intended to use Shopify billing.

**Search keywords**  
ecommerce operations, order management, product sync, dropshipping operations, ecommerce automation, AI customer support

**Support**  
Email: support@diaglob.tech  
Website: https://diaglob.tech  
Privacy: https://diaglob.tech/privacy  
Terms: https://diaglob.tech/terms

**Reviewer instructions (draft; replace bracketed values)**  
1. Install DIAGLOB on the provided development store and approve the requested Shopify permissions.
2. Sign in with the test account: `[reviewer email]` / `[reviewer password]`.
3. Open Integrations → Shopify and confirm that the connected store displays its `.myshopify.com` domain.
4. Run the catalog sync, then review active products and order synchronization using the supplied test data.
5. Open the AI assistant and ask about a product marked active in the test catalog. Do not use a real customer or create a real order.
6. To verify privacy handling, use Shopify’s test webhook delivery for the three compliance topics and confirm successful HTTP responses. No destructive redaction action is claimed by this draft implementation.

## Demo video outline

Record the actual English interface, with English narration or subtitles:

1. Start at the Shopify App Store listing and choose Install.
2. Approve Shopify permissions; show the return to DIAGLOB and the exact connected shop.
3. Show onboarding, connection status, selected store, and plan/billing state.
4. Sync a development catalog and show an active product plus a draft/unavailable product excluded from recommendation.
5. Show a read-only order list and a product question in the AI assistant.
6. Show automation configuration only for a scenario that works end-to-end in the current release.
7. Show where the merchant disconnects/uninstalls and where to contact support.

Use test data and redact any credentials, customer PII, or real merchant records in the recording.

## Partner Dashboard checklist

1. **App configuration:** verify the production callback URLs, scopes, redirect URLs, embedded setting, and current API version against the running backend.
2. **Emergency developer contact:** add a monitored contact in Partner Dashboard settings.
3. **App icon:** upload an original square icon meeting the current image specifications; original artwork is still needed if not in the repository.
4. **Primary language:** set English; retain Spanish in DIAGLOB’s application interface.
5. **Protected customer data:** submit only after confirming requested fields/scopes, retention, encryption claims, and data subject process.
6. **Automated checks:** resolve every issue and retain the result/date for the final report.
7. **App Store listing:** use the draft copy above after confirming every claim against production behavior; add real English screenshots and demo screencast.
8. **Public plans:** create public plan entries and confirm Shopify’s “at least one plan” validation clears; do not activate a charge without authorization.
9. **Testing credentials:** provide a non-production merchant and DIAGLOB test account with working end-to-end permissions.
10. **Review instructions:** replace placeholders, state the supported scenarios and disclose any setup needed for connected services.
11. **Submission readiness:** submit only after privacy redaction, billing, install, checkout, scopes, and full final-head CI are verified.

## Pilot Bakatá status

From issue #146 and draft PR #147: pilot shop `0djnem-9x.myshopify.com`; twelve products were previously observed (eight ACTIVE and four DRAFT, with the draft examples priced at zero); reviewed Shopify inventory was zero; no DIAGLOB app installation was present. PR #147 says Shopify currently disables installation pending review, and three requested Flow Builder scenarios are unsupported while the simulate endpoint only validates structure. No real order, payment, fulfillment, inventory change, or customer message should be used for acceptance. Recheck live shop state after Shopify enables the app; prior audit evidence may have changed.

## Official sources

- [Shopify App Store requirements](https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements)
- [About billing for your app](https://shopify.dev/docs/apps/launch/billing)
- [Privacy law compliance](https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance)
- [About app authentication](https://shopify.dev/docs/apps/build/authentication-authorization)
- [App Store quality checks](https://shopify.dev/docs/apps/launch/app-store-review/app-quality-checks)
