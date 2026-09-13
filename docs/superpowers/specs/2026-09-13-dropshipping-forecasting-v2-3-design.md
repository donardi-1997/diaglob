# Dropshipping Analytics V2.3 — Store Forecasting Design

Date: 2026-09-13
Status: Design approved; written spec pending user review
Scope: Store-level forecasting for Dropshipping Analytics

## 1. Purpose

V2.3 adds deterministic, auditable forecasting to Diaglob's dropshipping analytics. For each store it forecasts, for the next 7 and 30 days:

- delivered orders;
- delivered revenue;
- contribution profit when Unit Economics is complete;
- known-cost contribution when Unit Economics is incomplete.

Every available forecast exposes a central estimate, probable range, confidence, selected model, and backtesting diagnostics. Numerical forecasting does not use an LLM or external AI model.

## 2. Fixed product decisions

1. V2.3 is **store-first**. Product/SKU forecasting is deferred.
2. Horizons are exactly **7 days** and **30 days**.
3. Every forecast returns `estimate`, `lower_bound`, and `upper_bound`.
4. Limited-history stores may still receive a forecast, but confidence is forced low and ranges widen.
5. Direct targets are delivered orders, delivered revenue, and contribution/known-cost contribution.
6. Delivery, cancellation, confirmation, and return rates remain historical diagnostics, not direct forecast targets.
7. Unit Economics incompleteness does not suppress all financial forecasting. It produces `known_cost_contribution_forecast`, never a falsely complete contribution-profit forecast.
8. The engine is deterministic and adaptive: candidate models are compared with rolling backtesting and the best one is selected independently per metric.
9. Confidence is independent per metric and horizon.
10. Forecasts always start after the latest completed day in `Store.timezone`; dashboard `date_from`/`date_to` filters do not affect them.
11. Forecasts are calculated on demand. V2.3 adds no forecast persistence, scheduled training, or model tables.
12. Forecasting is an independent Analytics section and may fail without blanking the rest of the dashboard.

## 3. Non-goals

V2.3 does not:

- forecast products, variants, campaigns, customers, closers, or channels;
- use LLMs for numeric prediction;
- create an ML microservice;
- persist forecasts or model artifacts;
- model future promotions, holidays, planned ad budgets, supplier events, or manual scenarios;
- perform FX conversion;
- infer missing Unit Economics costs;
- expose partial known-cost contribution as final contribution profit;
- add scheduled forecast alerts;
- change existing historical accounting semantics.

## 4. Authoritative historical semantics

V2.3 reuses the current dropshipping definitions.

### Delivered orders

A delivered order is an `Order` whose current `lifecycle_status == "delivered"`.

### Delivered revenue

Delivered revenue is `Order.total_amount` for orders currently in delivered status.

### Calendar day

Daily series are grouped in the store's configured `Store.timezone`. `Order.created_at` is converted to the store-local calendar date before bucketing.

Because lifecycle status is current state, historical observations may change if an order later changes status. This matches the existing dashboard and remains intentional.

## 5. Forecast anchor

Let `local_today` be the current date in `Store.timezone`.

- `forecast_anchor_date = local_today - 1 day`
- history includes only completed local days through the anchor;
- the in-progress current local day is excluded;
- 7d covers `[local_today, local_today + 7 days)`;
- 30d covers `[local_today, local_today + 30 days)`.

Invalid persisted timezone values are not silently replaced with server timezone. The forecast endpoint returns a stable error/unavailable condition.

## 6. Historical series

All inputs are daily series.

- Missing dates between the first observation and anchor are materialized as zero.
- Zero-sales days are real observations and are never dropped.
- Maximum lookback is the latest 365 completed days.
- If history is shorter, use all available completed days.
- Fewer than 7 daily observations => affected metric is `unavailable` with reason `insufficient_history`.
- Fewer than 28 days => confidence cannot exceed `low`.

This prevents cold-start estimates from appearing more certain than the evidence supports.

## 7. Candidate models

The candidate set is small, fixed, deterministic, and pure.

### `recent_naive`

Constant daily forecast based on the recent 7-day level. This is the baseline and simplest eligible model.

### `weighted_moving_average`

Recency-weighted average over a fixed recent window. Weights and window are named implementation constants covered by tests.

### `linear_trend`

Least-squares trend over a bounded recent history window. Delivered-order and revenue daily predictions are floored at zero. Non-finite results disqualify the candidate.

### `weekday_trend`

Linear trend plus weekday effect. Eligible only with at least 28 daily observations and sufficient weekday coverage. Weekday effects are shrunk toward neutral when support is low.

## 8. Rolling backtesting and model selection

For every metric independently:

1. build chronological history;
2. create rolling cutoffs;
3. fit each eligible candidate using only data before each cutoff;
4. forecast the validation period;
5. compare against actual held-out data;
6. aggregate errors;
7. select the candidate with best historical predictive performance.

Primary diagnostics:

- MAE;
- sMAPE when mathematically meaningful.

Selection uses normalized error when valid and deterministic MAE fallback for zero-heavy/degenerate series.

Tie-breaking favors simplicity in this fixed order:

1. `recent_naive`
2. `weighted_moving_average`
3. `linear_trend`
4. `weekday_trend`

This prevents unstable model switching for negligible differences.

Seven-day backtest windows are always used when sufficient history exists. Thirty-day backtest windows are additionally used when enough history exists to produce at least two meaningful 30-day validation windows. Otherwise 30-day uncertainty/confidence is derived conservatively from shorter-window residual behavior and is never allowed to exceed the 7-day confidence solely because long-window validation is unavailable.

## 9. Probable ranges

Available forecasts contain:

- `estimate`
- `lower_bound`
- `upper_bound`

Ranges are calibrated from out-of-sample residuals of the selected model, not a hard-coded percentage around the estimate.

The product language is **probable range**, not a guaranteed statistical confidence interval.

Rules:

- use a robust residual quantile/dispersion estimate;
- widen deterministically when backtest sample count is low;
- orders/revenue: estimate and bounds cannot be negative;
- contribution may be negative;
- all values must be finite;
- `lower_bound <= estimate <= upper_bound` after normalization.

## 10. Confidence

Allowed values:

- `low`
- `medium`
- `high`

Confidence is based on:

1. history length;
2. usable/non-zero signal volume;
3. backtest window count;
4. backtest error.

Hard rules:

- history <28 days => `low`;
- insufficient backtest windows => `low`;
- high normalized error => `low`;
- `high` requires adequate history, sufficient signal, and low error;
- 30d confidence may be lower than 7d.

Thresholds are named constants with unit tests. The API exposes the evidence used to classify confidence; the label is never opaque.

## 11. Contribution forecasting

Contribution forecasting reuses Unit Economics V2.2 semantics and does not duplicate payment/COD/shipping/return/Meta rules.

### 11.1 Historical daily contribution series

V2.3 constructs a daily contribution target for the same bounded historical lookback used by forecasting.

Order-resolvable components are calculated using existing V2.2 rules:

- delivered revenue;
- COGS;
- outbound shipping;
- payment fees;
- COD fees;
- reverse logistics.

Meta Ads is not attributed to orders. Forecasting resolves Meta spend **once for the entire historical lookback**, using the existing exact-period store-level resolver. If Meta spend is available and currency-compatible, its aggregate is allocated uniformly across completed history days solely to construct the analytical daily forecasting series:

`daily_meta_allocation = historical_meta_spend / history_days`

This allocation:

- is forecasting-only analytical smoothing, not ad attribution;
- exactly reconciles back to the authoritative historical Meta aggregate;
- requires one provider resolution for the lookback, not one call per day;
- is never exposed as an order/product ad cost.

If Meta is missing, it is not invented. The contribution target becomes known-cost contribution and remains explicitly incomplete.

### 11.2 Complete Unit Economics

When every mandatory historical component is available, the adaptive engine forecasts the daily complete contribution series and returns:

`metric = "contribution_profit_forecast"`

### 11.3 Incomplete Unit Economics

When any mandatory component is missing, the same series contains only resolved known costs and returns:

`metric = "known_cost_contribution_forecast"`

The response must include:

- `data_quality.status = "incomplete"`;
- `missing_components`;
- `missing_reasons`;
- no complete contribution-profit label.

Missing components remain semantically missing even though known-cost arithmetic excludes them.

### 11.4 Future assumption

Contribution forecasting is a time-series continuation of the historical contribution/known-cost contribution series. It does not claim to know future Meta budget, fee changes, or cost-policy changes. The UI must describe it as a forecast based on recent observed/configured economics.

## 12. Service architecture

Business logic remains in `backend/app/services/`.

Add `dropshipping_forecasting.py` as orchestration with focused pure helpers/modules for:

- timezone/day-boundary conversion;
- historical series construction;
- candidate model math;
- rolling backtests/model selection;
- residual ranges;
- confidence classification;
- response assembly.

Database/provider access stays outside pure model math.

Forecasting may refactor narrowly reusable Unit Economics primitives, but there must remain one authoritative implementation of cost rules.

No migration is expected. If implementation proves persistence is required, stop and treat that as a design change.

## 13. API

Add:

`GET /api/stores/{store_id}/analytics/dropshipping/forecast`

Permission: `analytics.read`.

Requirements:

- validate active store;
- enforce organization and store ownership;
- enforce membership store access;
- use `Store.timezone` and `Store.currency`;
- accept no historical date filters.

Top-level response contains:

- `store_id`
- `currency`
- `timezone`
- `generated_at`
- `forecast_anchor_date`
- history metadata
- `horizons.7d`
- `horizons.30d`

Each horizon contains:

- `date_from`
- `date_to_exclusive`
- `delivered_orders`
- `delivered_revenue`
- `contribution`

Each available metric contains at least:

```json
{
  "status": "available",
  "estimate": 42.0,
  "lower_bound": 34.0,
  "upper_bound": 51.0,
  "confidence": "medium",
  "model": "weekday_trend",
  "quality": {
    "history_days": 104,
    "observations": 104,
    "backtest_windows": 10,
    "error_metric": "smape",
    "error_value": 14.2
  }
}
```

Unavailable metrics remain structurally present:

```json
{
  "status": "unavailable",
  "reason": "insufficient_history",
  "estimate": null,
  "lower_bound": null,
  "upper_bound": null,
  "confidence": "low",
  "model": null,
  "quality": {
    "history_days": 4,
    "observations": 4,
    "backtest_windows": 0,
    "error_metric": null,
    "error_value": null
  }
}
```

Stable metric-level reasons include:

- `insufficient_history`
- `backtest_unavailable`
- `non_finite_model_output`

Invalid timezone may fail the whole forecast section with a stable API/service error because every metric shares the same calendar basis.

Unexpected programming/provider failures are not disguised as fake forecasts.

## 14. Frontend

Forecasting becomes the seventh independent dropshipping Analytics section.

Extend the existing `Promise.allSettled` fetch set with:

`getDropshippingForecast(storeId)`

Do **not** pass dashboard `dateFrom`/`dateTo`.

Update the section registry/index mapping so forecast rejection does not affect other analytics and all-sections-failed remains correct.

Add `DropshippingForecast` with:

- 7d and 30d views;
- delivered orders card;
- delivered revenue card;
- contribution card;
- estimate + probable range;
- localized low/medium/high confidence badge;
- short model/backtesting note;
- per-metric unavailable state;
- section unavailable state;
- explicit partial label and missing-cost warning for known-cost contribution.

No complex chart is required in V2.3.

Complete contribution label: `Contribución proyectada`.

Incomplete contribution label: `Contribución proyectada con costos conocidos`, visibly marked `Parcial`.

## 15. Defensive behavior

Tests and implementation must prevent:

- tenant/store leakage;
- invalid timezone fallback;
- inclusion of partial current day;
- dropped zero-sales days;
- zero-denominator sMAPE failures;
- NaN/Infinity;
- negative order/revenue ranges;
- inverted ranges;
- one bad candidate crashing all candidates;
- missing Unit Economics components becoming complete zero;
- dashboard-wide failure from forecast rejection.

If one candidate fails, disqualify it and evaluate remaining candidates. If all candidates fail for a metric, return that metric unavailable.

## 16. Performance

On-demand calculation is bounded by:

- max 365 daily observations;
- four candidate models;
- bounded rolling windows;
- aggregate SQL/in-memory passes rather than one query per day;
- one Meta historical spend resolution at most for contribution series construction.

Do not add a heavyweight ML framework solely for V2.3. Prefer Python standard-library math or lightweight dependencies already present.

## 17. Security and tenancy

Every data path must preserve:

- `organization_id` scoping;
- `store_id` scoping;
- membership store access;
- no cross-store or cross-tenant cold-start pooling;
- no provider credentials/raw sensitive errors in responses or logs.

## 18. Required tests

### Pure model tests

- constant series;
- recent level shift;
- linear trend;
- weekday seasonality;
- weekday ineligibility under short history;
- deterministic tie-breaking;
- zero-heavy/all-zero series;
- non-finite candidate rejection;
- residual range widening;
- non-negative count/revenue bounds;
- negative contribution allowed;
- different 7d/30d confidence;
- <7 observations unavailable;
- <28 observations forced low confidence.

### Timezone tests

- local anchor calculation;
- UTC-midnight edge cases;
- positive/negative offsets;
- DST-aware IANA zone;
- partial current local day excluded;
- invalid timezone behavior.

### Service/API tests

- tenant isolation;
- membership restrictions;
- active-store validation;
- no date-filter dependency;
- exact 7d/30d bounds;
- zero-day materialization;
- model metadata serialization;
- complete Unit Economics -> complete contribution forecast;
- incomplete Unit Economics -> known-cost contribution forecast;
- Meta uniform analytical allocation exactly reconciles to period spend;
- no per-day Meta provider loop;
- missing components propagate;
- no NaN/Infinity JSON;
- route contract includes exactly the new endpoint.

### Frontend tests

- seventh `Promise.allSettled` section mapping;
- forecast failure isolation;
- all-sections-failed count updated;
- 7d/30d rendering;
- estimate/range formatting;
- confidence localization;
- partial contribution labeling;
- insufficient-history state;
- no dashboard date params sent to forecast endpoint.

## 19. Acceptance criteria

V2.3 is complete only when:

1. Stores with >=7 completed observations can obtain deterministic 7d/30d delivered-order and revenue forecasts.
2. Available forecasts include estimate, probable range, confidence, model, and backtest diagnostics.
3. Selection is rolling-backtest-driven and deterministic.
4. Short history cannot produce inflated confidence.
5. Store-local current partial day is excluded.
6. Complete Unit Economics yields `contribution_profit_forecast`.
7. Incomplete Unit Economics yields explicitly partial `known_cost_contribution_forecast` with missing components.
8. Historical Meta spend uses at most one exact-period resolution and forecasting-only uniform daily allocation that reconciles to the aggregate.
9. Missing costs never become semantically complete zero.
10. Endpoint is tenant/store isolated and protected by `analytics.read`.
11. Forecast failure does not break the existing Analytics dashboard.
12. No NaN/Infinity, negative order/revenue bounds, or inverted ranges escape serialization.
13. Existing historical analytics contracts remain backward compatible except for the intentionally added route/section.
14. Targeted tests and full CI are green before merge.

## 20. Deferred follow-ups

Later versions may add:

- product/SKU demand and stockout forecasting;
- persisted forecast-vs-actual snapshots;
- holidays/promotions/events;
- future ad-budget scenarios;
- conservative/base/aggressive planning;
- forecast-driven Decision Intelligence alerts;
- hierarchical store/product reconciliation;
- richer forecast charts;
- learned ensembles after sufficient production evidence exists.
