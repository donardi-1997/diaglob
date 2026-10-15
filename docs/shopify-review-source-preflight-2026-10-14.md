# DIAGLOB — Shopify App Store review preflight (14 Oct 2026)

**Scope: committed source, not live Shopify Partner verification. Submission: NO-GO.**
This audit neither creates a Shopify application nor deploys app configuration,
issues Admin API queries, invokes private Partner APIs, processes customer data,
charges merchants, or modifies AWS.

## Findings checked against current GitHub `main`

1. **OAuth scope drift, blocking:** `shopify.app.toml` declares
   `read_customers,read_inventory,read_orders,write_orders,read_products,write_products`.
   The authorization URL generated from `backend/app/shopify_oauth.py`
   instead requests three permissions not declared in that TOML:
   `write_draft_orders`, `read_merchant_managed_fulfillment_orders`,
   `write_merchant_managed_fulfillment_orders`. Conversely,
   `write_products` is declared in the TOML but not requested by the backend.
   Do not silently grant more permissions or delete functionality: review each
   actual GraphQL call against the minimum API scopes, confirm the **active**
   version in Partner, then reconcile OAuth and the linked app configuration
   with authorized reauthorization tests if required.
2. **Embedded App Home now exists in source:** contrary to the earlier
   `docs/shopify-embedded-auth-audit.md` gap, the repository includes
   `backend/app/api/shopify_embedded.py`, App Bridge CDN, Shopify ID-token
   verification (`shopify_embedded_identity.py`), explicit Cognito and
   store/tenant authorization, and related tests. This proves **code
   presence only**. A browser install in the Shopify Admin iframe is still
   unverified, so don't mark embedding PASS in the Partner Dashboard.
3. **Mandatory privacy webhooks are represented in TOML and protected by
   HMAC in backend**, but a source file doesn't prove active Shopify
   subscriptions. Production privacy processing still lacks approved,
   end-to-end delivery/deletion across processors and backups.
4. **App Store listing is a separate Partner workflow.** The latest
   operator-provided screenshot in the repository recorded twelve listing
   issues: category, feature media, screenshots, support, pricing, search
   terms, sales channel requirements, two contact emails, reviewer test
   account, screencast and testing instructions. Draft copy is available in
   `docs/shopify-app-store-12-issue-field-pack-2026-10-11.md`. Later
   Partner changes are NOT verified.
5. **Video supplied by the operator:** `https://youtu.be/6zdgFoCWVXs`.
   Its current public/unlisted accessibility, English subtitles and coverage
   of the installed, functional app still require an authorized review.
6. **Billing:** do not assume a Shopify App Pricing plan or private USD 0
   test plan exists until verified in Partner. Do not activate live charges.

## Execute the source-only audit without external accounts

From the repository's `backend` directory with dependencies installed:

```bash
python -m tools.shopify_review_source_preflight --config ../shopify.app.toml
python -m pytest -q tests/test_shopify_review_source_preflight.py
```

The first command intentionally exits non-zero while scope drift remains.
Only predefined diagnostic codes and **permission names** are emitted; no
app secrets, access tokens, shop domains or PII. Even after a clean report,
`shopify_approval_verified` and `release_authorized` remain false.

## Priorities before Shopify submission

**P0 technical:** reconcile actual minimum scopes and active Partner version;
verify embedded login/OAuth install+reinstall in `diaglob-poc.myshopify.com`;
confirm webhook subscriptions and properly signed test delivery in an
isolated environment; prove store-scoped, legally reviewed privacy requests;
verify Shopify-hosted pricing before commerce.

**P0 operator:** confirm actual current Partner checklist, review app listing
assets and support inbox, provide functional reviewer account **only in the
private Partner review form**, check authentic English-subtitled screencast
and testing instructions. Do not publish or charge based on repository CI.

**Development policy:** PRs remain open, without merge or production deploy,
while direct Lightsail recovery is unavailable. Keep the PR #246 CI fix and
PR #247 blue/green preflight separate from Shopify review work.

Official requirements:
- https://shopify.dev/docs/apps/launch/app-store-review/pass-app-review
- https://shopify.dev/docs/apps/launch/protected-customer-data
- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
