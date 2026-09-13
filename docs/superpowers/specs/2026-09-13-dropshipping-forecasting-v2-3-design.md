# Dropshipping Analytics V2.3 — Store Forecasting Design

Date: 2026-09-13
Status: Design approved; written spec pending user review
Scope: Diaglob dropshipping analytics, store-level forecasting, Unit Economics integration, analytics UI

## 1. Purpose

Dropshipping Analytics V2.3 adds deterministic, store-level forecasting on top of the existing operational analytics and Unit Economics layers.

The feature answers three forward-looking questions for each store:

1. How many delivered orders are likely in the next 7 and 30 days?
2. How much delivered revenue is likely in the next 7 and 30 days?
3. How much contribution profit, or known-cost contribution when Unit Economics is incomplete, is likely in the next 7 and 30 days?

The design prioritizes auditability and calibrated uncertainty. Forecasts are not presented as exact predictions. Every forecast reports an expected value, a probable range, confidence, backtesting diagnostics, and data-quality information.

V2.3 deliberately avoids generative AI for numerical prediction. Model selection is deterministic and based on historical predictive performance for the selected store.

## 2. Approved product decisions

1. Forecasting is **store-first** in V2.3. Product/SKU demand forecasting is deferred.
2. Horizons are exactly **7 days** and **30 days**.
3. Every metric returns **central estimate + lower/upper probable bounds**.
4. Stores with limited history still receive forecasts when technically possible, but with `low` confidence and wider ranges.
5. Direct forecast metrics are:
   - delivered orders;
   - delivered revenue;
   - contribution profit when Unit Economics is complete;
   - known-cost contribution when Unit Economics is incomplete.
6. Delivery, cancellation, confirmation, and return rates remain historical diagnostics in V2.3 and are not separately forecast.
7. If Unit Economics is incomplete, Diaglob does **not** suppress all contribution forecasting. It exposes an explicitly partial metric named `known_cost_contribution_forecast` and reports missing cost components.
8. The forecasting engine is **adaptive but deterministic**: it evaluates several simple candidate models with rolling backtesting and selects the best model independently for each metric.
9. Forecast confidence is determined independently per metric and horizon.
10. Forecasts always start from the most recent completed local calendar day for the store. They do not depend on the dashboard's historical `date_from` / `date_to` filters.
11. Forecasting is computed on demand in V2.3. No forecast snapshots, training jobs, or new persistence tables are required.
12. Forecasting is a new independently-failing analytics section. A forecast failure must not take down existing overview, profitability, product, order, insight, or Unit Economics analytics.

## 3. Non-goals

V2.3 does not:

- forecast at product, variant, SKU, campaign, closer, customer, or channel level;
- predict delivery/cancellation/return rates directly;
- use LLMs or external AI APIs to generate numerical forecasts;
- train or deploy a separate ML service;
- persist forecast snapshots or model artifacts;
- perform probabilistic Bayesian modeling;
- perform causal attribution or answer why future sales will change;
- model explicit marketing plans, future ad budgets, promotions, holidays, supplier events, stock constraints, or manual business assumptions;
- perform FX conversion;
- invent missing Unit Economics costs;
- present partial known-cost contribution as complete contribution profit;
- add automated alerts or scheduled forecast notifications;
- change existing historical dropshipping accounting semantics.

These are candidates for later versions once V2.3 has sufficient live-history validation.

## 4. Existing semantics remain authoritative

V2.3 reuses current dropshipping definitions rather than introducing a second accounting vocabulary.

### 4.1 Delivered orders

A delivered order is an `Order` whose current `lifecycle_status == "delivered"`.

Daily delivered-order history is grouped by the store's configured `Store.timezone`, using `Order.created_at` converted to the store's local calendar day.

The current-state lifecycle caveat remains: because lifecycle status is mutable, historical daily values may change if an order later changes to returned/cancelled/etc. This is consistent with existing analytics behavior.

### 4.2 Delivered revenue

Daily delivered revenue is the sum of `Order.total_amount` for orders currently in delivered status, grouped by the same local calendar day semantics.

### 4.3 Contribution

Contribution semantics come from Unit Economics V2.2.

When all applicable mandatory Unit Economics components for the historical evaluation window are complete, the forecasted financial metric is `contribution_profit_forecast`.

When one or more mandatory cost components are missing, V2.3 may still forecast the **known-cost contribution** derived from recognized revenue minus costs that are actually known/resolved for the historical window. This metric must be named and labeled distinctly and must carry `data_quality.status = "incomplete"` plus `missing_components`.

V2.3 must never relabel known-cost contribution as final contribution profit.

## 5. Forecast anchor and calendar semantics

Forecasting operates in the store's configured timezone.

Let `local_today` be the current date in `Store.timezone`.

The latest completed day is:

`forecast_anchor_date = local_today - 1 day`

Historical observations end at the end of `forecast_anchor_date`. The in-progress local day is excluded to avoid systematic undercounting caused by partial-day data.

The forecast horizons begin on `local_today`:

- 7-day horizon: local dates `[local_today, local_today + 7 days)`
- 30-day horizon: local dates `[local_today, local_today + 30 days)`

The service response includes the anchor and forecast date bounds explicitly.

Timezone conversion must be implemented centrally and tested for at least:

- UTC-offset zones;
- negative UTC offsets;
- positive UTC offsets;
- DST-aware IANA zones where applicable.

If a persisted store timezone is invalid, forecasting fails with a stable service error rather than silently falling back to server time.

## 6. Historical series construction

### 6.1 Frequency

All model inputs use daily observations.

Missing calendar dates between the first observation and the forecast anchor are materialized as zero-valued days. This is essential because absence of orders on a day is an observation, not missing data.

### 6.2 History window

V2.3 uses available store history ending at the forecast anchor, subject to a practical maximum lookback to keep on-demand computation bounded.

Recommended implementation limit:

- use up to the most recent 365 completed days;
- use all available completed days when history is shorter.

This limit is an implementation-performance boundary, not a user setting.

### 6.3 Minimum history

The engine should attempt a forecast whenever at least 7 completed daily observations can be constructed.

If fewer than 7 completed observations exist, the endpoint still returns a stable response but the affected metric is `unavailable` with reason `insufficient_history` rather than fabricating an estimate.

History shorter than 28 days is automatically `low` confidence even if backtesting error appears small.

### 6.4 Sparse stores

Zero-heavy series are valid. The engine must not discard zero-sales days.

A store with long sequences of zeros may legitimately receive a forecast near zero. Confidence is governed by history length, volume, and backtesting behavior, not by a rule that forces positive sales.

## 7. Candidate forecasting models

V2.3 evaluates a small fixed model set. All candidates must be pure, deterministic functions with no network calls and no stochastic state.

### 7.1 Recent naive

Forecast each future day using a recent level estimate.

Recommended form:

- median or mean of the last 7 completed daily observations;
- same constant daily expectation across the horizon.

This is the robust baseline and must always be available when minimum history exists.

### 7.2 Weighted moving average

Forecast from a recency-weighted average of recent history, with newer days carrying greater weight.

The exact fixed window/weights belong in implementation constants and tests, not mutable user configuration in V2.3.

### 7.3 Linear trend

Fit a deterministic least-squares linear trend to a bounded recent history window and extrapolate daily values.

For non-negative business metrics, daily point forecasts are floored at zero before aggregation.

The implementation must cap unreasonable numerical behavior and reject non-finite results.

### 7.4 Trend + weekday seasonality

Estimate a linear trend plus multiplicative or additive weekday adjustment derived from observed Monday-Sunday behavior.

This candidate is eligible only when there is enough history to estimate weekday effects responsibly. Recommended eligibility threshold: at least 28 daily observations with adequate weekday coverage.

Weekday adjustments must be regularized/shrunk toward neutral when sample counts are low so one anomalous weekday cannot dominate the forecast.

## 8. Adaptive model selection by rolling backtesting

### 8.1 Principle

Model choice is based on out-of-sample historical performance, not in-sample fit.

For each forecast metric independently, the engine creates rolling backtest cutoffs over the available history. At each cutoff:

1. train/evaluate the candidate using only observations before the cutoff;
2. forecast a fixed validation window;
3. compare prediction to known actual observations;
4. aggregate error across windows.

### 8.2 Validation horizons

Model selection should be aligned to the product horizons while remaining computationally bounded.

Recommended approach:

- evaluate short-window prediction error using rolling 7-day validation windows;
- derive 30-day reliability from the same selected model plus longer-horizon residual scaling when enough history exists;
- optionally add 30-day backtest windows only when history is long enough.

The implementation plan may refine the exact rolling-window schedule, but it must remain deterministic and covered by tests.

### 8.3 Error metrics

Use metrics that behave reasonably across monetary and count series:

- `MAE` as the primary absolute-error measure;
- `sMAPE` as a normalized diagnostic when denominator conditions permit.

Model selection should primarily minimize normalized error when valid, with deterministic fallback to MAE for zero-heavy or degenerate series.

The API reports the chosen selection metric and value.

### 8.4 Tie-breaking

Ties or near-ties must resolve deterministically in favor of the simpler model.

Recommended fixed simplicity order:

1. recent naive;
2. weighted moving average;
3. linear trend;
4. trend + weekday seasonality.

This prevents unstable model switching for negligible accuracy differences.

## 9. Probable ranges

Every available forecast returns:

- `estimate`;
- `lower_bound`;
- `upper_bound`.

The range is calibrated from observed out-of-sample forecast residuals, not from a hard-coded percentage around the estimate.

### 9.1 Residual-based interval

For each chosen model, collect absolute or signed aggregate backtest errors at the relevant horizon.

The probable range uses a robust residual quantile or equivalent deterministic dispersion estimate.

Recommended target is an intuitive approximately 80% probable band, but the contract should call it a `probable_range`, not a statistically guaranteed confidence interval unless formal coverage is later validated.

### 9.2 Low-history widening

When history or backtest windows are limited, apply a deterministic widening factor. This is separate from the `confidence` label and prevents narrow bands from tiny samples.

### 9.3 Safety constraints

For delivered orders and revenue:

- `estimate >= 0`;
- `lower_bound >= 0`;
- `upper_bound >= lower_bound`;
- all values finite.

For contribution metrics, negative values are allowed because contribution can be negative. Bounds must still be finite and ordered.

Delivered-order totals may be returned as numeric values. UI presentation may round counts for display, but internal/model calculations should retain numeric precision until final serialization.

## 10. Confidence classification

Confidence is computed independently for each metric and horizon.

Allowed values:

- `low`
- `medium`
- `high`

Confidence is a product-facing summary of three dimensions:

1. history sufficiency;
2. observed transaction volume / non-zero signal;
3. rolling backtest error.

### 10.1 Hard low-confidence conditions

A forecast cannot exceed `low` confidence when any of these apply:

- history < 28 completed days;
- too few valid backtest windows;
- very sparse signal relative to history;
- backtest error above a defined high-error threshold.

### 10.2 Medium/high

`medium` and `high` require both adequate history and demonstrably acceptable backtest performance.

The implementation must define thresholds as named constants with unit tests rather than scattering magic numbers through service code.

30-day confidence may be lower than 7-day confidence for the same metric.

The API exposes the diagnostics that justify the label; confidence must not be a hidden opaque score.

## 11. Unit Economics and partial contribution forecasting

### 11.1 Complete Unit Economics

If the historical Unit Economics window is complete, V2.3 forecasts:

`contribution_profit_forecast`

The historical daily target should be built from the same cost semantics as V2.2 where daily attribution is technically valid.

For costs that only exist as period-level aggregate data, especially Meta Ads spend, the engine must avoid inventing order-level attribution. A deterministic daily allocation may be used only if clearly documented as an analytical allocation solely for time-series modeling and if the aggregate exactly reconciles to the authoritative period total.

A safer implementation is to forecast contribution from forecasted revenue/orders combined with historical effective cost ratios where component completeness permits. The implementation plan should choose one method and test reconciliation explicitly.

### 11.2 Incomplete Unit Economics

If one or more mandatory components are missing:

- expose `known_cost_contribution_forecast`;
- set contribution `data_quality.status = "incomplete"`;
- include `missing_components` and `missing_reasons`;
- never populate `contribution_profit_forecast` as if complete;
- UI must label the metric as partial.

Known costs must remain based only on resolved actual/estimated V2.2 components. Missing costs are not substituted with zero for semantic purposes, even if the known-cost arithmetic naturally excludes them.

### 11.3 Currency

All financial forecasts use the store currency.

No FX conversion is introduced. If a Unit Economics dependency is incomplete due to currency mismatch, that incompleteness propagates into contribution quality metadata.

## 12. Service architecture

Business logic lives under `backend/app/services/`.

### 12.1 `dropshipping_forecasting.py`

Primary responsibilities:

- validate store timezone assumptions;
- determine forecast anchor;
- build daily historical series;
- run candidate models;
- execute rolling backtests;
- select models deterministically;
- compute probable ranges;
- classify confidence;
- assemble 7-day and 30-day forecast DTOs;
- orchestrate contribution forecasting and quality metadata;
- avoid persistence and side effects.

### 12.2 Internal pure modules/helpers

To keep the forecasting service testable, model math should be isolated from SQLAlchemy access.

Recommended separation:

- series/data extraction orchestration;
- pure candidate model functions;
- backtesting/model-selection functions;
- interval/confidence functions.

A pure-module boundary is preferred so most tests can run without a database.

### 12.3 Unit Economics reuse

Forecasting may call shared Unit Economics helpers or introduce a narrowly-scoped service adapter, but must not duplicate payment/COD/shipping/return/Meta cost rules in a second independent implementation.

If reusable daily/period cost primitives do not exist, refactor only the minimum V2.2 logic needed to establish a single authoritative cost semantic layer.

## 13. API contract

Add:

`GET /api/stores/{store_id}/analytics/dropshipping/forecast`

Permission: `analytics.read`.

Store rules:

- validate organization ownership;
- require active store, matching existing dropshipping analytics semantics;
- enforce membership store access consistently with sensitive store-scoped analytics;
- use `Store.timezone` and `Store.currency` from the validated store.

The endpoint accepts no `date_from` or `date_to`. Forecasting always uses the latest completed store-local day.

### 13.1 Illustrative response

```json
{
  "store_id": 1,
  "currency": "COP",
  "timezone": "America/Bogota",
  "generated_at": "2026-09-13T18:00:00Z",
  "forecast_anchor_date": "2026-09-12",
  "history": {
    "first_date": "2026-06-01",
    "last_date": "2026-09-12",
    "history_days": 104
  },
  "horizons": {
    "7d": {
      "date_from": "2026-09-13",
      "date_to_exclusive": "2026-09-20",
      "delivered_orders": {
        "status": "available",
        "estimate": 42.0,
        "lower_bound": 34.0,
        "upper_bound": 51.0,
        "confidence": "high",
        "model": "weekday_trend",
        "quality": {
          "history_days": 104,
          "observations": 104,
          "backtest_windows": 10,
          "error_metric": "smape",
          "error_value": 11.8
        }
      },
      "delivered_revenue": {
        "status": "available",
        "estimate": 8400000.0,
        "lower_bound": 6900000.0,
        "upper_bound": 10100000.0,
        "confidence": "medium",
        "model": "weighted_moving_average",
        "quality": {
          "history_days": 104,
          "observations": 104,
          "backtest_windows": 10,
          "error_metric": "smape",
          "error_value": 18.2
        }
      },
      "contribution": {
        "metric": "known_cost_contribution_forecast",
        "status": "available",
        "estimate": 1850000.0,
        "lower_bound": 900000.0,
        "upper_bound": 2700000.0,
        "confidence": "low",
        "model": "linear_trend",
        "data_quality": {
          "status": "incomplete",
          "missing_components": ["ad_spend"],
          "missing_reasons": {"ad_spend": "meta_not_connected"}
        },
        "quality": {
          "history_days": 104,
          "observations": 104,
          "backtest_windows": 8,
          "error_metric": "mae",
          "error_value": 420000.0
        }
      }
    },
    "30d": {
      "date_from": "2026-09-13",
      "date_to_exclusive": "2026-10-13",
      "delivered_orders": {},
      "delivered_revenue": {},
      "contribution": {}
    }
  }
}
```

Exact field factoring may be normalized during implementation, but these semantics are required.

### 13.2 Unavailable metric contract

When a metric cannot be forecast, it returns a stable object rather than disappearing:

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

Stable unavailable reasons include at least:

- `insufficient_history`
- `invalid_timezone`
- `non_finite_model_output`
- `backtest_unavailable`
- contribution-specific upstream quality reasons when relevant.

Unexpected internal errors should still use normal API error handling rather than converting every exception into a fake metric-level reason.

## 14. Frontend design

Forecasting is added as a seventh independent section in the dropshipping Analytics dashboard.

### 14.1 Fetch isolation

Extend the existing `Promise.allSettled` pattern with:

`getDropshippingForecast(storeId)`

Forecast must not receive dashboard historical date filters.

Update the analytics section registry with `forecast` so failure reporting and all-sections-failed logic remain index-safe and tested.

### 14.2 Component

Add a dedicated `DropshippingForecast` component.

Presentation:

- title such as `Pronóstico` / localized equivalent;
- two horizon tabs or side-by-side groups: `Próximos 7 días` and `Próximos 30 días`;
- cards for delivered orders, delivered revenue, and contribution;
- each card shows central estimate and probable range;
- confidence badge `Baja`, `Media`, `Alta` localized;
- short model/quality note, e.g. `Seleccionado por backtesting sobre 63 días`;
- partial-contribution warning when Unit Economics is incomplete;
- unavailable state per metric when history is insufficient;
- section-level unavailable state when the request fails.

Do not add complex forecasting charts in V2.3. The MVP emphasizes clear ranges and confidence.

### 14.3 Financial labeling

Complete contribution:

- label: `Contribución proyectada` or equivalent.

Incomplete contribution:

- label: `Contribución proyectada con costos conocidos`;
- visible `Parcial` indicator;
- show or summarize missing components;
- never use final-profit language that obscures incompleteness.

## 15. Error handling and defensive behavior

The service must defend against:

- invalid/missing timezone;
- empty history;
- insufficient history;
- all-zero history;
- extreme outliers;
- zero denominators in normalized error metrics;
- NaN/Infinity from regression/model math;
- negative count/revenue extrapolation;
- inverted probable bounds;
- stale/malformed Unit Economics dependencies;
- tenant/store leakage;
- candidate model failure.

A failure in one candidate model should disqualify that candidate when other valid candidates remain. It should not necessarily fail the whole forecast.

If all candidates for a metric fail, return that metric as unavailable with a stable reason.

## 16. Performance

V2.3 is on-demand and should remain lightweight enough for normal dashboard requests.

Controls:

- max 365 daily history points per metric;
- small fixed candidate model set;
- bounded rolling backtest windows;
- vector/math implementation using standard Python/numpy only if already acceptable in project dependencies; avoid adding a heavyweight ML framework;
- avoid one SQL query per day;
- aggregate historical data efficiently in SQL or one bounded in-memory pass.

No background training or cache is required initially.

If production profiling later shows forecast latency is material, snapshot caching can be designed as a separate version without changing the forecast response contract.

## 17. Security and tenancy

Forecasting must preserve existing multitenant guarantees.

Requirements:

- every database query filters `organization_id`;
- every store-bound query filters `store_id`;
- membership store access is enforced;
- no cross-store history pooling;
- no fallback to data from other tenants/stores for cold-start forecasts;
- no sensitive provider credentials or raw integration errors in the response.

Cold start is handled through low confidence/unavailability, not cross-tenant data sharing.

## 18. Testing strategy

### 18.1 Pure forecasting tests

Cover at least:

- constant series chooses a simple model and remains stable;
- recent level change can favor weighted moving average;
- clear linear growth can favor trend;
- clear weekday pattern can favor weekday trend when eligible;
- weekday model is ineligible with insufficient weekday history;
- deterministic tie-breaking favors simpler model;
- zero-heavy series does not divide by zero;
- all-zero series yields non-negative zero/near-zero forecasts;
- no NaN/Infinity escapes;
- count/revenue lower bounds never become negative;
- contribution bounds allow negatives but remain ordered;
- 7-day and 30-day confidence can differ;
- short history forces low confidence;
- residual-based range widens under high error;
- low-history widening is applied;
- unavailable contract for <7 observations.

### 18.2 Timezone tests

Cover:

- forecast anchor uses store-local completed day;
- orders near UTC midnight fall into the correct store-local date;
- partial current local day is excluded;
- invalid timezone produces stable behavior.

### 18.3 Service/integration tests

Cover:

- organization/store isolation;
- membership access restrictions;
- active-store validation;
- endpoint has no date-range dependency;
- 7d/30d date bounds are correct;
- history zeros are materialized;
- model diagnostics serialize correctly;
- Unit Economics complete -> `contribution_profit_forecast`;
- Unit Economics incomplete -> `known_cost_contribution_forecast`;
- missing components propagate correctly;
- missing costs are never silently treated as complete zero;
- candidate model failure can fall back to another valid model;
- no non-finite JSON values.

### 18.4 Frontend tests

Cover:

- forecast is added to `Promise.allSettled` without breaking index mapping;
- forecast failure does not blank other analytics;
- all-sections-failed logic includes forecast;
- 7d/30d switching or grouping renders correct horizon;
- estimate and range formatting;
- confidence localization;
- partial contribution label and missing-cost warning;
- insufficient-history metric state;
- API call does not forward dashboard `date_from/date_to`.

### 18.5 Route-contract tests

Update strict API route snapshots/contracts to include exactly the new forecast endpoint and no accidental route changes.

## 19. Observability

V2.3 should expose enough metadata for troubleshooting without logging sensitive data.

Recommended structured logs or diagnostics include:

- organization/store identifiers according to existing logging policy;
- history length;
- chosen model per metric;
- backtest window count;
- error metric/value;
- forecast computation duration;
- candidate failures by stable internal reason.

Do not log raw order payloads or provider credentials.

## 20. Rollout and compatibility

V2.3 is additive.

It does not change existing endpoint response contracts for:

- overview;
- profitability;
- products;
- orders;
- insights;
- Unit Economics.

Frontend should tolerate forecast endpoint absence/failure through its section-isolation behavior during staged deployments.

No database migration is expected unless implementation discovers a hard requirement; such a discovery must be treated as a design change rather than silently adding persistence.

## 21. Acceptance criteria

V2.3 is complete when:

1. A store with >=7 completed daily observations can receive deterministic 7d and 30d forecasts for delivered orders and revenue.
2. Available forecasts contain central estimate, probable bounds, confidence, model, and backtesting quality metadata.
3. Model selection is based on rolling backtesting and is deterministic.
4. Low-history stores are not presented with unjustified confidence.
5. The current partial local day is excluded using `Store.timezone`.
6. Unit Economics complete stores expose contribution profit forecasts.
7. Unit Economics incomplete stores expose explicitly partial known-cost contribution forecasts with missing components.
8. No missing cost is presented as complete zero.
9. Forecast endpoint is tenant/store isolated and uses `analytics.read`.
10. Forecast failure does not break other Analytics sections.
11. Frontend clearly distinguishes 7d vs 30d, estimate vs probable range, and complete vs partial contribution.
12. Backend/frontend targeted tests and full CI are green before merge.
13. No NaN/Infinity or invalid ordered ranges can reach the API response.
14. Existing dropshipping analytics contracts remain backward compatible except for the intentionally added route/section.

## 22. Deferred follow-ups

Potential later versions:

- product/SKU demand forecasting and stockout prediction;
- forecast snapshots and historical forecast-vs-actual tracking;
- holiday/promotion/event regressors;
- future Meta budget/scenario inputs;
- scenario planning: conservative/base/aggressive;
- automated anomaly/forecast alerts;
- forecast-driven Decision Intelligence recommendations;
- hierarchical reconciliation between store and product forecasts;
- richer charts and forecast-vs-actual visualization;
- learned ensemble models after sufficient production data exists.

These are explicitly outside V2.3.
