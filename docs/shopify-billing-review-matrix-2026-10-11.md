# DIAGLOB — Shopify Billing review matrix

Date: 2026-10-11

## Review contract

Shopify App Store billing is deliberately separate from DIAGLOB direct/Paddle billing.

| Requirement | Shopify review contract |
|---|---|
| Public plans | Starter, Growth, Pro |
| Starter | USD 19/month or USD 190/year |
| Growth | USD 49/month or USD 490/year |
| Pro | USD 99/month or USD 990/year |
| Trial | 3 days on every public Shopify plan |
| Billing periods | Monthly and annual only |
| Scale | Direct/Paddle or future enterprise only; never a Shopify public plan |
| Plan selection | Shopify-hosted pricing page |
| Subscription authority | Shopify Partner activeSubscription |
| Paddle checkout | Forbidden for Shopify-managed organizations |

The application code treats this as an allowlisted contract, but Partner Dashboard remains authoritative for the plans, actual handles, prices, and trial. A code constant is not evidence that a three-day Shopify trial has been configured.

## Automated coverage

Backend regression tests must prove:

1. The Shopify public catalog contains exactly Starter, Growth, and Pro.
2. The expected trial configuration is three days.
3. Only monthly (EVERY_30_DAYS) and annual (ANNUAL) periods are recognized.
4. Starter resolves at USD 19 monthly and USD 190 annual.
5. Growth resolves at USD 49 monthly and USD 490 annual.
6. Pro resolves at USD 99 monthly and USD 990 annual.
7. Scale is rejected by Shopify entitlement resolution.
8. Unknown handles, incorrect prices, zero-dollar commercial contracts, unsupported intervals, and ambiguous multi-item subscriptions fail closed.
9. Shopify-managed tenants never fall back to Paddle checkout.
10. A plan transition can only be applied after a fresh Partner API verification and the server-side entitlement gate is enabled.

## Partner / development-store E2E

Run the following on the authorized DIAGLOB development store after App Pricing is enabled and the three plans exist in Partner Dashboard.

### Initial selection

| Case | Merchant action | Expected Shopify state | Expected DIAGLOB result |
|---|---|---|---|
| S-M | Select Starter monthly | Starter / EVERY_30_DAYS / 3-day trial | Partner subscription verifies as Starter, period 1 |
| S-A | Select Starter annual | Starter / ANNUAL / 3-day trial | Partner subscription verifies as Starter, period 12 |
| G-M | Select Growth monthly | Growth / EVERY_30_DAYS / 3-day trial | Partner subscription verifies as Growth, period 1 |
| G-A | Select Growth annual | Growth / ANNUAL / 3-day trial | Partner subscription verifies as Growth, period 12 |
| P-M | Select Pro monthly | Pro / EVERY_30_DAYS / 3-day trial | Partner subscription verifies as Pro, period 1 |
| P-A | Select Pro annual | Pro / ANNUAL / 3-day trial | Partner subscription verifies as Pro, period 12 |

For each initial selection, capture Partner `activeSubscription` evidence after merchant approval. Confirm `trialEndsAt` corresponds to the Shopify-configured three-day trial. Do not infer the duration from a redirect parameter or DIAGLOB UI copy.

### Tier changes

Every directed pair must work without reinstalling the application or contacting support:

| From | To | Expected result |
|---|---|---|
| Starter | Growth | Shopify owns approval/proration; fresh Partner verification resolves Growth |
| Starter | Pro | Shopify owns approval/proration; fresh Partner verification resolves Pro |
| Growth | Starter | Shopify owns downgrade timing; fresh Partner verification eventually resolves Starter |
| Growth | Pro | Shopify owns approval/proration; fresh Partner verification resolves Pro |
| Pro | Starter | Shopify owns downgrade timing; fresh Partner verification eventually resolves Starter |
| Pro | Growth | Shopify owns downgrade timing; fresh Partner verification eventually resolves Growth |

DIAGLOB must not guess whether a downgrade is immediate or end-of-cycle. The current Partner subscription and any pending update are the authority.

### Billing-period changes

For each public plan, exercise:

- monthly -> annual
- annual -> monthly

The application must verify the period returned by Shopify before changing internal `billing_period_months`. A same-tier cadence change is still a billing transition and must not be treated as a no-op.

### Cancellation and invalid state

Verify these cases separately:

- cancellation scheduled: DIAGLOB must not apply a newly staged paid-plan transition;
- inactive subscription: paid feature access is suspended after confirmed provider state;
- unknown/changed price or handle: access moves to review-required instead of silently mapping a plan;
- Partner API outage: do not falsely cancel a previously active contract solely because Shopify could not be reached;
- uninstall/reinstall during verification: reject stale evidence and require a new verification.

## Reviewer flow

1. Enter DIAGLOB from the authorized Shopify development-store installation.
2. Open **Planes y facturación**.
3. Confirm the page identifies billing as Shopify-managed and shows Starter / Growth / Pro, three-day trial, and monthly/annual billing.
4. Click **Abrir planes de Shopify**. The destination must be the Shopify Admin hosted pricing page for the authenticated shop; DIAGLOB does not accept a browser-supplied shop or plan handle as proof.
5. Select/approve a plan in Shopify.
6. Return to DIAGLOB and run **Verificar suscripción**.
7. When Shopify reports a different recognized plan/period, DIAGLOB records a transition requiring review.
8. The owner stages the transition and checks its freshness.
9. Only when the production entitlement gate is intentionally enabled may the owner apply it; DIAGLOB re-queries Shopify immediately before changing internal entitlements.
10. Repeat the tier-change and cadence-change matrix.

## Release gates

### Code-ready when

- backend tests are green;
- frontend build/tests are green;
- the three-plan catalog is visible in the Shopify billing workspace;
- Shopify organizations cannot access Paddle plan checkout;
- Scale and 3/6-month billing are rejected from the Shopify public billing path.

### Partner-ready when

- Shopify App Pricing is enabled for the existing DIAGLOB app;
- Starter, Growth, and Pro exist with the approved monthly/annual prices;
- every public plan has a three-day free trial;
- actual Partner plan/item handles are stored in the server-side allowlist;
- the trusted Partner app GID and least-privileged Partner API token are configured securely;
- the development-store matrix above has passed with captured evidence.

### Review-ready when

- the reviewer account can install/open DIAGLOB;
- the Shopify-hosted plan selector opens successfully;
- at least one initial trial selection is demonstrated end-to-end;
- an upgrade and a downgrade are demonstrated and independently reverified from Partner API;
- no Paddle checkout or external payment request appears for a Shopify-managed merchant.

No code change in this branch creates Shopify plans, changes Partner Dashboard pricing, charges a merchant, or provisions Partner credentials.
