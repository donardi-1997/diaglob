# Dropshipping Analytics V2.1 — Decision Intelligence

## Status
Approved in chat for specification on 2026-09-11. This document defines the architecture and behavior to implement after explicit review of this written spec.

## Context
Diaglob already has a strong descriptive analytics layer for dropshipping operations:

- overview metrics and previous-period comparison;
- lifecycle funnel (created, confirmed, shipped, delivered, cancelled, returned, unknown);
- delivered-order profitability (revenue, COGS, gross profit, gross margin, profit per delivered order, cost completeness);
- Product Analytics V2 with per-product lifecycle, contribution, variants, inventory and daily trends;
- sales attribution for AI and human closers;
- partial-failure resilience so healthy analytics remain visible when one section fails.

The next gap is not more descriptive charts. The product needs to translate existing evidence into deterministic, explainable operating decisions.

## Goal
Add a Decision Intelligence layer to Dropshipping Analytics that answers: **what requires attention, what is working, and what action should the operator consider next?**

The first version must be deterministic and explainable. It must not use an LLM to invent diagnoses or recommendations.

## Non-goals
This iteration does **not** include:

- paid-media ROAS or CAC calculation;
- shipping/provider fee ingestion;
- payment gateway fee accounting;
- contribution margin beyond the existing delivered revenue minus recorded COGS model;
- statistical forecasting or ML;
- automated price, inventory or campaign changes;
- database migrations;
- new background jobs;
- cross-store ranking in one insight response.

Those belong to later Unit Economics and Forecasting phases.

## Architecture

### New backend service
Create `backend/app/services/dropshipping_decision_intelligence.py`.

This service consumes existing dropshipping analytics primitives rather than duplicating SQL aggregation wherever practical. Its responsibilities are:

1. obtain per-product performance for the requested organization/store/range;
2. calculate stock runway from current inventory and observed delivered-unit velocity;
3. evaluate deterministic insight rules;
4. attach structured evidence and a recommended action key;
5. sort and cap insights consistently;
6. return a summary suitable for the frontend.

The existing `dropshipping_analytics.py` remains the source of operational/product metrics. Decision rules stay isolated so thresholds can evolve without destabilizing core analytics.

### API
Add:

`GET /api/stores/{store_id}/analytics/dropshipping/insights`

Query parameters:

- `date_from` — same parsing semantics as current dropshipping analytics;
- `date_to` — same inclusive date-only semantics as current dropshipping analytics;
- `limit` — integer, default 20, minimum 1, maximum 50.

Security and scoping:

- use the existing active-store validation;
- require `analytics.read`;
- scope strictly by `membership.organization_id` and `store_id`;
- never mix products or orders from another tenant/store.

No new router group or permission is introduced.

## Response contract

The endpoint returns:

```json
{
  "generated_at": "2026-09-11T19:00:00Z",
  "date_from": "2026-09-01T00:00:00",
  "date_to": "2026-09-12T00:00:00",
  "currency": "COP",
  "summary": {
    "critical": 1,
    "warning": 2,
    "opportunity": 1,
    "positive": 1,
    "products_evaluated": 8
  },
  "insights": [
    {
      "id": "stock_runway:123",
      "type": "stock_runway",
      "severity": "critical",
      "product_id": 123,
      "title_key": "stock_runway_critical",
      "action_key": "replenish_stock",
      "reason_key": "stock_runway_below_threshold",
      "evidence": {
        "inventory_quantity": 6,
        "units_delivered": 21,
        "units_per_day": 3.0,
        "stock_runway_days": 2.0
      }
    }
  ]
}
```

### Stable enums

`severity` is one of:

- `critical`
- `warning`
- `opportunity`
- `positive`

`type` is one of:

- `negative_margin`
- `low_margin`
- `cost_incomplete`
- `delivery_risk`
- `cancellation_risk`
- `return_risk`
- `stockout`
- `stock_runway`
- `revenue_concentration`
- `profit_concentration`
- `winner`
- `opportunity`

The API returns machine-readable keys rather than localized prose. The frontend owns ES/EN/PT-BR copy. This avoids backend language coupling and makes insight behavior testable.

## Evidence and confidence rules

### General rule
A diagnosis must not claim more than the available data supports.

If profitability is incomplete, the system must not label a product as definitively loss-making based on partial COGS. Instead it emits `cost_incomplete` and suppresses margin-dependent `negative_margin`, `low_margin`, `winner`, and `opportunity` diagnoses for that product.

### Minimum sample thresholds
Operational rate insights require enough observations to avoid noisy alerts:

- delivery risk: at least 5 shipped orders;
- cancellation risk: at least 5 total orders;
- return risk: at least 5 shipped orders;
- winner: at least 3 delivered orders and at least 5 total orders;
- opportunity: at least 2 delivered orders and at least 5 total orders;
- stock runway: at least 3 delivered units in a complete selected date range.

Products below thresholds can still produce deterministic conditions such as `stockout` or `cost_incomplete`, but not rate-based conclusions.

## Insight rules

Thresholds are intentionally simple and deterministic for V2.1. They are product rules, not statistical claims.

### 1. Negative margin
Emit `negative_margin` / `critical` when:

- `profitability_complete == true`;
- delivered orders > 0;
- `gross_profit < 0`.

Recommended action: `review_price_and_cost`.

### 2. Low margin
Emit `low_margin` / `warning` when:

- profitability is complete;
- delivered orders >= 3;
- `gross_profit >= 0`;
- `gross_margin < 20%`.

Recommended action: `improve_unit_economics`.

### 3. Incomplete cost coverage
Emit `cost_incomplete` / `warning` when:

- delivered orders > 0;
- `cost_completeness_pct < 100`.

Evidence includes coverage percentage and delivered order count.

Recommended action: `complete_product_costs`.

### 4. Delivery risk
Emit `delivery_risk` / `warning` when:

- shipped orders >= 5;
- `delivery_rate < 60%`.

Recommended action: `review_fulfillment_quality`.

### 5. Cancellation risk
Emit `cancellation_risk` / `warning` when:

- total orders >= 5;
- `cancellation_rate > 25%`.

Recommended action: `review_confirmation_and_offer`.

### 6. Return risk
Emit `return_risk` / `warning` when:

- shipped orders >= 5;
- `return_rate > 15%`.

Recommended action: `review_product_expectations`.

### 7. Stockout
Emit `stockout` / `critical` when:

- current inventory is 0;
- delivered units in the selected period > 0.

Recommended action: `replenish_stock`.

### 8. Stock runway
Runway is only calculated when both `date_from` and `date_to` exist and define a positive complete range.

Formula:

`units_per_day = delivered_units / selected_period_days`

`stock_runway_days = inventory_quantity / units_per_day`

Rules:

- if delivered units < 3, do not emit runway insight;
- if units/day <= 0, runway is undefined;
- if inventory == 0, emit `stockout` instead of `stock_runway`;
- runway < 3 days => `stock_runway` / `critical`;
- runway >= 3 and < 7 days => `stock_runway` / `warning`;
- runway >= 7 days => no stock runway alert.

Runway values are rounded to one decimal for the response.

Recommended action: `replenish_stock`.

### 9. Revenue concentration
Emit `revenue_concentration` / `warning` when:

- at least 2 products have delivered revenue > 0;
- one product has `revenue_share_pct >= 50%`.

Recommended action: `diversify_product_mix`.

### 10. Profit concentration
Emit `profit_concentration` / `warning` when:

- at least 2 products have positive gross profit;
- one product has `profit_share_pct >= 50%`.

Recommended action: `diversify_profit_sources`.

### 11. Winner
Emit `winner` / `positive` when all are true:

- profitability complete;
- total orders >= 5;
- delivered orders >= 3;
- gross margin >= 30%;
- delivery rate >= 70%;
- cancellation rate <= 20%;
- return rate is null or <= 10%;
- gross profit > 0.

Recommended action: `consider_scaling`.

A product may still produce concentration or stock-risk insights alongside `winner`; positive performance does not hide operational risk.

### 12. Opportunity
Emit `opportunity` / `opportunity` when all are true:

- profitability complete;
- total orders >= 5;
- delivered orders >= 2;
- gross margin >= 30%;
- delivery rate >= 70%;
- cancellation rate <= 20%;
- return rate is null or <= 10%;
- `revenue_share_pct < 15%`;
- gross profit > 0;
- product does not qualify as `winner`.

Recommended action: `test_more_volume`.

## Conflict and suppression behavior

Rules are not globally mutually exclusive, but contradictory diagnoses are suppressed:

- `cost_incomplete` suppresses margin-dependent `negative_margin`, `low_margin`, `winner`, and `opportunity`;
- `negative_margin` suppresses `low_margin`, `winner`, and `opportunity`;
- `winner` suppresses `opportunity`;
- `stockout` suppresses `stock_runway`;
- risk insights can coexist with concentration insights;
- stock risk can coexist with winner/opportunity.

This lets a product be both commercially strong and operationally risky without generating logically contradictory cards.

## Ordering

Sort insights by:

1. severity rank: `critical`, `warning`, `opportunity`, `positive`;
2. deterministic type priority within severity;
3. larger relevant magnitude where useful (for example lower runway first, more negative profit first, higher cancellation/return risk first);
4. product title/id as a stable tie-breaker.

Apply `limit` only after complete evaluation and ordering.

## Frontend

### New component
Add a dedicated component, expected name:

`frontend/src/components/DropshippingDecisionInsights.tsx`

It appears near the top of `DropshippingOverview`, after any global partial-data warning and before the existing KPI grids.

### UX structure
The section title is localized as the equivalent of **“Qué requiere tu atención”** / “What needs your attention”.

Display order follows backend severity.

Each insight card shows:

- localized title;
- localized concise reason;
- 1–3 evidence values from the structured payload;
- localized recommended action;
- product name when product-specific;
- severity treatment;
- a `Ver producto` / `View product` action when `product_id` exists.

### Product navigation
Clicking a product insight must open/select the corresponding product in Product Analytics V2 rather than navigating to an unrelated route.

Implementation should use a small explicit selected-product contract between `DropshippingDecisionInsights`, `DropshippingOverview`, and `ProductPerformanceAnalytics`. Avoid DOM querying or synthetic click hacks.

### Localization
Provide complete ES, EN and PT-BR copy for:

- section headings;
- insight titles;
- reasons;
- action labels;
- evidence labels;
- empty state;
- temporary-unavailable state.

No raw backend key should be visible to users.

### Failure isolation
Decision Intelligence is an additional analytics section, not a dependency for the existing dashboard.

If `/insights` fails:

- existing overview, profitability, products and order funnel remain usable;
- show the insights section as temporarily unavailable;
- do not turn the entire analytics page into an error state.

The existing partial-resilience philosophy must be preserved.

## Data range semantics

The insights endpoint uses the exact selected range already supplied by the analytics page.

- all lifecycle/profitability rules work with an omitted range using existing all-time analytics semantics;
- previous-period comparison is not needed for V2.1 insight generation;
- stock runway is deliberately omitted when a complete bounded range is not provided because all-time velocity would be misleading;
- `date_to` remains exclusive internally after date-only inclusive parsing, matching current analytics behavior.

## Error handling

- Invalid dates use the existing `400` range parsing behavior.
- Inactive/foreign stores return `404` through existing store validation.
- A product with no orders generates no performance/rate insight.
- An empty store returns `200` with zero counts and `insights: []`.
- Missing cost data does not raise; it generates `cost_incomplete` when relevant.
- No division by zero may produce `Infinity`, `NaN`, or serialization errors.

## Testing strategy

### Backend TDD
Add focused tests for:

- empty store;
- strict tenant/store isolation;
- incomplete cost suppression;
- negative margin;
- low margin;
- delivery risk threshold boundary;
- cancellation risk threshold boundary;
- return risk threshold boundary;
- zero inventory with recent delivered units;
- stock runway critical/warning/no-alert boundaries;
- omitted date range suppressing runway only;
- concentration requiring at least two contributing products;
- winner rule;
- opportunity rule;
- winner suppressing opportunity;
- stable severity ordering and limit;
- API permission/store/date-range contract.

Use deterministic fixtures and assert structured evidence, not localized prose.

### Frontend TDD
Cover:

- severity ordering as returned;
- localization mapping ES/EN/PT-BR;
- evidence rendering;
- unavailable insights without hiding healthy existing analytics;
- empty insight state;
- product insight opening Product Analytics V2 detail;
- no raw translation key leakage.

### Final verification
Before merge:

- focused backend tests green;
- frontend tests green;
- frontend lint green;
- production frontend build green;
- full backend shards green;
- final PR diff reviewed for scope;
- normal repository validation workflow green.

## Files expected to change
Likely implementation scope:

- `backend/app/services/dropshipping_decision_intelligence.py` (new)
- `backend/app/api/dropshipping_analytics.py`
- `backend/tests/test_dropshipping_decision_intelligence.py` (new)
- existing dropshipping API contract tests if needed
- `frontend/src/services/analytics.ts`
- `frontend/src/components/DropshippingOverview.tsx`
- `frontend/src/components/DropshippingDecisionInsights.tsx` (new)
- `frontend/src/components/ProductPerformanceAnalytics.tsx` for explicit selection contract
- targeted frontend analytics tests
- analytics CSS/i18n resources as needed

No schema/model migration is expected.

## Rollout and compatibility

The change is additive:

- no existing analytics endpoint is removed or renamed;
- no existing response field is changed;
- existing Product Analytics V2 remains functional independently;
- insight generation relies only on data already present in Diaglob;
- no production backfill is required.

## Future phases enabled by this design

This Decision Intelligence contract becomes the foundation for later work without coupling the first release to it:

1. Unit Economics: advertising, shipping, payment, COD and return costs;
2. alert subscriptions and Operations Center surfacing;
3. configurable thresholds by organization/market;
4. forecasting and replenishment recommendations;
5. optional natural-language summaries generated from structured evidence, never as the source of truth.

## Acceptance criteria

The feature is complete when a store operator can open Dropshipping Analytics and immediately see deterministic, evidence-backed insights about product profitability, operational risk, concentration, stock runway and scaling opportunities; each product-specific insight can open the existing Product Analytics V2 detail; incomplete data is represented honestly; and failure of this new layer cannot take down the existing analytics dashboard.
