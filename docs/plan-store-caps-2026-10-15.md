# DIAGLOB — reduced store capacity per organization (2026-10-15)

**Decision for the DIAGLOB direct SaaS catalog:** simplify the active-shop tiers
instead of marketing up to ten active stores.

| Plan | Old effective API limit | New limit | USD/month | USD/year |
|---|---:|---:|---:|---:|
| Starter | 1 | 1 | 19 | 190 |
| Growth | 2 | 2 | 49 | 490 |
| Pro | 5 | **3** | 99 | 990 |
| Scale | 10 | **5** | 199 | 1990 |

- Aligned `backend/app/plan_limits.py` with the previously divergent
  `backend/app/plans.py`, already set to 1/2/3/5.
- Updated the pricing cards on the authenticated and public frontend pages.
  Existing i18n Pro/Scale feature copy already says 3 and 5 respectively.
- Enforcement via `get_organization_limits` applies to new active store
  creation / reactivation; the reduction does **not** automatically delete or
  deactivate any existing store. Organizations currently above the new cap
  cannot activate additional stores. Check for existing excess usage and
  decide a customer-safe grandfathering/migration policy before rollout.
- Customers, team members, included AI responses, prices, billing periods,
  three-day Shopify App Pricing trials, direct Paddle semantics and quotas
  for all other resources are unchanged.
- Shopify App Pricing and direct DIAGLOB tenancy remain different contracts:
  **a 3-/5-store DIAGLOB organization limit is not a 3-/5-shop Shopify
  subscription**. Current Shopify verification fails closed on multiple shop
  installations in the same org. Do not advertise multi-store inclusion to
  Shopify App Store merchants until that contract is separately implemented.
- Shopify Scale availability is a separate product decision. The backend
  Shopify Partner subscription validator still lists only Starter/Growth/Pro;
  no change here makes Scale eligible for Shopify.
- Historical financial sensitivity tables are estimates and do not
  certify actual AI usage or variable costs.

## Suggested regression coverage

```bash
cd backend
pytest -q tests/test_plan_store_caps.py tests/test_organization.py tests/test_shopify_app_pricing.py
```

The new contract tests verify Pro 3 / Scale 5, parity across both backend
limit catalogs, block-on-next-activation behavior, no store mutation and
Shopify inactive-contract suspension. GitHub CI additionally validates the
frontend bundle and regressions.

**App Store approval remains NO-GO** until Shopify billing lifecycle E2E,
privacy fulfillment, protected customer data/scopes, checkout review and
reviewer listing are verified independently.
