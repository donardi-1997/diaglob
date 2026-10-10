# Shopify App Pricing — read-only entitlement reconciliation preview

**Status: staged in a development branch. No active entitlement reconciliation, checkout, merchant billing or production changes.**

`app.services.shopify_app_pricing_reconciliation.preview_shopify_entitlement_reconciliation` combines Shopify's trusted Admin API Shop GID identity verification with the Partner API's `activeSubscription` and the existing operator-controlled plan handle catalog.

The preview intentionally **does not modify** any `Organization` fields, commit a transaction, create Shopify charges, cancel plans, grant paid features, or modify Paddle subscriptions.

## Fail-closed requirements

1. `billing_provider` must already be `shopify` due to a trusted, server-side installation and contracting-provenance decision. A Shopify domain or a redirect parameter is NOT proof. Channel migration does not exist yet.
2. The `CommerceConnection.organization_id` must match the organization, and its provider must be Shopify.
3. Exactly **one trusted connected Shopify store** is currently supported per organization by the preview. The count must be calculated from tenant-scoped database state by the eventual caller, **never supplied by the browser**. DIAGLOB's existing organization-level subscription model does not yet handle multiple Shopify stores reliably.
4. Any existing legacy `billing_subscription_id` or `billing_customer_id` causes a manual-review error; do not accidentally transfer a Paddle contract.
5. A valid Admin API Shop GID, active Partner API subscription, matching shop, and exact flat-rate USD plan handle from the configured catalog are required before suggesting a target plan.
6. If Shopify reports no active subscription, return a **review-required status**; do not deactivate an existing DIAGLOB plan automatically.

Every preview returns `requires_review=true`. This is not an entitlement grant. It deliberately has no API endpoint or background schedule.

## Work needed before activation

- Verify the existing DIAGLOB Shopify App GID and provision a least-privilege Partner API client/secret.
- Complete trusted installation provenance and `billing_provider` assignment, including prevention of accidental reassignment of existing Paddle customers.
- Decide multi-Shopify-store billing: separate Shopify subscription per shop vs organization-level aggregation.
- Persist subscription verification evidence and plan transitions atomically, with idempotency and audit.
- Handle cancellation, expiry, trials, provider errors and safe periodic reconciliations.
- Route Shopify-origin signups/upgrades to the hosted Shopify pricing surface.
- Run safe E2E against a development shop. No real charges or plan activation without approval.

Related: issue #148 and draft compliance PR #149.
