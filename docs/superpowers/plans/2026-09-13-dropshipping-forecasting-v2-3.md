# Dropshipping Analytics V2.3 — Store Forecasting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, auditable 7-day and 30-day store forecasts for delivered orders, delivered revenue, and complete/known-cost contribution, with probable ranges, confidence, and rolling-backtest diagnostics.

**Architecture:** Forecast on demand per store. Reuse V2.2 Unit Economics cost rules through one public order-resolvable calculator, construct timezone-correct daily history with bounded DB/provider access, run four pure deterministic candidate models selected by rolling backtesting, expose one thin analytics endpoint, and render Forecasting as the seventh independently failing dashboard section.

**Tech Stack:** FastAPI, SQLAlchemy 2, Python 3.10 standard library (`math`, `statistics`, `datetime`, `zoneinfo`, `decimal`), pytest, React 19, TypeScript 6, Axios, node:test, Vite.

**Spec:** `docs/superpowers/specs/2026-09-13-dropshipping-forecasting-v2-3-design.md`

## Global Constraints

- No LLM, external AI model, NumPy/Pandas, ML framework, persistence table, migration, scheduled training job, or forecast cache.
- Targets are store-level delivered orders, delivered revenue, and contribution/known-cost contribution only.
- Horizons are exactly 7 and 30 store-local calendar days.
- Exclude the store-local current partial day.
- Invalid `Store.timezone` is an explicit section-level error; never fall back to server timezone.
- Use at most 365 completed local days and materialize missing dates as zero observations.
- Fewer than 7 observations => affected metric unavailable; fewer than 28 => confidence forced `low`.
- Candidate priority/tie order is `recent_naive`, `weighted_moving_average`, `linear_trend`, `weekday_trend`.
- Probable ranges come from out-of-sample residuals. Never emit NaN/Infinity or inverted ranges.
- Orders/revenue estimate and bounds are non-negative. Contribution may be negative.
- Forecasting must not duplicate COGS, shipping, payment, COD, return, or Meta business rules from V2.2.
- Resolve Meta at most once for the contribution lookback. Uniform daily smoothing is forecasting-only and must reconcile exactly to the period aggregate.
- Incomplete economics returns `known_cost_contribution_forecast` with missing components/reasons; never label it complete contribution profit.
- Endpoint accepts no dashboard `date_from`/`date_to` arguments.
- Business logic remains in `backend/app/services/`.
- Scope every read by `organization_id + store_id`; API also enforces membership store access.
- Frontend pure tests must not import HTTP service modules.
- Forecast failure must not hide existing Analytics sections.

## Fixed Algorithm Constants

```python
MAX_HISTORY_DAYS = 365
MIN_HISTORY_DAYS = 7
LOW_CONFIDENCE_HISTORY_DAYS = 28
MIN_SIMPLE_MODEL_TRAIN_DAYS = 3
RECENT_NAIVE_WINDOW = 7
WMA_WINDOW = 14
LINEAR_TREND_WINDOW = 56
WEEKDAY_TREND_WINDOW = 84
WEEKDAY_MIN_HISTORY = 28
WEEKDAY_MIN_SUPPORT_PER_DAY = 2
WEEKDAY_SHRINKAGE = 3.0
SHORT_BACKTEST_VALIDATION_DAYS = 1
STANDARD_BACKTEST_VALIDATION_DAYS = 7
STANDARD_BACKTEST_MIN_TRAIN_DAYS = 7
LONG_BACKTEST_VALIDATION_DAYS = 30
LONG_BACKTEST_MIN_TRAIN_DAYS = 28
MAX_BACKTEST_WINDOWS = 8
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
MODEL_SCORE_TIE_EPSILON = 1e-9
```

### Exact model definitions

```python
recent_naive = mean(last min(7, n) values)
weighted_moving_average = sum(value * weight) / sum(weights)
# weight sequence is 1..window_length, oldest to newest, window <=14
linear_trend = OLS over last min(56, n) observations
weekday_trend = OLS over last min(84, n) observations + shrunk weekday residual effect
weekday_effect = raw_weekday_residual_mean * support / (support + 3.0)
```

`recent_naive`, WMA, and linear trend are eligible with at least 3 training observations. `weekday_trend` requires at least 28 training observations and every weekday represented at least twice.

### Exact backtesting rules

- History 7–13 days: use expanding one-day validation. Training cutoffs start at 3 observations and continue one day at a time. A candidate is scored only on cutoffs where it is eligible.
- History >=14 days: use rolling 7-day validation windows, minimum 7-day training prefix, keeping the newest 8 windows.
- Direct 30-day validation uses a minimum 28-day training prefix. Two 30-day validation windows therefore first become possible at 88 observations.
- If direct 30-day residuals are unavailable, 30-day range width is derived from shorter out-of-sample aggregate residual width multiplied linearly by `30/7`; if only one-day residuals exist, multiply by `30`.
- Missing two direct 30-day windows forces 30-day confidence `low`.
- sMAPE is selected only when at least 25% of held-out points have `abs(actual) + abs(predicted) > 0`; otherwise use MAE.
- MAE confidence normalization is `MAE / mean(abs(actual)) * 100` when the scale is positive. If actual and prediction are both all-zero, normalized error is 0.
- Candidate scores within `1e-9` use the fixed simplicity order.

### Exact probable-range quantile

Use **nearest-rank q80 only**, not interpolation:

```python
def nearest_rank_quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]
```

Range width:

```python
width = nearest_rank_quantile(absolute_aggregate_residuals, 0.80)
if residual_count < 3:
    width *= 1.50
elif residual_count < 5:
    width *= 1.25
lower = estimate - width
upper = estimate + width
```

Clamp estimate/lower/upper to zero only for orders/revenue. Then enforce finite values and `lower <= estimate <= upper`.

### Exact confidence rules

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

For horizon 30d, fewer than two direct 30-day validation windows overrides this result to `low`.

---

## File Structure

### Backend create
- `backend/app/services/dropshipping_forecast_math.py`
- `backend/app/services/dropshipping_forecasting.py`
- `backend/tests/test_dropshipping_forecast_math.py`
- `backend/tests/test_dropshipping_forecasting.py`
- `backend/tests/test_dropshipping_forecasting_api.py`

### Backend modify
- `backend/app/services/dropshipping_unit_economics.py`
- `backend/tests/test_dropshipping_unit_economics.py`
- `backend/app/api/dropshipping_analytics.py`
- `backend/tests/contracts/api_routes.json`

### Frontend create
- `frontend/src/components/DropshippingForecast.tsx`
- `frontend/src/utils/dropshippingForecast.ts`
- `frontend/src/dropshipping-forecast.css`
- `frontend/tests/dropshippingForecast.test.ts`

### Frontend modify
- `frontend/src/services/analytics.ts`
- `frontend/src/utils/dropshippingAnalyticsState.ts`
- `frontend/tests/dropshippingAnalyticsState.test.ts`
- `frontend/src/components/DropshippingOverview.tsx`

---

## Task 1: Extract reusable V2.2 order economics without semantic drift

**Files:** modify `backend/app/services/dropshipping_unit_economics.py`, `backend/tests/test_dropshipping_unit_economics.py`.

**Interfaces:**

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
    """Resolve revenue and non-ad Unit Economics for an explicit cohort."""
```

Return:

```python
{
    "recognized_revenue": 0.0,
    "components": {
        "cogs": {},
        "outbound_shipping": {},
        "payment_fees": {},
        "cod_fees": {},
        "reverse_logistics": {},
    },
    "known_cost_subtotal": 0.0,
    "data_quality": {
        "status": "complete",
        "missing_components": [],
        "missing_reasons": {},
        "estimated_components": [],
        "actual_components": [],
    },
    "order_counts": {
        "total": 0,
        "delivered": 0,
        "returned": 0,
        "cancelled": 0,
        "fulfilled_outcomes": 0,
    },
}
```

Also expose `summarize_unit_economics_quality(components) -> dict[str, Any]`.

- [ ] Add characterization assertions for complete mixed cohort, partial COGS, missing payment rule, no orders, and returned-only negative contribution.
- [ ] Run baseline:

```bash
cd backend
pytest -q tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_edge_cases.py tests/test_dropshipping_unit_economics_api.py
```

- [ ] Add RED test proving prefetched items avoid a new `OrderItem` query.
- [ ] Implement the full optional-prefetch signature:

```python
def _resolve_cogs(
    db: Session,
    organization_id: int,
    store_id: int,
    delivered_orders: list[Order],
    *,
    prefetched_items: list[OrderItem] | None = None,
) -> dict[str, Any]:
    if not delivered_orders:
        return _not_applicable({"cost_completeness_pct": 100.0, "item_count": 0})
    delivered_ids = {order.id for order in delivered_orders}
    if prefetched_items is None:
        items = (
            db.query(OrderItem)
            .filter(
                OrderItem.organization_id == organization_id,
                OrderItem.store_id == store_id,
                OrderItem.order_id.in_(delivered_ids),
            )
            .all()
        )
    else:
        items = [
            item
            for item in prefetched_items
            if item.order_id in delivered_ids
            and item.organization_id == organization_id
            and item.store_id == store_id
        ]
    return _resolve_cogs_from_items(delivered_orders, items)
```

`_resolve_cogs_from_items` contains the current known-cost/completeness arithmetic unchanged.

- [ ] Make `get_store_unit_economics()` call `calculate_order_resolvable_economics()`, append its one Meta component, recompute six-component quality, and preserve all current response fields/values.
- [ ] Run V2.2 regressions plus `tests/test_unit_economics_meta.py`.
- [ ] Commit:

```bash
git add backend/app/services/dropshipping_unit_economics.py backend/tests/test_dropshipping_unit_economics.py
git commit -m "refactor: expose reusable unit economics components"
```

---

## Task 2: Implement pure deterministic candidate models

**Files:** create `backend/app/services/dropshipping_forecast_math.py`, `backend/tests/test_dropshipping_forecast_math.py`.

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

Public API:

```python
def eligible_models(history: Sequence[ForecastPoint]) -> tuple[str, ...]:
    models = ["recent_naive", "weighted_moving_average", "linear_trend"]
    if _weekday_model_is_eligible(history):
        models.append("weekday_trend")
    return tuple(models)


def forecast_candidate(
    model: str,
    history: Sequence[ForecastPoint],
    future_dates: Sequence[date],
    *,
    non_negative: bool,
) -> CandidateForecast | None:
    ...
```

The body above is fully determined by the fixed model definitions; do not add hyperparameter search.

- [ ] RED tests: constant series, recent shift, exact linear trend, weekday seasonality, weekday ineligibility, non-negative floor, negative contribution, and non-finite rejection.
- [ ] Run RED: `cd backend && pytest -q tests/test_dropshipping_forecast_math.py`.
- [ ] Implement OLS exactly:

```python
x_mean = sum(xs) / len(xs)
y_mean = sum(ys) / len(ys)
denominator = sum((x - x_mean) ** 2 for x in xs)
slope = 0.0 if denominator == 0 else (
    sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
)
intercept = y_mean - slope * x_mean
```

- [ ] Implement weekday residual shrinkage with support threshold 2 and shrinkage 3.0.
- [ ] Reject any candidate with non-finite input-derived output before target clamping.
- [ ] Run GREEN: `cd backend && pytest -q tests/test_dropshipping_forecast_math.py`.
- [ ] Commit:

```bash
git add backend/app/services/dropshipping_forecast_math.py backend/tests/test_dropshipping_forecast_math.py
git commit -m "feat: add deterministic forecast candidate models"
```

---

## Task 3: Add rolling backtests, model selection, ranges, and confidence

**Files:** modify `backend/app/services/dropshipping_forecast_math.py`, `backend/tests/test_dropshipping_forecast_math.py`.

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

Public API:

```python
def forecast_metric(
    history: Sequence[ForecastPoint],
    *,
    horizon_days: int,
    non_negative: bool,
) -> MetricForecast:
    ...
```

- [ ] RED tests for deterministic winner selection: constant => recent naive tie winner; exact linear => linear trend; weekly synthetic => weekday trend; one bad candidate does not crash selection; all invalid => unavailable `non_finite_model_output`.
- [ ] RED tests for MAE/sMAPE: zero denominators safe, all-zero returns normalized 0, <25% signal uses MAE.
- [ ] Implement 7–13 day one-step expanding validation and >=14 day rolling 7d validation exactly as fixed above.
- [ ] Implement direct 30d validation with 28-day minimum prefix and newest 8 windows.
- [ ] Implement nearest-rank q80 exactly:

```python
def nearest_rank_quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile_requires_values")
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]
```

- [ ] RED/GREEN tests for sample multipliers, 30d fallback scaling, non-negative order/revenue ranges, negative contribution, and range ordering.
- [ ] RED/GREEN tests for low/medium/high confidence and 30d low override.
- [ ] Final numeric guard:

```python
def _is_finite_number(value: float | None) -> bool:
    return value is not None and math.isfinite(value)
```

If estimate/range cannot be finite after candidate filtering, return unavailable rather than invalid JSON.

- [ ] Run: `cd backend && pytest -q tests/test_dropshipping_forecast_math.py`.
- [ ] Commit:

```bash
git add backend/app/services/dropshipping_forecast_math.py backend/tests/test_dropshipping_forecast_math.py
git commit -m "feat: select forecast models with rolling backtests"
```

---

## Task 4: Build timezone-correct daily store history

**Files:** create `backend/app/services/dropshipping_forecasting.py`, `backend/tests/test_dropshipping_forecasting.py`.

```python
class InvalidStoreTimezoneError(ValueError):
    code = "invalid_store_timezone"

@dataclass(frozen=True)
class ForecastCalendar:
    timezone: str
    local_today: date
    anchor_date: date
    history_end_utc_exclusive: datetime

@dataclass(frozen=True)
class DailyStoreObservation:
    date: date
    delivered_orders: float
    delivered_revenue: float
    contribution: float
```

- [ ] RED timezone tests for America/Bogota, Asia/Tokyo, America/Los_Angeles, DST-aware America/New_York, and invalid timezone.
- [ ] Implement local midnight conversion:

```python
zone = ZoneInfo(store.timezone)
now_local = now_utc.astimezone(zone)
local_today = now_local.date()
anchor_date = local_today - timedelta(days=1)
end_local = datetime.combine(local_today, time.min, tzinfo=zone)
end_utc_exclusive = end_local.astimezone(timezone.utc).replace(tzinfo=None)
```

- [ ] RED history tests around UTC/local midnight, partial-day exclusion, current lifecycle semantics, zero-day materialization, 365-day cap, and empty store.
- [ ] Query all bounded orders once with organization/store scope. Use earliest observed order local date, capped at `anchor_date - 364 days`, as history start. If no completed historical orders exist, history has zero observations.
- [ ] Bucket each persisted naive UTC `created_at` by attaching `timezone.utc`, converting to store zone, then taking `.date()`.
- [ ] Run: `cd backend && pytest -q tests/test_dropshipping_forecasting.py -k "timezone or history or anchor or partial or zero"`.
- [ ] Commit:

```bash
git add backend/app/services/dropshipping_forecasting.py backend/tests/test_dropshipping_forecasting.py
git commit -m "feat: build timezone-aware forecasting history"
```

---

## Task 5: Build complete/known-cost daily contribution with one Meta call

**Files:** modify `backend/app/services/dropshipping_forecasting.py`, `backend/tests/test_dropshipping_forecasting.py`.

```python
@dataclass(frozen=True)
class ContributionSeriesQuality:
    status: str
    metric: str
    missing_components: tuple[str, ...]
    missing_reasons: dict[str, str | None]
```

- [ ] RED test with 60 history days proving `resolve_meta_ad_spend` is called exactly once.
- [ ] RED test that Meta allocation sums exactly to aggregate. Allocation algorithm:

```python
def allocate_meta(total: Decimal, days: int) -> list[Decimal]:
    if days <= 0:
        return []
    base = total / Decimal(days)
    values = [base for _ in range(days - 1)]
    values.append(total - sum(values, Decimal("0")))
    return values
```

- [ ] Prefetch all bounded `OrderItem` rows once:

```python
items = (
    db.query(OrderItem)
    .filter(
        OrderItem.organization_id == organization_id,
        OrderItem.store_id == store.id,
        OrderItem.order_id.in_(order_ids),
    )
    .all()
)
```

Skip this query when `order_ids` is empty.

- [ ] Read Unit Economics config once, group orders by local day, and call `calculate_order_resolvable_economics(..., config=config, prefetched_items=items)` for each materialized day. This is in-memory daily reuse, not daily DB access.
- [ ] Compute daily known contribution:

```python
known_costs = sum(
    Decimal(str(component["amount"]))
    for component in components.values()
    if component["amount"] is not None
)
known_contribution = Decimal(str(recognized_revenue)) - known_costs
if meta_status == "actual":
    known_contribution -= meta_allocation_for_day
```

- [ ] Union missing component names/reasons across all history days; add `ad_spend` when Meta is missing.
- [ ] Metric selection:

```python
metric = (
    "contribution_profit_forecast"
    if not missing_components
    else "known_cost_contribution_forecast"
)
```

- [ ] Tests: complete costs+Meta, missing Meta, partial COGS known amount, missing shipping/payment/return reasons, zero-sales day with Meta can be negative, non-applicable does not mark incomplete.
- [ ] Run forecast + V2.2 regression suites.
- [ ] Commit:

```bash
git add backend/app/services/dropshipping_forecasting.py backend/tests/test_dropshipping_forecasting.py
git commit -m "feat: build contribution forecast history"
```

---

## Task 6: Assemble forecast response and add the API route

**Files:** modify `backend/app/services/dropshipping_forecasting.py`, `backend/app/api/dropshipping_analytics.py`; create `backend/tests/test_dropshipping_forecasting_api.py`; modify `backend/tests/contracts/api_routes.json`.

Service API:

```python
def get_store_forecast(
    db: Session,
    organization_id: int,
    store: Store,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    ...
```

Top-level contract:

```python
{
    "store_id": 1,
    "currency": "COP",
    "timezone": "America/Bogota",
    "generated_at": "2026-09-13T20:00:00+00:00",
    "forecast_anchor_date": "2026-09-12",
    "history": {
        "date_from": "2026-08-01",
        "date_to": "2026-09-12",
        "days": 43,
        "contribution_data_quality": {
            "status": "complete",
            "metric": "contribution_profit_forecast",
            "missing_components": [],
            "missing_reasons": {},
        },
    },
    "horizons": {
        "7d": {},
        "30d": {},
    },
}
```

Each horizon has `date_from`, `date_to_exclusive`, `delivered_orders`, `delivered_revenue`, and `contribution`. Each available metric contains status, estimate, lower/upper, confidence, model, and quality. Unavailable metrics keep those keys with null values and a stable reason.

- [ ] RED service tests for exact 7d/30d dates and <7 observation unavailable structure.
- [ ] Implement horizon assembly by calling `forecast_metric` independently for orders, revenue, and contribution; `non_negative=True` only for orders/revenue.
- [ ] RED API tests: permission 403, foreign org 404, inactive 404, restricted membership 403, invalid timezone 422 `invalid_store_timezone`, finite JSON, complete/partial contribution, and no date dependency.
- [ ] Add thin route:

```python
@router.get("/api/stores/{store_id}/analytics/dropshipping/forecast")
def dropshipping_forecast(
    store_id: int,
    membership=Depends(require_permission("analytics.read")),
    db: Session = Depends(get_db),
):
    store = _validate_store(store_id, membership, db)
    ensure_membership_store_access(membership, store)
    try:
        return get_store_forecast(db, membership.organization_id, store)
    except InvalidStoreTimezoneError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
```

- [ ] Update strict snapshot:

```bash
cd backend
python -m pytest tests/test_route_contract.py --update-snapshot
python -m pytest -q tests/test_route_contract.py
```

Review that the only route delta is `GET /api/stores/{store_id}/analytics/dropshipping/forecast`.

- [ ] Run:

```bash
cd backend
pytest -q tests/test_dropshipping_forecast_math.py tests/test_dropshipping_forecasting.py tests/test_dropshipping_forecasting_api.py tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_api.py tests/test_route_contract.py
ruff check app/ tests/ tools/
```

- [ ] Commit:

```bash
git add backend/app/services/dropshipping_forecasting.py backend/app/api/dropshipping_analytics.py backend/tests/test_dropshipping_forecasting_api.py backend/tests/contracts/api_routes.json
git commit -m "feat: expose dropshipping store forecast API"
```

---

## Task 7: Add frontend DTO/client and pure forecast presentation helpers

**Files:** modify `frontend/src/services/analytics.ts`; create `frontend/src/utils/dropshippingForecast.ts`, `frontend/tests/dropshippingForecast.test.ts`.

Types:

```ts
export type DropshippingForecastConfidence = "low" | "medium" | "high";
export type DropshippingForecastStatus = "available" | "unavailable";
export type DropshippingForecastModel =
  | "recent_naive"
  | "weighted_moving_average"
  | "linear_trend"
  | "weekday_trend";

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
  model: DropshippingForecastModel | null;
  quality: DropshippingForecastQuality;
}
```

Client:

```ts
export async function getDropshippingForecast(storeId: number) {
  const response = await api.get<DropshippingForecastResponse>(
    `/api/stores/${storeId}/analytics/dropshipping/forecast`,
  );
  return response.data;
}
```

- [ ] RED pure tests for es/en/pt-BR confidence labels, model labels, insufficient-history copy, complete vs partial contribution title, currency range formatting, and unavailable display.
- [ ] Confirm RED with `cd frontend && node --test tests/dropshippingForecast.test.ts`.
- [ ] Implement `dropshippingForecast.ts` with local copy maps matching the existing Unit Economics localization pattern. No Axios or React import; use `import type` only when a type is needed.
- [ ] Add all response DTOs and HTTP client to `analytics.ts`; do not call `buildParams` and do not accept date arguments.
- [ ] Run `node --test tests/dropshippingForecast.test.ts` and `npm run build`.
- [ ] Commit:

```bash
git add frontend/src/services/analytics.ts frontend/src/utils/dropshippingForecast.ts frontend/tests/dropshippingForecast.test.ts
git commit -m "feat: add dropshipping forecast client contract"
```

---

## Task 8: Render Forecasting as the seventh isolated Analytics section

**Files:** create `frontend/src/components/DropshippingForecast.tsx`, `frontend/src/dropshipping-forecast.css`; modify `frontend/src/components/DropshippingOverview.tsx`, `frontend/src/utils/dropshippingAnalyticsState.ts`, `frontend/tests/dropshippingAnalyticsState.test.ts`, `frontend/tests/dropshippingForecast.test.ts`.

Section registry must become:

```ts
export const DROPSHIPPING_ANALYTICS_SECTIONS = [
  "overview",
  "profitability",
  "products",
  "orders",
  "insights",
  "unitEconomics",
  "forecast",
] as const;
```

- [ ] RED state tests: only forecast rejected => `["forecast"]`; all seven rejected => global failure; existing indices remain correct.
- [ ] Add `forecast` to `DashboardData` and seventh request `getDropshippingForecast(storeId)` only. Map `results[6]` and label section `pronóstico`.
- [ ] Create component props:

```tsx
interface Props {
  data: DropshippingForecastResponse | null;
  unavailable: boolean;
  language: string;
  currency: string;
}
```

- [ ] Render responsive 7d and 30d panels; each has delivered orders, delivered revenue, contribution, estimate, probable range, confidence badge, model/backtest note, and per-metric unavailable state.
- [ ] Complete label: `Contribución proyectada`. Partial label: `Contribución proyectada con costos conocidos` plus visible `Parcial` and missing-cost notice. Localize es/en/pt-BR through pure helpers.
- [ ] Add responsive CSS:

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

- [ ] Extend pure tests for partial badge text and range formatting. Do not add React Testing Library.
- [ ] Run:

```bash
cd frontend
npm test
npm run lint
npm run build
```

- [ ] Commit:

```bash
git add frontend/src/components/DropshippingForecast.tsx frontend/src/dropshipping-forecast.css frontend/src/components/DropshippingOverview.tsx frontend/src/utils/dropshippingAnalyticsState.ts frontend/tests/dropshippingAnalyticsState.test.ts frontend/tests/dropshippingForecast.test.ts
git commit -m "feat: render store forecasting in analytics"
```

---

## Task 9: Hardening and full regression

**Files:** modify only V2.3 files/tests if failures expose defects.

- [ ] Add performance-boundary tests proving: one bounded order load, zero/one item preload, one config read, at most one Meta resolver call, and no provider/DB loop per history day.
- [ ] Add parametrized finite-response tests for all-zero, alternating zero/large, large finite revenue, negative contribution, outlier, and flat histories. Recursively assert every float is `math.isfinite()`.
- [ ] Run existing dropshipping regression set:

```bash
cd backend
pytest -q tests/test_dropshipping_analytics.py tests/test_dropshipping_decision_intelligence.py tests/test_dropshipping_decision_intelligence_api.py tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_api.py tests/test_dropshipping_unit_economics_edge_cases.py tests/test_unit_economics_meta.py tests/test_dropshipping_forecast_math.py tests/test_dropshipping_forecasting.py tests/test_dropshipping_forecasting_api.py tests/test_route_contract.py
```

- [ ] Run full backend CI-equivalent validation:

```bash
cd backend
ruff check app/ tests/ tools/
python -m pytest -q --tb=short
```

- [ ] Run full frontend CI-equivalent validation:

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build
```

- [ ] If hardening required code/test edits, commit them:

```bash
git add backend frontend
git commit -m "test: harden dropshipping forecasting v2.3"
```

If no files changed, do not create an empty commit.

---

## Task 10: PR and merge gate

- [ ] Compare against current `main` and confirm no migration, forecast persistence, unrelated refactor, extra route, LLM dependency, or date-filtered forecast client.
- [ ] Re-read all acceptance criteria in `docs/superpowers/specs/2026-09-13-dropshipping-forecasting-v2-3-design.md` and verify each explicitly.
- [ ] Open PR title: `feat: add dropshipping store forecasting v2.3`.
- [ ] PR body summarizes adaptive deterministic models, 7d/30d ranges, timezone semantics, complete/partial contribution, one-call Meta smoothing, independent frontend section, and test evidence.
- [ ] Require a fresh GitHub `Validate Pull Request` run on the exact final head SHA with success for Detect changed scopes, backend shard 0, backend shard 1, frontend validation, and final aggregator.
- [ ] If CI fails, use `superpowers:systematic-debugging`, patch the feature branch, rerun focused tests, and require another fresh all-green run.
- [ ] Squash merge only after final-head CI is green; then verify PR `merged == true`, merge commit exists, and `main` points at the returned merge/squash commit.

---

## Definition of Done

- [ ] Store-local current partial day is excluded.
- [ ] >=7 observations can produce deterministic 7d/30d order/revenue forecasts.
- [ ] Available metrics expose estimate, probable range, confidence, selected model, and diagnostics.
- [ ] Model selection is rolling-backtest-driven and deterministic.
- [ ] Short history and insufficient long validation cannot inflate confidence.
- [ ] Zero-heavy/all-zero histories are safe.
- [ ] Orders/revenue cannot be negative; contribution can.
- [ ] No NaN/Infinity or inverted range reaches JSON.
- [ ] V2.2 cost formulas have one authoritative implementation.
- [ ] Meta historical spend is resolved at most once and daily smoothing reconciles exactly.
- [ ] Complete economics => `contribution_profit_forecast`.
- [ ] Incomplete economics => `known_cost_contribution_forecast` plus missing metadata.
- [ ] API enforces `analytics.read`, tenant/store scope, active store, and membership store access.
- [ ] Route snapshot has exactly one approved route addition.
- [ ] Forecast client has no dashboard date filters.
- [ ] Forecast is the seventh isolated `Promise.allSettled` section.
- [ ] Forecast rejection cannot blank established Analytics.
- [ ] es/en/pt-BR forecast presentation works.
- [ ] Backend Ruff + full pytest pass.
- [ ] Frontend lint + tests + build pass.
- [ ] Exact final PR head is green in GitHub Actions before merge.
