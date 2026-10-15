# DIAGLOB — Shopify pricing, plan limits and contribution sensitivity
Audit: 2026-10-10 · Owner: ChatGPT · **ANALYTICAL SCENARIOS, NOT OBSERVED P&L OR PRICE APPROVAL**

> Store-limit amendment (2026-10-15): Pro is 3 active stores and Scale is 5
> instead of the earlier 5/10 values. Pricing, customer/member/AI limits and
> assumptions in this historical analysis are otherwise unchanged.
> The multiple-store organization limit is for direct DIAGLOB tenancy; it is
> NOT approval to bundle Shopify merchant installs under one App Pricing
> subscription.

## Verified in code
Source: `backend/app/plan_limits.py` and existing App Store draft `docs/shopify-app-store-readiness.md`.

| Plan | Current proposed monthly USD | Annual USD | Active stores | Monthly customers | Team members | Included AI responses/month |
|---|---:|---:|---:|---:|---:|---:|
| Starter | 19 | 190 | 1 | 1,000 | 2 | 1,000 |
| Growth | 49 | 490 | 2 | 5,000 | 5 | 5,000 |
| Pro | 99 | 990 | 3 | 20,000 | 10 | 20,000 |
| Scale | 199 | 1,990 | 5 | 50,000 | 15 | 50,000 |

Annual price equals 10 monthly payments (approximately **16.7% less than paying monthly for 12 months**) in each tier. Existing software limits are not proof of enforcement of every AI quota or data-processing obligation.

## Financial model — explicit assumptions, not Shopify's real fees

Illustrative assumptions solely to highlight risk:
- `p` = monthly list price, `q` = advertised maximum included AI responses.
- `r = 15%` is a **hypothetical** total platform/payment/revenue deduction for sensitivity. Do not present 15% as Shopify's actual charge or Partner revenue share.
- `F` per-org monthly variable cloud/support cost **assumed** $2 / $5 / $10 / $20 respectively by tier; not actual AWS or support invoices.
- `c` unit fully-loaded AI response cost scenarios $0.001 and $0.003; these are **not** measured DIAGLOB tokens/model costs.
- Contribution `= p × (1 − r) − F − q × c` at 100% of included AI capacity, excluding taxes, refunds, marketing acquisition, personnel, other external provider usage and overhead.

| Plan | Contribution at c=$0.001 | Contribution at c=$0.003 | Maximum c at 75% contribution target* |
|---|---:|---:|---:|
| Starter | $13.15 | $11.15 | $0.002038 |
| Growth | $31.65 | $21.65 | $0.001083 |
| Pro | $54.15 | $14.15 | $0.000552 |
| Scale | $99.15 | **-$0.85** | $0.000446 |

*Target equation: `p×(1−r)−F−q×c ≥ 75%×p×(1−r)`; this is a **sensitivity ceiling** and not a forecast, actual margin, or claim the model currently has a 75% margin. Full consumption by every merchant is an intentionally conservative stress case.

## Decision
- **Do not change public prices or create paid Shopify plans yet.** Owner approval is required.
- The current Pro/Scale inclusion appears economically sensitive if all included AI responses use high-token tools or expensive inference; choose limits based on **measured tokens and tool costs**, not assumed average “responses.” Dynamic tool use, retrieval, messaging, provider APIs, retries and shipping calls can cost more than one plain text generation.
- Initial recommendation for release planning: retain prices as *candidates* and implement per-organization, per-provider usage attribution; block runaway model calls and excess quota when no approved overage agreement exists.
- Evaluate whether AI limits should be reduced, standardized to usage credits, split by model/tool, or metered using Shopify App Pricing usage pricing after reviewing current supported features and approved plan copy. **Do not promise unlimited requests or usage-based overages** until implementation and charge-approval semantics are verified.
- A single subscription per shop on Shopify does not automatically correspond to DIAGLOB's **2/3/5 active stores per organization**. Current reconciliation rejects multi-shop Shopify billing; public plan marketing must clarify whether these are independent installs, additional directly contracted stores or future functionality. Until solved, don't publish multi-store promises as live Shopify entitlements.
- Paddle remains for qualifying **independent direct contracts**; Shopify App Store subscribers must not be routed through Paddle checkout.

## Measurement acceptance criteria for Codex / business owner
1. Instrument daily and monthly response counts, tokens in/out, models, guardrails, retries, AWS Bedrock inference rates, RAG/retrieval costs, automation execution, messages/API provider charges, shipping/tracking and cost attribution by organization (PII-free).
2. Reconcile quotas `plan_limits.py` vs frontend display and backend **server enforcement**; report 0, 25, 50, 75, 95, 100% utilization distributions and outliers.
3. Verify actual Shopify Partner earnings/revenue share/taxes/fees for this app and seller jurisdiction from the owner account; replace hypothetical `r` before profitability decision.
4. Simulate 10 / 50 / 100 / 500 merchants by tier mix and model usage; compute gross contribution, total fixed infrastructure, support hours and churn, with at least optimistic/base/stress cases and breakeven customer count.
5. Confirm real public plan handles/intervals in the existing Partner Dashboard, one-to-one entitlement mapping and Shopify-managed redirects; no charge without merchant approval.
6. Owner must approve final price, trial duration, annual discount, store limits, AI credits, fair-use/overage policy and early-adopter strategy **before** publishing plans.

Official source: https://shopify.dev/docs/apps/launch/billing/shopify-app-pricing
