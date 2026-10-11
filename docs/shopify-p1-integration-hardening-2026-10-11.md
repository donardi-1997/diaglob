# Shopify P1 integration hardening — 2026-10-11

**Scope:** code/test hardening only. No production deployment, installation, merchant charge, order creation, supplier mutation or customer messaging has occurred as part of this block. The Shopify App Store P0 readiness gates remain explicitly blocked by `docs/shopify-app-store-readiness.md` and `backend/app/services/shopify_release_readiness.py`.

## Implemented

1. **Catalog pagination:** Follow `product.variants.pageInfo` beyond the embedded first 100 variants, before writing the product. Repeated/missing cursors and missing product responses fail closed.
2. **GraphQL cost:** Read products five at a time to avoid requesting 50 products × 100 nested variants in one query, which can exceed Shopify's 1,000-point single-query limit. Rate limits must still be verified with a real shop.
3. **Sync result integrity:** Distinguish complete (`ok=true`) from partial (`ok=false`) runs, preserve the last successful synchronization timestamp on incomplete scans, store a non-sensitive error code, and avoid a false catalog-synced analytics event.
4. **Reconciliation:** Retire Shopify-linked products missing after a **complete** store scan, and variants missing after a **complete** individual product scan. Records are deactivated, not deleted; manual products remain untouched. Update currency for existing variant records.
5. **Webhook subscriptions:** Walk all GraphQL subscription pages before deciding whether to create order/uninstall subscriptions. Abort on missing/repeated cursors.
6. **Order changes:** Existing signed/idempotent Shopify webhooks now emit meaningful `order.updated` and `order.cancelled` transitions, while unchanged retries produce no new events. Preserve the original `order.created` idempotency key.
7. **Flow Builder:** Register order-update and cancellation triggers in the legacy event registry, durable-flow event bridge, graph validator, Spanish/English editor labels and frontend trigger types. Execution uses the existing flow runner and its configured store/customer permissions.

## Synthetic automated regression coverage

In `backend/tests/test_shopify.py`:
- Product with 101 variants fetched over two pages.
- Incomplete variant pagination flagged and no product written.
- Missing Shopify product deactivated only after a complete scan.
- Order/uninstall webhook subscriptions on page two retained without duplicate mutation.
- New Shopify orders, updates, unchanged retry and cancellation emit exactly the meaningful transitions.
- Frontend/backend supported trigger vocabulary remains aligned.
- Incomplete product cursor is a partial sync, not success.

## CI / deployment gate

- Verify final branch SHA: backend pytest (both shards), Ruff, frontend lint/test/build.
- Run API smoke in a dedicated development store with real OAuth after Shopify allows installation; verify 101+ variant catalog, partial-sync status, deleted product handling, live signed order webhook delivery and idempotence **using synthetic/test orders only**.
- Verify automation flow recipient lifecycle in a controlled environment before activating any customer-facing node. A graph validation/simulation response is **not** proof of executed side effects.
- For production deploy, verify app config, signed callback, permissions and feature flags, then enable gradually; rollback by reverting this PR and re-running sync only when authorization has been confirmed.

## Unfinished / external P1 gates (not claimed complete)

- **App Store materials:** final English listing, real UI screenshots, 1200×1200 logo export, screencast, reviewer access, support contact, Dev Dashboard and automated checks. Draft copy and evidence checklist exist in `docs/shopify-app-store-publication-kit-2026-10-10.md`; real evidence requires the installable app.
- **Bakatá OAuth and actual webhooks:** issue #146 remains blocked on App Store distribution/review. No real Bakatá connection, product synchronization or Shopify webhook delivery has been certified.
- **Supplier stock:** Shopify `inventoryPolicy=CONTINUE` and inventory zero do not prove Dropi/Dropify stock. Verify authoritative supplier availability before enabling sales.
- **Remaining Flow Builder scenarios:** internal_notification/product_unavailable and execution-level shipment/customer flows are not proven by these changes. Do not advertise unsupported workflows.
- **Catalog display completeness:** the existing Product schema persists only one image and a boolean active flag (not all Shopify image/status metadata), and per-variant currency/price histories are not modeled. A schema/product UX change is required if those are release requirements.
- **Customer privacy and hosted billing:** still P0; see issue #148. No irreversible redaction, paid plan activation or real customer transaction is in scope.

Official references:
- https://shopify.dev/docs/apps/build/apis/graphql-admin/rate-limits
- https://shopify.dev/docs/apps/launch/app-store-review/submit-app-for-review
- https://shopify.dev/docs/apps/launch/shopify-app-store/app-store-requirements
