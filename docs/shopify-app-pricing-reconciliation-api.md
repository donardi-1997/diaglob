# Shopify App Pricing — authenticated read-only reconciliation endpoint

Status: **development branch only**; no production deployment, no entitlement mutation, no merchant charges.

Endpoint: `GET /api/billing/shopify/reconciliation-preview`

This endpoint is available only to an authenticated DIAGLOB organization **owner** or **manager**. It uses the existing membership/tenant resolver (and organization context header where required). The request accepts **no** shop, plan handle, price, or customer identifier supplied by the browser.

Requirements before any Shopify Partner API call:

- The organization must already have the server-controlled `billing_provider = "shopify"`. This PR does **not** assign the contracting channel.
- Exactly one connected Shopify `CommerceConnection` must belong to the selected organization and an active, non-deleted store of that same organization.
- The underlying service verifies the shop identity with Shopify Admin API and cross-checks it against the Partner API subscription.
- Paddle billing fields remain untouched and legacy subscription ambiguity is rejected.

Successful responses contain the current/target plan and billing period plus `requires_review=true` and `applied=false`. They intentionally omit Shopify tokens, handles and shop GIDs. `409` represents a reviewable organization/plan conflict; `503` represents missing or unavailable Shopify configuration. Nothing is persisted or granted.

Prerequisites still pending: Partner API secret, existing-app GID, real verified App Pricing handles, server-controlled Shopify billing provenance at installation, explicit multisite policy, and an approved entitlement-sync state machine. Do not consider this endpoint a billing integration completion.

Verification: automated unit tests mock all provider calls and cover RBAC, non-Shopify orgs, zero/multiple stores, read-only behavior, secret hygiene and error handling. Run full backend CI on the final PR head; frontend/mobile need not be changed.

Tracking: issue #148 and draft PR #149.
