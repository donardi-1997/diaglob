# DIAGLOB — Shopify App Store review preflight (14 Oct 2026)

**Scope: committed source, not live Shopify Partner verification. Submission: NO-GO.**
Update 15 Oct 2026: tracked TOML now matches backend OAuth scopes in PR #251. This
is a repository-only correction, not a deployed Shopify app version or merchant reauthorization.
This audit neither creates a Shopify application nor deploys app configuration,
issues Admin API queries, invokes private Partner APIs, processes customer data,
charges merchants, or modifies AWS.

## Findings checked against current GitHub `main`

1. **OAuth source scope mismatch corrected (repository only):** the tracked
   `shopify.app.toml` now declares the same eight scopes requested by
   `backend/app/shopify_oauth.py`. `write_draft_orders` is needed for
   `draftOrderCreate`; merchant-managed fulfillment access is used in
   `shopify_fulfillment.py` for `fulfillmentOrders` and `fulfillmentCreate`.
   The unused `write_products` scope was removed from the tracked TOML.
   **The active Shopify version was not updated:** confirm the exact Client ID,
   version and grants in the Partner Dashboard/CLI before deploying app
   configuration. New authorization and merchant consent may be required.
   Do not mark live OAuth as PASS based on the source change.
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

The first command should exit zero for source parity on this branch; it must
still report that external evidence and Shopify approval are not verified.
Only predefined diagnostic codes and **permission names** are emitted; no
app secrets, access tokens, shop domains or PII. Even after a clean report,
`shopify_approval_verified` and `release_authorized` remain false.

## Priorities before Shopify submission

**P0 technical:** verify active Partner version and actual OAuth grants after
reconciling the tracked source scopes;
verify embedded login/OAuth install+reinstall in `diaglob-poc.myshopify.com`;
confirm webhook subscriptions and properly signed test delivery in an
isolated environment; prove store-scoped, legally reviewed privacy requests;
verify Shopify-hosted pricing before commerce.

**P0 operator:** confirm actual current Partner checklist, review app listing
assets and support inbox, provide functional reviewer account **only in the
private Partner review form**, check authentic English-subtitled screencast
and testing instructions. Do not publish or charge based on repository CI.

**Development policy:** PR #251 remains a draft; no production deployment is
triggered by source correction. A Lightsail recovery snapshot exists, but a
reviewed deployment/rollback and live end-to-end Shopify tests are still required.

Official requirements:
- https://shopify.dev/docs/apps/launch/app-store-review/pass-app-review
- https://shopify.dev/docs/apps/launch/protected-customer-data
- https://shopify.dev/docs/apps/build/compliance/privacy-law-compliance
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
