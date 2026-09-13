# Dropshipping Analytics V2.3 — Store Forecasting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, auditable 7-day and 30-day store forecasts for delivered orders, delivered revenue, and complete/known-cost contribution, with probable ranges, confidence, and rolling-backtest diagnostics.

**Architecture:** Keep forecasting on demand and store-scoped. Extract only the reusable order-resolvable Unit Economics primitives needed for daily contribution without changing V2.2 semantics; build timezone-correct daily history in one bounded query/pass; run a pure standard-library forecasting engine with four deterministic candidate models and rolling backtesting; expose one thin analytics endpoint; render Forecasting as the seventh independently failing dashboard section.

**Tech Stack:** FastAPI, SQLAlchemy 2, Python 3.10 standard library (`math`, `statistics`, `datetime`, `zoneinfo`, `decimal`), pytest, React 19, TypeScript 6, Axios, node:test, Vite.

**Spec:** `docs/superpowers/specs/2026-09-13-dropshipping-forecasting-v2-3-design.md`

## Global Constraints

- No LLM, external AI model, NumPy/Pandas, new ML framework, persistence table, migration, scheduled training job, or forecast cache in V2.3.
- Forecast targets are store-level only: delivered orders, delivered revenue, and contribution/known-cost contribution.
- Horizons are exactly 7 and 30 calendar days beginning at the store-local current day.
- The store-local in-progress day is excluded from history.
- `Store.timezone` is authoritative; invalid persisted timezone is a stable section-level error, never a server-timezone fallback.
- Historical lookback is at most 365 completed local days; missing dates are explicit zero observations.
- Fewer than 7 observations makes a metric unavailable; fewer than 28 observations forces `low` confidence.
- Forecast model selection is deterministic and independent per metric.
- Candidate priority for deterministic tie-breaking is `recent_naive`, `weighted_moving_average`, `linear_trend`, `weekday_trend`.
- Probable ranges come from out-of-sample residual behavior. Never emit NaN/Infinity or inverted ranges.
- Delivered-order and revenue estimates/bounds are clamped to zero; contribution may be negative.
- Existing V2.2 cost rules remain authoritative. Do not duplicate payment, COD, shipping, return, or COGS business rules in forecasting.
- Meta Ads is resolved at most once for the historical contribution lookback and uniformly smoothed only for the analytical time series; this is not ad attribution.
- Incomplete Unit Economics returns `known_cost_contribution_forecast`, `data_quality.status = "incomplete"`, and missing component metadata. Never label partial economics as complete contribution profit.
- Forecast endpoint accepts no dashboard `date_from`/`date_to` arguments.
- Business logic belongs in `backend/app/services/`, never the API router.
- Every DB/provider path is scoped by `organization_id + store_id`; the API also enforces membership store access.
- Frontend tests must import pure utilities, not HTTP service modules, to avoid the Node 22 ESM resolution problem previously seen in V2.2.
- Existing Analytics sections must remain usable when Forecasting fails.

---

## Algorithm Constants Fixed by This Plan

These constants remove implementation-time ambiguity and must be named/exported only where tests need them:

```python
MAX_HISTORY_DAYS = 365
MIN_HISTORY_DAYS = 7
LOW_CONFIDENCE_HISTORY_DAYS = 28
RECENT_NAIVE_WINDOW = 7
WMA_WINDOW = 14
LINEAR_TREND_WINDOW = 56
WEEKDAY_TREND_WINDOW = 84
WEEKDAY_MIN_HISTORY = 28
WEEKDAY_SHRINKAGE = 3.0
SHORT_BACKTEST_VALIDATION_DAYS = 1
STANDARD_BACKTEST_VALIDATION_DAYS = 7
LONG_BACKTEST_VALIDATION_DAYS = 30
MAX_BACKTEST_WINDOWS = 8
LONG_BACKTEST_MIN_TRAIN_DAYS = 28
LONG_BACKTEST_MIN_WINDOWS = 2
SMAPE_SIGNAL_RATIO_MIN = 0.25
RANGE_QUANTILE = 0.80
LOW_SAMPLE_MULTIPLIER_LT_3 = 1.50
LOW_SAMPLE_MULTIPLIER_LT_5 = 1.25
HIGH_CONFIDENCE_ERROR_PCT = 20.0
MEDIUM_CONFIDENCE_ERROR_PCT = 40.0
HIGH_CONFIDENCE_HISTORY_DAYS = 56
HIGH_CONFIDENCE_BACKTEST_WINDOWS = 4
MEDIUM_CONFIDENCE_BACKTEST_WINDOWS = 2
MIN_SIGNAL_RATIO_FOR_HIGH = 0.25
```

Backtesting rules:

- With 7–13 observations, use expanding one-day validation cutoffs so the feature still has genuine out-of-sample residuals; only models eligible at each cutoff participate.
- With >=14 observations, model selection uses rolling 7-day validation windows, newest `MAX_BACKTEST_WINDOWS` only.
- 30-day validation uses rolling 30-day windows only when at least two windows are possible with a 28-day minimum training prefix (first point where two windows are possible is 88 observations).
- If a direct 30-day residual sample is unavailable, derive 30-day range width conservatively by linearly scaling the selected model's shorter-horizon absolute aggregate residual width (`x 30/7`, or `x 30` when only one-day residuals exist). Confidence remains `low` without two direct 30-day windows.
- sMAPE is the model-selection metric only when at least `SMAPE_SIGNAL_RATIO_MIN` of held-out points have `abs(actual) + abs(predicted) > 0`; otherwise use MAE. For confidence, convert MAE to an internal normalized percentage with `MAE / mean(abs(actual)) * 100` when scale > 0; an all-zero series gets normalized error 0 when predictions are also zero.
- Model-score ties within `1e-9` use the fixed simplicity order above.

Model definitions:

```python
recent_naive = mean(last min(7, n) observations)
weighted_moving_average = sum(value * weight) / sum(weights)
# weights are 1..window_length, oldest to newest, window <=14
linear_trend = ordinary least squares over the last min(56, n) points
weekday_trend = OLS trend over last min(84, n) points + shrunk weekday residual effect
weekday_effect = raw_weekday_mean * support / (support + WEEKDAY_SHRINKAGE)
```

`weekday_trend` requires >=28 training observations and each weekday represented at least twice. One bad/non-finite candidate is disqualified without failing other candidates.

Probable-range rules:

```python
width = quantile(abs(aggregate_backtest_residuals), 0.80)
if residual_count < 3:
    width *= 1.50
elif residual_count < 5:
    width *= 1.25
lower = estimate - width
upper = estimate + width
```

Use deterministic nearest-rank/interpolated quantile logic implemented in the pure module and covered by exact tests. For orders/revenue, clamp estimate/lower/upper to `>=0`; for contribution do not clamp. Normalize at the end so `lower <= estimate <= upper` and every number is finite.

Confidence rules:

```python
if history_days < 28 or backtest_windows < 2 or normalized_error_pct > 40:
    confidence = "low"
elif (
    history_days >= 56
    and backtest_windows >= 4
    and signal_ratio >= 0.25
    and normalized_error_pct <= 20
):
    confidence = "high"
else:
    confidence = "medium"
```

For the 30-day horizon, lack of at least two direct 30-day validation windows forces `low`, regardless of 7-day confidence.

---

## File Structure

### Backend create
- `backend/app/services/dropshipping_forecast_math.py` — pure candidate models, backtesting, scoring, intervals, confidence, response-safe numeric normalization.
- `backend/app/services/dropshipping_forecasting.py` — timezone anchor, bounded DB loading, zero-day materialization, contribution series orchestration, Meta smoothing, horizon assembly.
- `backend/tests/test_dropshipping_forecast_math.py` — pure deterministic model/backtest/range/confidence tests.
- `backend/tests/test_dropshipping_forecasting.py` — timezone, historical-series, Unit Economics/Meta orchestration tests.
- `backend/tests/test_dropshipping_forecasting_api.py` — permissions, tenancy, API contract, no date-filter dependency.

### Backend modify
- `backend/app/services/dropshipping_unit_economics.py` — expose one reusable order-resolvable economics function and optional prefetched item path; preserve current public V2.2 response exactly.
- `backend/tests/test_dropshipping_unit_economics.py` — characterization/regression coverage for the refactor.
- `backend/app/api/dropshipping_analytics.py` — add one thin forecast GET endpoint.
- `backend/tests/test_route_contract.py` — no code change expected unless test helper needs none; run/update snapshot intentionally.
- `backend/tests/contracts/api_routes.json` — add exactly `GET /api/stores/{store_id}/analytics/dropshipping/forecast`.

### Frontend create
- `frontend/src/components/DropshippingForecast.tsx` — 7d/30d cards, ranges, confidence, partial contribution state.
- `frontend/src/utils/dropshippingForecast.ts` — pure locale/presentation helpers; no Axios/React imports.
- `frontend/src/dropshipping-forecast.css` — responsive forecast section styles.
- `frontend/tests/dropshippingForecast.test.ts` — pure presentation tests.

### Frontend modify
- `frontend/src/services/analytics.ts` — forecast DTOs and `getDropshippingForecast(storeId)` with no date parameters.
- `frontend/src/utils/dropshippingAnalyticsState.ts` — register `forecast` as the seventh section.
- `frontend/tests/dropshippingAnalyticsState.test.ts` — seven-section isolation/global-failure assertions.
- `frontend/src/components/DropshippingOverview.tsx` — seventh `Promise.allSettled` call and forecast render.

---

### Task 1: Make V2.2 order-resolvable economics reusable without changing behavior

**Files:**
- Modify: `backend/app/services/dropshipping_unit_economics.py`
- Modify: `backend/tests/test_dropshipping_unit_economics.py`

**Interfaces:**

Add this public service helper:

```python
def calculate_order_resolvable_economics(
    db: Session,
    organization_id: int,
    store_id: int,
    orders: list[Order],
    *,
    config: dict[str, Any] | None = None,
    prefetched_items: list[OrderItem] | None = None,
) -> dict[str, Any]:
    """Resolve revenue + non-ad Unit Economics components for an explicit order cohort."""
```

Return exactly:

```python
{
    "recognized_revenue": float,
    "components": {
        "cogs": component,
        "outbound_shipping": component,
        "payment_fees": component,
        "cod_fees": component,
        "reverse_logistics": component,
    },
    "known_cost_subtotal": float,
    "data_quality": quality,
    "order_counts": {...},
}
```

Also expose:

```python
def summarize_unit_economics_quality(components: dict[str, dict[str, Any]]) -> dict[str, Any]:
```

- [ ] **Step 1: Add characterization tests before the refactor**

Add tests asserting the existing `get_store_unit_economics()` result remains byte-for-byte equivalent at the meaningful dict fields for:

- complete mixed delivered/returned/cancelled cohort;
- incomplete COGS with a known partial amount;
- missing payment rule with a known subtotal;
- no orders;
- returned-only negative complete contribution.

Example assertion structure:

```python
before = get_store_unit_economics(db, store.organization_id, store, DATE_FROM, DATE_TO)
assert before["recognized_revenue"] == 2500000.0
assert before["components"]["payment_fees"]["amount"] == 92000.0
assert before["data_quality"]["status"] == "complete"
```

- [ ] **Step 2: Run the existing Unit Economics suite as the GREEN baseline**

```bash
cd backend
pytest -q tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_edge_cases.py tests/test_dropshipping_unit_economics_api.py
```

Expected: PASS before production refactor.

- [ ] **Step 3: Add a failing test for prefetched items and reusable order components**

```python
result = calculate_order_resolvable_economics(
    db,
    store.organization_id,
    store.id,
    [delivered_order],
    config=_configure(db, store),
    prefetched_items=items,
)
assert result["components"]["cogs"]["amount"] == 40000.0
assert result["recognized_revenue"] == 100000.0
```

Monkeypatch `db.query(OrderItem)` or use a query counter so this path proves no item query occurs when `prefetched_items` is supplied.

- [ ] **Step 4: Implement the minimal refactor**

Change `_resolve_cogs` to accept an optional item list and filter it in memory by delivered order IDs:

```python
def _resolve_cogs(..., delivered_orders, *, prefetched_items=None):
    delivered_ids = {order.id for order in delivered_orders}
    if prefetched_items is None:
        items = db.query(OrderItem).filter(...).all()
    else:
        items = [
            item for item in prefetched_items
            if item.order_id in delivered_ids
            and item.organization_id == organization_id
            and item.store_id == store_id
        ]
```

Build `calculate_order_resolvable_economics()` from the existing resolver functions. Update `get_store_unit_economics()` to call it, append the one Meta component, run `summarize_unit_economics_quality()` over all six components, and preserve the current output contract.

Do not move formulas to forecasting.

- [ ] **Step 5: Verify no V2.2 semantic drift**

```bash
cd backend
pytest -q tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_edge_cases.py tests/test_dropshipping_unit_economics_api.py tests/test_unit_economics_meta.py
```

Expected: PASS with existing values/provenance unchanged.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dropshipping_unit_economics.py backend/tests/test_dropshipping_unit_economics.py
git commit -m "refactor: expose reusable unit economics components"
```

---

### Task 2: Implement deterministic candidate models as pure functions

**Files:**
- Create: `backend/app/services/dropshipping_forecast_math.py`
- Create: `backend/tests/test_dropshipping_forecast_math.py`

**Interfaces:**

Use focused immutable types:

```python
@dataclass(frozen=True)
class ForecastPoint:
    date: date
    value: float

@dataclass(frozen=True)
class CandidateForecast:
    model: str
    values: tuple[float, ...]

MODEL_PRIORITY = (
    "recent_naive",
    "weighted_moving_average",
    "linear_trend",
    "weekday_trend",
)
```

Public pure entry points:

```python
def forecast_candidate(
    model: str,
    history: Sequence[ForecastPoint],
    future_dates: Sequence[date],
    *,
    non_negative: bool,
) -> CandidateForecast | None:

def eligible_models(history: Sequence[ForecastPoint]) -> tuple[str, ...]:
```

- [ ] **Step 1: Write RED tests for the four model definitions**

Cover:

- constant history -> all eligible simple models remain constant;
- recent level shift -> WMA responds more than long trend;
- exact linear sequence -> `linear_trend` extrapolates expected values;
- synthetic weekday pattern -> `weekday_trend` reproduces weekday ordering;
- <28 history -> weekday model absent;
- insufficient weekday coverage -> weekday model absent;
- negative trend for non-negative target -> output floors at zero;
- negative contribution mode -> output remains negative where predicted;
- any NaN/Infinity input/output -> candidate returns `None`.

Example:

```python
def test_linear_trend_extrapolates_exact_sequence():
    history = points([10, 12, 14, 16, 18, 20, 22])
    result = forecast_candidate("linear_trend", history, next_dates(2), non_negative=True)
    assert result is not None
    assert result.values == pytest.approx((24.0, 26.0))
```

- [ ] **Step 2: Confirm RED**

```bash
cd backend
pytest -q tests/test_dropshipping_forecast_math.py -k "candidate or trend or weekday"
```

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement model math with standard library only**

Implement OLS directly:

```python
x_mean = sum(xs) / len(xs)
y_mean = sum(ys) / len(ys)
den = sum((x - x_mean) ** 2 for x in xs)
slope = 0.0 if den == 0 else sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / den
intercept = y_mean - slope * x_mean
```

For weekday effects, compute residuals against trend, group by `date.weekday()`, then shrink each mean:

```python
shrunk = raw_mean * support / (support + WEEKDAY_SHRINKAGE)
```

After fitting, reject any non-finite forecast before clamping.

- [ ] **Step 4: Run focused pure tests**

```bash
cd backend
pytest -q tests/test_dropshipping_forecast_math.py -k "candidate or trend or weekday"
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dropshipping_forecast_math.py backend/tests/test_dropshipping_forecast_math.py
git commit -m "feat: add deterministic forecast candidate models"
```

---

### Task 3: Add rolling backtesting, selection, probable ranges, and confidence

**Files:**
- Modify: `backend/app/services/dropshipping_forecast_math.py`
- Modify: `backend/tests/test_dropshipping_forecast_math.py`

**Interfaces:**

Add:

```python
@dataclass(frozen=True)
class ForecastQuality:
    history_days: int
    observations: int
    non_zero_observations: int
    backtest_windows: int
    long_backtest_windows: int
    error_metric: str | None
    error_value: float | None
    normalized_error_pct: float | None
    confidence: str

@dataclass(frozen=True)
class MetricForecast:
    status: str
    reason: str | None
    estimate: float | None
    lower_bound: float | None
    upper_bound: float | None
    confidence: str
    model: str | None
    quality: ForecastQuality
```

Main pure function:

```python
def forecast_metric(
    history: Sequence[ForecastPoint],
    *,
    horizon_days: int,
    non_negative: bool,
) -> MetricForecast:
```

- [ ] **Step 1: Write RED tests for model selection**

Cover exact deterministic outcomes:

- constant series selects `recent_naive` due tie priority;
- strong recency shift favors WMA over naive/trend when backtest error proves it;
- exact linear history favors `linear_trend`;
- weekly synthetic history >=84 days favors `weekday_trend`;
- one deliberately broken/non-finite candidate is ignored and another wins;
- all candidates invalid -> `status="unavailable", reason="non_finite_model_output"`.

- [ ] **Step 2: Write RED tests for zero-heavy error behavior**

Implement and test helpers:

```python
def mae(actual, predicted) -> float: ...
def smape(actual, predicted) -> float | None: ...
def choose_error_metric(actual, predicted) -> tuple[str, float, float]: ...
```

Required behavior:

- both zero at a point does not divide by zero;
- all-zero actual/predicted selects MAE with normalized error 0;
- low-signal series below 25% informative points uses MAE;
- no NaN/Infinity escapes.

- [ ] **Step 3: Implement rolling validation cutoffs exactly as fixed above**

Pseudo-interface:

```python
def _backtest_candidate(model, history, validation_days) -> BacktestResult | None:
    # 7–13 days: expanding one-day validations
    # >=14 days: rolling 7-day windows, newest 8
```

Score candidates only on out-of-sample predictions. Use identical validation cutoffs among candidates where possible; a candidate must have at least one valid window to be selectable.

- [ ] **Step 4: Write RED range tests**

Cover:

- range width is based on absolute held-out aggregate residuals;
- 1–2 residuals multiply width by 1.50;
- 3–4 multiply by 1.25;
- >=5 no low-sample multiplier;
- orders/revenue lower bound never <0;
- negative contribution lower/estimate is allowed;
- `lower <= estimate <= upper` always;
- 30d fallback width scales from shorter residuals when direct 30d windows are unavailable.

- [ ] **Step 5: Write RED confidence tests**

Cover:

- history 7–27 -> low;
- history >=28 but <2 backtest windows -> low;
- normalized error >40 -> low;
- history >=56 + >=4 windows + >=25% signal + <=20 error -> high;
- otherwise qualifying -> medium;
- 30d without >=2 direct 30d windows -> low even when 7d is high.

- [ ] **Step 6: Implement range/confidence and response-safe normalization**

At the final public boundary:

```python
def _finite_or_none(value):
    return value if value is not None and math.isfinite(value) else None
```

If final estimate/range cannot be made finite, return metric unavailable rather than serializing invalid JSON.

- [ ] **Step 7: Run the complete pure engine suite**

```bash
cd backend
pytest -q tests/test_dropshipping_forecast_math.py
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/dropshipping_forecast_math.py backend/tests/test_dropshipping_forecast_math.py
git commit -m "feat: select forecast models with rolling backtests"
```

---

### Task 4: Build store-local historical daily series correctly

**Files:**
- Create: `backend/app/services/dropshipping_forecasting.py`
- Create: `backend/tests/test_dropshipping_forecasting.py`

**Interfaces:**

```python
class InvalidStoreTimezoneError(ValueError):
    code = "invalid_store_timezone"

@dataclass(frozen=True)
class DailyStoreObservation:
    date: date
    delivered_orders: float
    delivered_revenue: float
    contribution: float

def resolve_forecast_calendar(store: Store, now_utc: datetime) -> ForecastCalendar:
    ...

def build_store_history(
    db: Session,
    organization_id: int,
    store: Store,
    *,
    now_utc: datetime,
) -> StoreHistory:
    ...
```

- [ ] **Step 1: Write timezone RED tests**

Use explicit UTC instants and assert local day behavior for:

- `America/Bogota`;
- positive offset such as `Asia/Tokyo`;
- negative offset such as `America/Los_Angeles`;
- DST-aware zone such as `America/New_York` around a transition;
- invalid timezone -> `InvalidStoreTimezoneError`.

Example:

```python
calendar = resolve_forecast_calendar(
    store_with_timezone("America/Bogota"),
    datetime(2026, 9, 13, 3, 0, tzinfo=timezone.utc),
)
assert calendar.local_today == date(2026, 9, 12)
assert calendar.anchor_date == date(2026, 9, 11)
```

- [ ] **Step 2: Implement calendar conversion with `zoneinfo.ZoneInfo`**

Query boundaries must be derived from local midnight and converted to UTC:

```python
start_local = datetime.combine(start_date, time.min, tzinfo=tz)
end_local = datetime.combine(local_today, time.min, tzinfo=tz)
start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
end_utc = end_local.astimezone(timezone.utc).replace(tzinfo=None)
```

Match repository's naive UTC persistence convention when querying `Order.created_at`.

- [ ] **Step 3: Write daily-series RED tests**

Seed orders around UTC/local-midnight boundaries and assert:

- current partial local day excluded;
- previous complete local day included;
- orders bucket by local date, not UTC date;
- delivered count/revenue only use current lifecycle `delivered`;
- cancelled/returned orders establish observed store activity dates but do not increase delivered metrics;
- missing calendar days between first observed order and anchor are zeros;
- max history is last 365 completed days;
- no orders -> zero observations, not fabricated 365 zeros.

- [ ] **Step 4: Implement one bounded order query and zero materialization**

Load all store orders in the bounded UTC interval with `organization_id` and `store_id`, then bucket in memory. Do not issue one query per day.

History starts at the later of:

- first observed order's local date;
- `anchor_date - 364 days`.

It ends at `anchor_date` inclusive.

- [ ] **Step 5: Verify timezone/history tests**

```bash
cd backend
pytest -q tests/test_dropshipping_forecasting.py -k "timezone or anchor or history or zero or partial"
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dropshipping_forecasting.py backend/tests/test_dropshipping_forecasting.py
git commit -m "feat: build timezone-aware forecasting history"
```

---

### Task 5: Build complete/known-cost daily contribution with one Meta resolution

**Files:**
- Modify: `backend/app/services/dropshipping_forecasting.py`
- Modify: `backend/tests/test_dropshipping_forecasting.py`
- Reuse: `backend/app/services/dropshipping_unit_economics.py`
- Reuse: `backend/app/services/unit_economics_meta.py`

**Interfaces:**

`StoreHistory` must expose contribution semantics:

```python
@dataclass(frozen=True)
class ContributionSeriesQuality:
    status: str  # complete | incomplete
    metric: str  # contribution_profit_forecast | known_cost_contribution_forecast
    missing_components: tuple[str, ...]
    missing_reasons: dict[str, str | None]
```

- [ ] **Step 1: Write RED test proving no per-day Meta loop**

Patch forecasting's Meta resolver with a counter and create 60 days of orders:

```python
calls = []
def fake_meta(*args, **kwargs):
    calls.append((args, kwargs))
    return {"status": "actual", "amount": Decimal("600"), "reason": None, "metadata": {}}

history = build_store_history(...)
assert len(calls) == 1
```

Assert the one call covers exactly `[history_start_local_midnight, local_today_midnight)` translated to the existing exact-period resolver convention.

- [ ] **Step 2: Write RED reconciliation test**

For 6 complete history days and aggregate Meta spend 600:

```python
assert sum(history.meta_daily_allocations, Decimal("0")) == Decimal("600")
assert history.meta_daily_allocations[:-1] == [Decimal("100")] * 5
assert history.meta_daily_allocations[-1] == Decimal("100")
```

For non-even division, assign equal `total/days` to all but the final day and put the Decimal remainder on the final day so the sum is exact.

- [ ] **Step 3: Prefetch all OrderItems once**

For all order IDs in the bounded cohort, issue one scoped query:

```python
items = db.query(OrderItem).filter(
    OrderItem.organization_id == organization_id,
    OrderItem.store_id == store.id,
    OrderItem.order_id.in_(order_ids),
).all()
```

Get Unit Economics config once. For each materialized day call `calculate_order_resolvable_economics(..., config=config, prefetched_items=items)` over that day's orders. This reuses V2.2 formulas without one DB query per day.

- [ ] **Step 4: Calculate daily known/full contribution**

For each day:

```python
known_costs = sum(
    Decimal(str(component["amount"]))
    for component in components.values()
    if component["amount"] is not None
)
known_contribution = Decimal(str(recognized_revenue)) - known_costs
if meta_available:
    known_contribution -= meta_daily_allocation
```

Union all missing component names/reasons across the period. Add `ad_spend` when Meta is missing. A missing component's known partial amount remains included in `known_costs` exactly like V2.2.

Metric label rule:

```python
metric = (
    "contribution_profit_forecast"
    if not missing_components
    else "known_cost_contribution_forecast"
)
```

- [ ] **Step 5: Add complete/incomplete regression tests**

Cover:

- complete costs + actual Meta -> complete contribution series;
- missing Meta -> partial known-cost series with `ad_spend` missing;
- partial COGS -> known COGS amount deducted but status incomplete;
- missing shipping/payment/return cost propagates stable reason;
- zero-sales day still receives smoothed Meta cost when Meta available, so contribution may be negative;
- no applicable daily cost is not considered missing.

- [ ] **Step 6: Run contribution orchestration tests plus V2.2 regressions**

```bash
cd backend
pytest -q tests/test_dropshipping_forecasting.py tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_edge_cases.py tests/test_unit_economics_meta.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dropshipping_forecasting.py backend/tests/test_dropshipping_forecasting.py
git commit -m "feat: build contribution forecast history"
```

---

### Task 6: Assemble forecast response and expose the store-scoped API

**Files:**
- Modify: `backend/app/services/dropshipping_forecasting.py`
- Modify: `backend/app/api/dropshipping_analytics.py`
- Create: `backend/tests/test_dropshipping_forecasting_api.py`
- Modify: `backend/tests/contracts/api_routes.json`

**Interfaces:**

Service entry point:

```python
def get_store_forecast(
    db: Session,
    organization_id: int,
    store: Store,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
```

`now_utc` is injectable for deterministic tests; production defaults to aware UTC `datetime.now(timezone.utc)`.

Endpoint:

```python
@router.get("/api/stores/{store_id}/analytics/dropshipping/forecast")
def dropshipping_forecast(
    store_id: int,
    membership=Depends(require_permission("analytics.read")),
    db: Session = Depends(get_db),
):
```

No `date_from`/`date_to` parameters.

Top-level response contract:

```python
{
    "store_id": int,
    "currency": str,
    "timezone": str,
    "generated_at": str,
    "forecast_anchor_date": "YYYY-MM-DD",
    "history": {
        "date_from": str | None,
        "date_to": str | None,
        "days": int,
        "contribution_data_quality": {...},
    },
    "horizons": {
        "7d": horizon,
        "30d": horizon,
    },
}
```

Each horizon:

```python
{
    "date_from": "YYYY-MM-DD",
    "date_to_exclusive": "YYYY-MM-DD",
    "delivered_orders": metric_forecast,
    "delivered_revenue": metric_forecast,
    "contribution": {
        **metric_forecast,
        "metric": "contribution_profit_forecast" | "known_cost_contribution_forecast",
        "data_quality": {
            "status": "complete" | "incomplete",
            "missing_components": [...],
            "missing_reasons": {...},
        },
    },
}
```

Metric unavailable shape remains structurally present with null values and stable reason.

- [ ] **Step 1: Write service RED tests for exact horizon dates and metric assembly**

Freeze `now_utc`, call `get_store_forecast`, and assert:

```python
assert payload["horizons"]["7d"]["date_from"] == "2026-09-13"
assert payload["horizons"]["7d"]["date_to_exclusive"] == "2026-09-20"
assert payload["horizons"]["30d"]["date_to_exclusive"] == "2026-10-13"
```

Also assert <7 observations returns each metric as `unavailable/insufficient_history` without 500.

- [ ] **Step 2: Implement response assembly by calling `forecast_metric` separately**

Use the same daily dates but independent target value vectors. Pass `non_negative=True` for orders/revenue and `False` for contribution.

Round delivered-order aggregate estimate/bounds to sensible display-safe numeric values without converting to integer in the backend; preserving floats keeps range calibration honest. Frontend may display whole numbers.

- [ ] **Step 3: Write API RED tests**

Cover:

- manager with `analytics.read` receives 200;
- operator without permission receives 403;
- foreign-organization store receives 404;
- inactive store receives 404;
- store-restricted membership unassigned store receives 403 `Store access denied`;
- invalid timezone returns stable 422 detail `invalid_store_timezone`;
- query `?date_from=...&date_to=...` does not alter the forecast and is not part of function signature/contract;
- JSON contains no NaN/Infinity;
- complete vs incomplete contribution labels;
- model/quality fields serialize.

- [ ] **Step 4: Add the thin API route**

Router sequence must be:

```python
store = _validate_store(store_id, membership, db)
ensure_membership_store_access(membership, store)
try:
    return get_store_forecast(db, membership.organization_id, store)
except InvalidStoreTimezoneError as exc:
    raise HTTPException(status_code=422, detail=exc.code) from exc
```

Do not catch generic exceptions as fake forecast results.

- [ ] **Step 5: Update strict route snapshot intentionally**

Run:

```bash
cd backend
python -m pytest tests/test_route_contract.py --update-snapshot
python -m pytest -q tests/test_route_contract.py
```

Review the JSON diff and require exactly one route addition:

```text
GET /api/stores/{store_id}/analytics/dropshipping/forecast
```

- [ ] **Step 6: Run backend forecast/API regression set**

```bash
cd backend
pytest -q \
  tests/test_dropshipping_forecast_math.py \
  tests/test_dropshipping_forecasting.py \
  tests/test_dropshipping_forecasting_api.py \
  tests/test_dropshipping_unit_economics.py \
  tests/test_dropshipping_unit_economics_api.py \
  tests/test_route_contract.py
ruff check app/ tests/ tools/
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dropshipping_forecasting.py backend/app/api/dropshipping_analytics.py backend/tests/test_dropshipping_forecasting_api.py backend/tests/contracts/api_routes.json
git commit -m "feat: expose dropshipping store forecast API"
```

---

### Task 7: Add frontend forecast DTO/client and pure presentation helpers

**Files:**
- Modify: `frontend/src/services/analytics.ts`
- Create: `frontend/src/utils/dropshippingForecast.ts`
- Create: `frontend/tests/dropshippingForecast.test.ts`

**Interfaces:**

Add DTOs matching the backend exactly:

```ts
export type DropshippingForecastConfidence = "low" | "medium" | "high";
export type DropshippingForecastStatus = "available" | "unavailable";

export interface DropshippingForecastQuality {
  history_days: number;
  observations: number;
  non_zero_observations: number;
  backtest_windows: number;
  long_backtest_windows: number;
  error_metric: "smape" | "mae" | null;
  error_value: number | null;
  normalized_error_pct: number | null;
}

export interface DropshippingForecastMetric {
  status: DropshippingForecastStatus;
  reason: "insufficient_history" | "backtest_unavailable" | "non_finite_model_output" | null;
  estimate: number | null;
  lower_bound: number | null;
  upper_bound: number | null;
  confidence: DropshippingForecastConfidence;
  model: "recent_naive" | "weighted_moving_average" | "linear_trend" | "weekday_trend" | null;
  quality: DropshippingForecastQuality;
}
```

Add contribution and top-level types, then:

```ts
export async function getDropshippingForecast(storeId: number) {
  const response = await api.get<DropshippingForecastResponse>(
    `/api/stores/${storeId}/analytics/dropshipping/forecast`,
  );
  return response.data;
}
```

No `buildParams`, no date arguments.

- [ ] **Step 1: Write pure-helper RED tests**

`dropshippingForecast.ts` should not import `analytics.ts` at runtime. Use `import type` only if needed.

Test:

- language normalization to es/en/pt-BR;
- confidence labels;
- model labels;
- `insufficient_history` copy;
- complete contribution title vs partial title;
- currency range formatting;
- unavailable metric returns em dash/copy rather than `null` text.

Example:

```ts
test("partial contribution never uses complete contribution label", () => {
  assert.equal(
    contributionForecastLabel("known_cost_contribution_forecast", "es"),
    "Contribución proyectada con costos conocidos",
  );
});
```

- [ ] **Step 2: Confirm RED**

```bash
cd frontend
npm test -- --test-name-pattern="forecast"
```

If Node's script does not forward the filter cleanly, run `node --test tests/dropshippingForecast.test.ts`.

- [ ] **Step 3: Implement pure localized presentation helpers**

Follow the existing Unit Economics pattern with local `es`, `en`, and `pt-BR` copy maps instead of expanding the already-large global `i18n.ts` for this isolated section.

Export helpers such as:

```ts
forecastConfidenceLabel(confidence, language)
forecastModelLabel(model, language)
forecastUnavailableCopy(reason, language)
contributionForecastLabel(metric, language)
formatForecastCurrencyRange(metric, currency, language)
```

- [ ] **Step 4: Add HTTP DTO/client**

Keep the HTTP call in `analytics.ts`, but keep tests pointed at the pure utility so `./api` is never pulled into Node's direct TypeScript test graph.

- [ ] **Step 5: Run helper tests and TypeScript build**

```bash
cd frontend
node --test tests/dropshippingForecast.test.ts
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/analytics.ts frontend/src/utils/dropshippingForecast.ts frontend/tests/dropshippingForecast.test.ts
git commit -m "feat: add dropshipping forecast client contract"
```

---

### Task 8: Render Forecasting as the seventh isolated Analytics section

**Files:**
- Create: `frontend/src/components/DropshippingForecast.tsx`
- Create: `frontend/src/dropshipping-forecast.css`
- Modify: `frontend/src/components/DropshippingOverview.tsx`
- Modify: `frontend/src/utils/dropshippingAnalyticsState.ts`
- Modify: `frontend/tests/dropshippingAnalyticsState.test.ts`
- Modify: `frontend/tests/dropshippingForecast.test.ts`

**Interfaces:**

Component:

```tsx
interface Props {
  data: DropshippingForecastResponse | null;
  unavailable: boolean;
  language: string;
  currency: string;
}
```

- [ ] **Step 1: Update analytics-state tests first and confirm RED**

Expected section order:

```ts
[
  "overview",
  "profitability",
  "products",
  "orders",
  "insights",
  "unitEconomics",
  "forecast",
]
```

Add explicit tests that:

- only forecast rejected -> failed list is `["forecast"]` and global failure false;
- all seven rejected -> global failure true;
- existing partial-failure mapping indexes remain correct.

Run:

```bash
cd frontend
node --test tests/dropshippingAnalyticsState.test.ts
```

Expected: RED because forecast is not registered.

- [ ] **Step 2: Register the seventh section**

Modify only the section constant; existing index-driven helpers then inherit seven-section behavior.

- [ ] **Step 3: Add forecast to `DashboardData` and `Promise.allSettled`**

The seventh request must be exactly:

```ts
getDropshippingForecast(storeId)
```

not:

```ts
getDropshippingForecast(storeId, dateFrom, dateTo)
```

Map `results[6]` to `forecast`, add `forecast: "pronóstico"` to section labels, and pass `unavailableSections.includes("forecast")` to the component.

Keep the existing effect dependencies because changing `dateFrom/dateTo` legitimately reloads historical sections; the forecast request may be repeated, but its URL/result must remain independent of those filters. Do not create cache/persistence in V2.3.

- [ ] **Step 4: Implement `DropshippingForecast`**

Render one section near Unit Economics with responsive 7d and 30d horizon panels. Each panel contains three metric cards:

- delivered orders;
- delivered revenue;
- contribution.

Each available metric shows:

```text
Estimate
Probable range: lower – upper
Confidence badge
Model/backtest note
```

For orders, display rounded whole-number values. Revenue/contribution use localized currency formatting with zero fraction digits.

For contribution:

- `contribution_profit_forecast` -> `Contribución proyectada` / localized equivalent;
- `known_cost_contribution_forecast` -> `Contribución proyectada con costos conocidos` plus visible `Parcial` badge and a missing-components note.

For unavailable metrics, show reason-specific copy. A whole section rejection shows only the forecast section unavailable state and must not hide any other analytics.

- [ ] **Step 5: Add focused responsive CSS**

Use existing CSS variable conventions. Required layout behavior:

```css
.dropshipping-forecast-horizons {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 760px) {
  .dropshipping-forecast-horizons {
    grid-template-columns: 1fr;
  }
}
```

Do not add a chart library.

- [ ] **Step 6: Add pure presentation assertions for partial/unavailable states**

Extend `dropshippingForecast.test.ts` to cover all three locales, partial badge text, model note inputs, and range formatting. Do not introduce React Testing Library dependency.

- [ ] **Step 7: Run all frontend verification**

```bash
cd frontend
npm test
npm run lint
npm run build
```

Expected: PASS. Lint warnings that pre-existed may remain only if CI currently tolerates them; new code should introduce no lint errors.

- [ ] **Step 8: Commit**

```bash
git add \
  frontend/src/components/DropshippingForecast.tsx \
  frontend/src/dropshipping-forecast.css \
  frontend/src/components/DropshippingOverview.tsx \
  frontend/src/utils/dropshippingAnalyticsState.ts \
  frontend/tests/dropshippingAnalyticsState.test.ts \
  frontend/tests/dropshippingForecast.test.ts
git commit -m "feat: render store forecasting in analytics"
```

---

### Task 9: Harden performance, serialization, and regression behavior

**Files:**
- Modify as required only within V2.3 files/tests discovered by failures.
- Test: `backend/tests/test_dropshipping_forecast_math.py`
- Test: `backend/tests/test_dropshipping_forecasting.py`
- Test: `backend/tests/test_dropshipping_forecasting_api.py`
- Test: existing Unit Economics/Analytics suites.

- [ ] **Step 1: Add query/provider-count regression tests**

Assert a 365-day forecast path uses bounded operations:

- one order cohort query;
- one order-item query when order IDs exist;
- one Unit Economics config read;
- at most one Meta spend resolver call;
- never one DB/provider call per history day.

Do not assert SQLAlchemy internal incidental queries unrelated to the targeted service; instrument the specific loaders/resolvers or wrap their helper boundaries.

- [ ] **Step 2: Add finite-JSON fuzz-style parametrized tests**

Use pathological but finite histories:

- all zeros;
- alternating zero/large value;
- very large finite revenue;
- negative contribution;
- single huge outlier;
- flat sequence.

Recursively walk the response and assert every float is `math.isfinite()`.

- [ ] **Step 3: Verify existing analytics behavior is unchanged**

```bash
cd backend
pytest -q \
  tests/test_dropshipping_analytics.py \
  tests/test_dropshipping_decision_intelligence.py \
  tests/test_dropshipping_decision_intelligence_api.py \
  tests/test_dropshipping_unit_economics.py \
  tests/test_dropshipping_unit_economics_api.py \
  tests/test_dropshipping_unit_economics_edge_cases.py \
  tests/test_unit_economics_meta.py \
  tests/test_dropshipping_forecast_math.py \
  tests/test_dropshipping_forecasting.py \
  tests/test_dropshipping_forecasting_api.py \
  tests/test_route_contract.py
```

Expected: PASS.

- [ ] **Step 4: Run full backend validation exactly like CI**

```bash
cd backend
ruff check app/ tests/ tools/
python -m pytest -q --tb=short
```

Expected: PASS.

- [ ] **Step 5: Run full frontend validation exactly like CI**

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build
```

Expected: PASS.

- [ ] **Step 6: Commit any hardening-only changes**

```bash
git add backend frontend
git commit -m "test: harden dropshipping forecasting v2.3"
```

Skip this commit if Step 1–5 require no code/test changes beyond already committed tasks.

---

### Task 10: Final review, PR, and merge gate

**Files:** none unless review finds a defect.

- [ ] **Step 1: Compare branch against `main`**

```bash
git fetch origin
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Confirm:

- no migration/model persistence added;
- no unrelated refactor;
- no route beyond the one approved forecast endpoint;
- no dashboard date parameters on forecast client;
- no LLM/ML dependency added.

- [ ] **Step 2: Re-read the approved spec and check every acceptance criterion**

Use `docs/superpowers/specs/2026-09-13-dropshipping-forecasting-v2-3-design.md` as the checklist. Explicitly verify all 13 acceptance criteria, especially partial contribution naming, current-day exclusion, one Meta resolution, and failure isolation.

- [ ] **Step 3: Open PR only after local/branch verification is green**

Suggested PR title:

```text
feat: add dropshipping store forecasting v2.3
```

PR body must summarize:

- deterministic adaptive model selection;
- 7d/30d estimate + probable ranges;
- timezone semantics;
- complete vs known-cost contribution;
- one-call Meta historical smoothing;
- independent frontend section;
- test commands/results.

- [ ] **Step 4: Wait for the actual GitHub `Validate Pull Request` run on the final head**

The workflow must show success for:

- Detect changed scopes;
- Backend validation shard 0;
- Backend validation shard 1;
- Frontend validation;
- Backend + Frontend validation aggregator.

Do not merge based on an older head SHA, a cancelled run, or local-only evidence.

- [ ] **Step 5: Review PR diff and CI on the same final SHA**

If any failure occurs, use `superpowers:systematic-debugging`, patch in the feature branch, rerun targeted tests, then require a fresh all-green PR run.

- [ ] **Step 6: Squash merge only after final-head CI is green**

After merge, verify:

- PR `merged == true`;
- merge commit exists on `main`;
- `main` HEAD is the merge/squash commit returned by GitHub;
- no later feature work is added to the merged branch.

---

## Definition of Done

V2.3 is done only when all of the following are true:

- [ ] Store-local calendar anchor excludes the current partial day.
- [ ] 7d and 30d forecasts exist for delivered orders and revenue when >=7 observations allow forecasting.
- [ ] Every available metric includes estimate, lower/upper probable bounds, confidence, selected model, and quality diagnostics.
- [ ] Rolling out-of-sample backtesting deterministically selects among the fixed four candidate models.
- [ ] Short history and insufficient long-window validation cannot produce inflated confidence.
- [ ] Zero-heavy/all-zero series are safe and deterministic.
- [ ] Orders/revenue never emit negative estimate/bounds; contribution may be negative.
- [ ] No NaN/Infinity or inverted range can reach JSON.
- [ ] V2.2 order/cost semantics are reused rather than reimplemented.
- [ ] Meta historical spend is resolved no more than once and smoothed with exact aggregate reconciliation.
- [ ] Complete economics returns `contribution_profit_forecast`.
- [ ] Incomplete economics returns `known_cost_contribution_forecast` with explicit missing components/reasons.
- [ ] Forecast API is `analytics.read`, tenant/store scoped, active-store validated, and membership-store restricted.
- [ ] Strict route snapshot contains exactly the one intentional new route.
- [ ] Forecast client sends no dashboard date filters.
- [ ] Forecasting is the seventh isolated `Promise.allSettled` section.
- [ ] Forecast rejection never blanks established Analytics sections.
- [ ] Frontend supports es/en/pt-BR presentation consistent with Unit Economics.
- [ ] Backend Ruff + full pytest pass.
- [ ] Frontend lint + tests + build pass.
- [ ] Final GitHub Actions run for the exact PR head SHA is fully green before merge.
