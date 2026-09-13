# Dropshipping Analytics V2.3 — Store Forecasting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, auditable 7-day and 30-day store forecasts for delivered orders, delivered revenue, and complete/known-cost contribution, with probable ranges, confidence, and rolling-backtest diagnostics.

**Architecture:** Forecast on demand per store. Reuse V2.2 Unit Economics through one public order-resolvable calculator, construct store-timezone daily history with bounded DB/provider access, run four standard-library candidate models selected by rolling backtesting, expose one thin analytics endpoint, and render Forecasting as the seventh independently failing dashboard section.

**Tech Stack:** FastAPI, SQLAlchemy 2, Python 3.10 standard library (`math`, `datetime`, `zoneinfo`, `decimal`, `dataclasses`), pytest, React 19, TypeScript 6, Axios, node:test, Vite.

**Spec:** `docs/superpowers/specs/2026-09-13-dropshipping-forecasting-v2-3-design.md`

## Global Constraints

- No LLM, external AI model, NumPy/Pandas, ML framework, forecast persistence, migration, scheduled training, or cache.
- Forecast only store-level delivered orders, delivered revenue, and complete/known-cost contribution.
- Horizons are exactly 7 and 30 store-local calendar days.
- Exclude the store-local current partial day.
- Invalid `Store.timezone` returns a stable unavailable/error state; never use server timezone as fallback.
- Use at most 365 completed local days. Materialize missing calendar dates as zero observations.
- Fewer than 7 observations => metric unavailable. Fewer than 28 => confidence forced `low`.
- Candidate simplicity order is `recent_naive`, `weighted_moving_average`, `linear_trend`, `weekday_trend`.
- Probable ranges come from out-of-sample residuals.
- Never emit NaN/Infinity or `lower_bound > estimate > upper_bound` inconsistencies.
- Clamp delivered-order and revenue estimates/bounds to zero. Do not clamp contribution.
- Do not duplicate V2.2 COGS, shipping, payment, COD, return, or Meta business rules.
- Resolve Meta at most once for the historical contribution lookback. Forecasting-only daily smoothing must sum exactly to that aggregate.
- Incomplete economics returns `known_cost_contribution_forecast` plus explicit missing components/reasons.
- Forecast endpoint has no `date_from` or `date_to` parameters.
- All DB/provider access is scoped by `organization_id + store_id`; API also enforces membership store access.
- Business logic stays in `backend/app/services/`.
- Frontend node:test files import pure utilities, never runtime HTTP modules.
- Forecast failure cannot hide established Analytics sections.

## Fixed Forecast Constants

```python
MAX_HISTORY_DAYS = 365
MIN_HISTORY_DAYS = 7
MIN_SIMPLE_MODEL_TRAIN_DAYS = 3
LOW_CONFIDENCE_HISTORY_DAYS = 28
RECENT_NAIVE_WINDOW = 7
WMA_WINDOW = 14
LINEAR_TREND_WINDOW = 56
WEEKDAY_TREND_WINDOW = 84
WEEKDAY_MIN_HISTORY = 28
WEEKDAY_MIN_SUPPORT_PER_DAY = 2
WEEKDAY_SHRINKAGE = 3.0
STANDARD_BACKTEST_MIN_TRAIN_DAYS = 7
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
MODEL_SCORE_TIE_EPSILON = 1e-9
```

Backtesting is fixed as follows:

- 7–13 observations: expanding one-day validation cutoffs, starting after 3 training observations.
- >=14 observations: newest eight rolling 7-day validation windows, minimum 7 training observations.
- Direct 30-day validation: newest eight rolling 30-day windows, minimum 28 training observations. Two direct 30-day windows first exist at 88 observations.
- Without two direct 30-day windows, select the model from shorter out-of-sample validation, scale range width by `30/7` from 7-day residuals or by `30` from one-day residuals, and force 30-day confidence `low`.
- Use sMAPE only when at least 25% of held-out point pairs have `abs(actual)+abs(predicted)>0`; otherwise use MAE.
- For confidence, MAE normalizes as `MAE / mean(abs(actual)) * 100` when scale is positive. All-zero actual/predicted has normalized error 0; zero actual with non-zero MAE has normalized error 100.
- Candidate score ties within `1e-9` use the simplicity order.

Probable range uses nearest-rank q80 exactly:

```python
def nearest_rank_quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]
```

Width is q80 of absolute aggregate held-out residuals, multiplied by 1.50 for fewer than 3 residuals or 1.25 for fewer than 5 residuals.

Confidence is exactly:

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

For 30d, fewer than two direct 30-day windows overrides the result to `low`.

---

## File Structure

### Backend create
- `backend/app/services/dropshipping_forecast_math.py` — pure models, backtests, error scoring, ranges, confidence.
- `backend/app/services/dropshipping_forecasting.py` — timezone/calendar, bounded history loading, Unit Economics/Meta daily series, response assembly.
- `backend/tests/test_dropshipping_forecast_math.py` — pure algorithm tests.
- `backend/tests/test_dropshipping_forecasting.py` — calendar/history/contribution orchestration tests.
- `backend/tests/test_dropshipping_forecasting_api.py` — API permissions/tenancy/contract tests.

### Backend modify
- `backend/app/services/dropshipping_unit_economics.py` — public reusable non-ad cohort calculator + prefetched COGS path.
- `backend/tests/test_dropshipping_unit_economics.py` — characterization and prefetched-item tests.
- `backend/app/api/dropshipping_analytics.py` — one thin forecast endpoint.
- `backend/tests/contracts/api_routes.json` — exactly one new route.

### Frontend create
- `frontend/src/components/DropshippingForecast.tsx` — 7d/30d forecast cards.
- `frontend/src/utils/dropshippingForecast.ts` — pure es/en/pt-BR copy and formatting.
- `frontend/src/dropshipping-forecast.css` — responsive forecast section.
- `frontend/tests/dropshippingForecast.test.ts` — pure presentation tests.

### Frontend modify
- `frontend/src/services/analytics.ts` — forecast DTO/client.
- `frontend/src/utils/dropshippingAnalyticsState.ts` — seventh isolated section.
- `frontend/tests/dropshippingAnalyticsState.test.ts` — seven-section resilience contract.
- `frontend/src/components/DropshippingOverview.tsx` — seventh fetch/render.

---

### Task 1: Reuse V2.2 order economics without changing V2.2 behavior

**Files:**
- Modify: `backend/app/services/dropshipping_unit_economics.py`
- Modify: `backend/tests/test_dropshipping_unit_economics.py`

**Interfaces:**
- Consumes existing `_resolve_outbound_shipping`, `_resolve_payment_fees`, `_resolve_cod_fees`, `_resolve_reverse_logistics`, `get_unit_economics_config`.
- Produces `calculate_order_resolvable_economics(db, organization_id, store_id, orders, *, config=None, prefetched_items=None) -> dict[str, Any]`.

- [ ] **Step 1: Write the failing prefetched-item test**

Append to `backend/tests/test_dropshipping_unit_economics.py`:

```python
def test_order_resolvable_economics_uses_prefetched_items_without_item_query(
    db, store, monkeypatch
):
    config = _configure(db, store)
    order = _order(
        db,
        store,
        number="PREFETCH-1",
        amount=100000,
        lifecycle="delivered",
        payment_method="card",
        item_costs=[(1, 40000)],
    )
    items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    original_query = db.query

    def guarded_query(*entities):
        if OrderItem in entities:
            raise AssertionError("OrderItem query must not run with prefetched_items")
        return original_query(*entities)

    monkeypatch.setattr(db, "query", guarded_query)
    result = unit_engine.calculate_order_resolvable_economics(
        db,
        store.organization_id,
        store.id,
        [order],
        config=config,
        prefetched_items=items,
    )

    assert result["recognized_revenue"] == 100000.0
    assert result["components"]["cogs"]["amount"] == 40000.0
    assert result["known_cost_subtotal"] == 40000.0
    assert result["data_quality"]["status"] == "complete"
```

Also add a characterization test before refactoring the public path:

```python
def test_public_unit_economics_contract_stays_stable_after_reuse_refactor(db, store):
    _configure(db, store, outbound_shipping_cost=10000)
    _order(
        db,
        store,
        number="STABLE-1",
        amount=100000,
        lifecycle="delivered",
        item_costs=[(1, 40000)],
    )
    result = _run(db, store)
    assert result["recognized_revenue"] == 100000.0
    assert result["components"]["cogs"]["amount"] == 40000.0
    assert result["components"]["outbound_shipping"]["amount"] == 10000.0
    assert result["order_counts"]["delivered"] == 1
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
cd backend
pytest -q tests/test_dropshipping_unit_economics.py -k "prefetched or stable"
```

Expected: prefetched test fails with `AttributeError` because `calculate_order_resolvable_economics` does not exist; characterization assertion remains green.

- [ ] **Step 3: Add the prefetched COGS resolver and reusable calculator**

Replace `_resolve_cogs` with this implementation, preserving the current amount/completeness rules:

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
        return _not_applicable(
            {"cost_completeness_pct": 100.0, "item_count": 0}
        )

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

    if not items:
        return _missing(
            "cogs_incomplete",
            amount=ZERO,
            metadata={
                "cost_completeness_pct": 0.0,
                "item_count": 0,
                "items_with_cost": 0,
                "delivered_orders": len(delivered_orders),
            },
        )

    known = ZERO
    with_cost = 0
    for item in items:
        if item.unit_cost is None:
            continue
        with_cost += 1
        known += _decimal(item.unit_cost) * Decimal(item.quantity)

    completeness = float(Decimal(with_cost) / Decimal(len(items)) * HUNDRED)
    metadata = {
        "cost_completeness_pct": completeness,
        "item_count": len(items),
        "items_with_cost": with_cost,
    }
    if with_cost != len(items):
        return _missing("cogs_incomplete", amount=known, metadata=metadata)
    return _component(known, "actual", metadata=metadata)
```

Add:

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
    delivered_orders = [o for o in orders if o.lifecycle_status == "delivered"]
    returned_orders = [o for o in orders if o.lifecycle_status == "returned"]
    cancelled_orders = [o for o in orders if o.lifecycle_status == "cancelled"]
    recognized_revenue = sum(
        (_decimal(order.total_amount) for order in delivered_orders), ZERO
    )
    effective_config = (
        get_unit_economics_config(db, organization_id, store_id)
        if config is None
        else config
    )
    components = {
        "cogs": _resolve_cogs(
            db,
            organization_id,
            store_id,
            delivered_orders,
            prefetched_items=prefetched_items,
        ),
        "outbound_shipping": _resolve_outbound_shipping(
            effective_config, len(delivered_orders) + len(returned_orders)
        ),
        "payment_fees": _resolve_payment_fees(effective_config, delivered_orders),
        "cod_fees": _resolve_cod_fees(effective_config, delivered_orders),
        "reverse_logistics": _resolve_reverse_logistics(
            effective_config, returned_orders
        ),
    }
    known_cost_subtotal = sum(
        (
            _decimal(component["amount"])
            for component in components.values()
            if component["amount"] is not None
        ),
        ZERO,
    )
    return {
        "recognized_revenue": float(recognized_revenue),
        "components": components,
        "known_cost_subtotal": float(known_cost_subtotal),
        "data_quality": _data_quality(components),
        "order_counts": {
            "total": len(orders),
            "delivered": len(delivered_orders),
            "returned": len(returned_orders),
            "cancelled": len(cancelled_orders),
            "fulfilled_outcomes": len(delivered_orders) + len(returned_orders),
        },
    }
```

Refactor `get_store_unit_economics` to use that helper for the five non-ad components, then append `_resolve_ad_component(resolve_meta_ad_spend(...))`, recompute six-component `_data_quality`, `known_cost_subtotal`, contribution, and return the same existing response keys. Do not change any formula or missing-reason string.

- [ ] **Step 4: Run V2.2 regression tests and verify GREEN**

Run:

```bash
cd backend
pytest -q tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_edge_cases.py tests/test_dropshipping_unit_economics_api.py tests/test_unit_economics_meta.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dropshipping_unit_economics.py backend/tests/test_dropshipping_unit_economics.py
git commit -m "refactor: expose reusable unit economics components"
```

---

### Task 2: Build the pure forecasting math engine

**Files:**
- Create: `backend/app/services/dropshipping_forecast_math.py`
- Create: `backend/tests/test_dropshipping_forecast_math.py`

**Interfaces:**
- Produces `ForecastPoint`, `MetricForecast`, and `forecast_metric(history, *, horizon_days, non_negative)`.
- No DB/provider imports are allowed in this module.

- [ ] **Step 1: Write failing tests for models, intervals, and confidence**

Create `backend/tests/test_dropshipping_forecast_math.py` with these helpers/tests:

```python
from datetime import date, timedelta
import math

import pytest

from app.services.dropshipping_forecast_math import ForecastPoint, forecast_metric


def points(values, start=date(2026, 1, 1)):
    return [
        ForecastPoint(start + timedelta(days=index), float(value))
        for index, value in enumerate(values)
    ]


def test_less_than_seven_observations_is_unavailable():
    result = forecast_metric(points([1, 2, 3, 4, 5, 6]), horizon_days=7, non_negative=True)
    assert result.status == "unavailable"
    assert result.reason == "insufficient_history"


def test_constant_series_uses_simple_tie_winner():
    result = forecast_metric(points([5] * 56), horizon_days=7, non_negative=True)
    assert result.status == "available"
    assert result.model == "recent_naive"
    assert result.estimate == pytest.approx(35.0)


def test_linear_series_selects_linear_trend():
    result = forecast_metric(points(list(range(1, 85))), horizon_days=7, non_negative=True)
    assert result.status == "available"
    assert result.model == "linear_trend"
    assert result.estimate > sum(range(78, 85))


def test_weekday_pattern_can_select_weekday_trend():
    values = [20 if index % 7 in (5, 6) else 5 for index in range(112)]
    result = forecast_metric(points(values), horizon_days=7, non_negative=True)
    assert result.status == "available"
    assert result.model == "weekday_trend"


def test_short_history_forces_low_confidence():
    result = forecast_metric(points([10] * 14), horizon_days=7, non_negative=True)
    assert result.confidence == "low"


def test_thirty_day_without_two_long_windows_is_low_confidence():
    result = forecast_metric(points([10] * 60), horizon_days=30, non_negative=True)
    assert result.status == "available"
    assert result.confidence == "low"


def test_non_negative_targets_are_clamped():
    values = [20, 18, 16, 14, 12, 10, 8] * 8
    result = forecast_metric(points(values), horizon_days=30, non_negative=True)
    assert result.estimate is not None and result.estimate >= 0
    assert result.lower_bound is not None and result.lower_bound >= 0


def test_contribution_can_be_negative():
    result = forecast_metric(points([-10] * 56), horizon_days=7, non_negative=False)
    assert result.estimate == pytest.approx(-70.0)
    assert result.lower_bound is not None and result.lower_bound <= result.estimate


def test_all_zero_series_is_finite():
    result = forecast_metric(points([0] * 56), horizon_days=7, non_negative=True)
    assert result.status == "available"
    for value in (result.estimate, result.lower_bound, result.upper_bound):
        assert value is not None and math.isfinite(value)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd backend
pytest -q tests/test_dropshipping_forecast_math.py
```

Expected: import failure because `dropshipping_forecast_math.py` does not exist.

- [ ] **Step 3: Implement the model primitives**

Create `backend/app/services/dropshipping_forecast_math.py` with these constants/types/helpers first:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import math
from typing import Sequence

MAX_HISTORY_DAYS = 365
MIN_HISTORY_DAYS = 7
MIN_SIMPLE_MODEL_TRAIN_DAYS = 3
RECENT_NAIVE_WINDOW = 7
WMA_WINDOW = 14
LINEAR_TREND_WINDOW = 56
WEEKDAY_TREND_WINDOW = 84
WEEKDAY_MIN_HISTORY = 28
WEEKDAY_MIN_SUPPORT_PER_DAY = 2
WEEKDAY_SHRINKAGE = 3.0
MAX_BACKTEST_WINDOWS = 8
LONG_BACKTEST_MIN_TRAIN_DAYS = 28
LONG_BACKTEST_MIN_WINDOWS = 2
SMAPE_SIGNAL_RATIO_MIN = 0.25
MODEL_SCORE_TIE_EPSILON = 1e-9

MODEL_PRIORITY = (
    "recent_naive",
    "weighted_moving_average",
    "linear_trend",
    "weekday_trend",
)

@dataclass(frozen=True)
class ForecastPoint:
    date: date
    value: float

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

@dataclass(frozen=True)
class _Backtest:
    model: str
    metric: str
    error_value: float
    normalized_error_pct: float
    aggregate_residuals: tuple[float, ...]
    signal_ratio: float
    windows: int


def _finite(values: Sequence[float]) -> bool:
    return all(math.isfinite(float(value)) for value in values)


def _linear_coefficients(values: Sequence[float]) -> tuple[float, float]:
    xs = [float(index) for index in range(len(values))]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(values) / len(values)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = 0.0 if denominator == 0 else (
        sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values))
        / denominator
    )
    return y_mean - slope * x_mean, slope


def _weekday_eligible(history: Sequence[ForecastPoint]) -> bool:
    window = history[-WEEKDAY_TREND_WINDOW:]
    if len(window) < WEEKDAY_MIN_HISTORY:
        return False
    counts = {weekday: 0 for weekday in range(7)}
    for point in window:
        counts[point.date.weekday()] += 1
    return all(count >= WEEKDAY_MIN_SUPPORT_PER_DAY for count in counts.values())


def _forecast_candidate(
    model: str,
    history: Sequence[ForecastPoint],
    future_dates: Sequence[date],
    *,
    non_negative: bool,
) -> tuple[float, ...] | None:
    if len(history) < MIN_SIMPLE_MODEL_TRAIN_DAYS:
        return None
    values = [float(point.value) for point in history]
    if not _finite(values):
        return None

    if model == "recent_naive":
        window = values[-RECENT_NAIVE_WINDOW:]
        predicted = [sum(window) / len(window)] * len(future_dates)
    elif model == "weighted_moving_average":
        window = values[-WMA_WINDOW:]
        weights = list(range(1, len(window) + 1))
        level = sum(v * w for v, w in zip(window, weights)) / sum(weights)
        predicted = [level] * len(future_dates)
    elif model == "linear_trend":
        window = values[-LINEAR_TREND_WINDOW:]
        intercept, slope = _linear_coefficients(window)
        predicted = [
            intercept + slope * (len(window) + index)
            for index in range(len(future_dates))
        ]
    elif model == "weekday_trend":
        if not _weekday_eligible(history):
            return None
        window_points = history[-WEEKDAY_TREND_WINDOW:]
        window = [float(point.value) for point in window_points]
        intercept, slope = _linear_coefficients(window)
        residuals = {weekday: [] for weekday in range(7)}
        for index, point in enumerate(window_points):
            baseline = intercept + slope * index
            residuals[point.date.weekday()].append(point.value - baseline)
        effects: dict[int, float] = {}
        for weekday, samples in residuals.items():
            raw = sum(samples) / len(samples)
            support = len(samples)
            effects[weekday] = raw * support / (support + WEEKDAY_SHRINKAGE)
        predicted = [
            intercept
            + slope * (len(window) + index)
            + effects[future_date.weekday()]
            for index, future_date in enumerate(future_dates)
        ]
    else:
        raise ValueError(f"unknown_forecast_model:{model}")

    if not _finite(predicted):
        return None
    if non_negative:
        predicted = [max(0.0, value) for value in predicted]
    return tuple(float(value) for value in predicted)
```

- [ ] **Step 4: Implement backtesting, scoring, ranges, confidence, and public forecast**

Append this implementation to the same module:

```python
def _validation_cutoffs(length: int, validation_days: int) -> list[int]:
    if validation_days == 1:
        cutoffs = list(range(MIN_SIMPLE_MODEL_TRAIN_DAYS, length))
        return cutoffs[-MAX_BACKTEST_WINDOWS:]
    minimum_train = 28 if validation_days == 30 else 7
    latest = length - validation_days
    if latest < minimum_train:
        return []
    cutoffs: list[int] = []
    cutoff = latest
    while cutoff >= minimum_train and len(cutoffs) < MAX_BACKTEST_WINDOWS:
        cutoffs.append(cutoff)
        cutoff -= validation_days
    return sorted(cutoffs)


def _smape(actual: Sequence[float], predicted: Sequence[float]) -> tuple[float | None, float]:
    informative = [
        (a, p)
        for a, p in zip(actual, predicted)
        if abs(a) + abs(p) > 0
    ]
    signal_ratio = len(informative) / len(actual) if actual else 0.0
    if not informative or signal_ratio < SMAPE_SIGNAL_RATIO_MIN:
        return None, signal_ratio
    values = [200.0 * abs(a - p) / (abs(a) + abs(p)) for a, p in informative]
    return sum(values) / len(values), signal_ratio


def _mae(actual: Sequence[float], predicted: Sequence[float]) -> float:
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual)


def _score(actual: Sequence[float], predicted: Sequence[float]) -> tuple[str, float, float, float]:
    smape, signal_ratio = _smape(actual, predicted)
    if smape is not None:
        return "smape", smape, smape, signal_ratio
    mae = _mae(actual, predicted)
    scale = sum(abs(value) for value in actual) / len(actual)
    normalized = 0.0 if scale == 0 and mae == 0 else (100.0 if scale == 0 else mae / scale * 100.0)
    return "mae", mae, normalized, signal_ratio


def _backtest_model(
    model: str,
    history: Sequence[ForecastPoint],
    *,
    validation_days: int,
    non_negative: bool,
) -> _Backtest | None:
    actual_values: list[float] = []
    predicted_values: list[float] = []
    aggregate_residuals: list[float] = []
    windows = 0
    for cutoff in _validation_cutoffs(len(history), validation_days):
        train = history[:cutoff]
        validation = history[cutoff:cutoff + validation_days]
        future_dates = [point.date for point in validation]
        prediction = _forecast_candidate(
            model, train, future_dates, non_negative=non_negative
        )
        if prediction is None or len(prediction) != len(validation):
            continue
        actual = [float(point.value) for point in validation]
        actual_values.extend(actual)
        predicted_values.extend(prediction)
        aggregate_residuals.append(sum(actual) - sum(prediction))
        windows += 1
    if windows == 0:
        return None
    metric, error_value, normalized_error, signal_ratio = _score(
        actual_values, predicted_values
    )
    if not _finite([error_value, normalized_error, signal_ratio]):
        return None
    return _Backtest(
        model=model,
        metric=metric,
        error_value=error_value,
        normalized_error_pct=normalized_error,
        aggregate_residuals=tuple(aggregate_residuals),
        signal_ratio=signal_ratio,
        windows=windows,
    )


def _select_backtest(
    history: Sequence[ForecastPoint],
    *,
    validation_days: int,
    non_negative: bool,
) -> _Backtest | None:
    candidates: list[_Backtest] = []
    for model in MODEL_PRIORITY:
        result = _backtest_model(
            model,
            history,
            validation_days=validation_days,
            non_negative=non_negative,
        )
        if result is not None:
            candidates.append(result)
    if not candidates:
        return None
    priority = {name: index for index, name in enumerate(MODEL_PRIORITY)}
    best = candidates[0]
    for candidate in candidates[1:]:
        delta = candidate.normalized_error_pct - best.normalized_error_pct
        if delta < -MODEL_SCORE_TIE_EPSILON:
            best = candidate
        elif abs(delta) <= MODEL_SCORE_TIE_EPSILON and priority[candidate.model] < priority[best.model]:
            best = candidate
    return best


def nearest_rank_quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile_requires_values")
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def _range_width(residuals: Sequence[float]) -> float:
    absolute = [abs(value) for value in residuals]
    width = nearest_rank_quantile(absolute, 0.80)
    if len(absolute) < 3:
        width *= 1.50
    elif len(absolute) < 5:
        width *= 1.25
    return width


def _confidence(
    *,
    history_days: int,
    backtest_windows: int,
    normalized_error_pct: float,
    signal_ratio: float,
    horizon_days: int,
    long_windows: int,
) -> str:
    if horizon_days == 30 and long_windows < LONG_BACKTEST_MIN_WINDOWS:
        return "low"
    if history_days < 28 or backtest_windows < 2 or normalized_error_pct > 40.0:
        return "low"
    if (
        history_days >= 56
        and backtest_windows >= 4
        and signal_ratio >= 0.25
        and normalized_error_pct <= 20.0
    ):
        return "high"
    return "medium"


def _unavailable(history_days: int, reason: str) -> MetricForecast:
    quality = ForecastQuality(
        history_days=history_days,
        observations=history_days,
        non_zero_observations=0,
        backtest_windows=0,
        long_backtest_windows=0,
        error_metric=None,
        error_value=None,
        normalized_error_pct=None,
        confidence="low",
    )
    return MetricForecast(
        status="unavailable",
        reason=reason,
        estimate=None,
        lower_bound=None,
        upper_bound=None,
        confidence="low",
        model=None,
        quality=quality,
    )


def forecast_metric(
    history: Sequence[ForecastPoint],
    *,
    horizon_days: int,
    non_negative: bool,
) -> MetricForecast:
    if horizon_days not in (7, 30):
        raise ValueError("unsupported_forecast_horizon")
    history = tuple(history[-MAX_HISTORY_DAYS:])
    if len(history) < MIN_HISTORY_DAYS:
        return _unavailable(len(history), "insufficient_history")

    short_validation = 1 if len(history) < 14 else 7
    short = _select_backtest(
        history,
        validation_days=short_validation,
        non_negative=non_negative,
    )
    long_result = _select_backtest(
        history,
        validation_days=30,
        non_negative=non_negative,
    )
    chosen = (
        long_result
        if horizon_days == 30
        and long_result is not None
        and long_result.windows >= LONG_BACKTEST_MIN_WINDOWS
        else short
    )
    if chosen is None:
        return _unavailable(len(history), "backtest_unavailable")

    future_dates = [
        history[-1].date + timedelta(days=offset)
        for offset in range(1, horizon_days + 1)
    ]
    prediction = _forecast_candidate(
        chosen.model,
        history,
        future_dates,
        non_negative=non_negative,
    )
    if prediction is None:
        return _unavailable(len(history), "non_finite_model_output")
    estimate = sum(prediction)

    residuals = chosen.aggregate_residuals
    width = _range_width(residuals)
    if horizon_days == 30 and chosen is short:
        width *= 30.0 if short_validation == 1 else 30.0 / 7.0
    lower = estimate - width
    upper = estimate + width
    if non_negative:
        estimate = max(0.0, estimate)
        lower = max(0.0, lower)
        upper = max(0.0, upper)
    lower = min(lower, estimate)
    upper = max(upper, estimate)
    if not _finite([estimate, lower, upper]):
        return _unavailable(len(history), "non_finite_model_output")

    long_windows = 0 if long_result is None else long_result.windows
    confidence = _confidence(
        history_days=len(history),
        backtest_windows=chosen.windows,
        normalized_error_pct=chosen.normalized_error_pct,
        signal_ratio=chosen.signal_ratio,
        horizon_days=horizon_days,
        long_windows=long_windows,
    )
    quality = ForecastQuality(
        history_days=len(history),
        observations=len(history),
        non_zero_observations=sum(1 for point in history if point.value != 0),
        backtest_windows=chosen.windows,
        long_backtest_windows=long_windows,
        error_metric=chosen.metric,
        error_value=chosen.error_value,
        normalized_error_pct=chosen.normalized_error_pct,
        confidence=confidence,
    )
    return MetricForecast(
        status="available",
        reason=None,
        estimate=float(estimate),
        lower_bound=float(lower),
        upper_bound=float(upper),
        confidence=confidence,
        model=chosen.model,
        quality=quality,
    )
```

- [ ] **Step 5: Run the pure suite and verify GREEN**

Run: `cd backend && pytest -q tests/test_dropshipping_forecast_math.py`

Expected: PASS. If the synthetic weekday/linear winner fixture does not uniquely favor the intended model, adjust only the synthetic input values while preserving the asserted behavior and fixed algorithm constants; do not change algorithm constants to fit tests.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dropshipping_forecast_math.py backend/tests/test_dropshipping_forecast_math.py
git commit -m "feat: add deterministic forecast engine"
```

---

### Task 3: Build store-local historical order series

**Files:**
- Create: `backend/app/services/dropshipping_forecasting.py`
- Create: `backend/tests/test_dropshipping_forecasting.py`

**Interfaces:**
- Produces `resolve_forecast_calendar`, `_load_historical_cohort`, and operational daily `ForecastPoint` sequences.

- [ ] **Step 1: Write failing timezone and zero-day tests**

Create the test module with existing SQLAlchemy test-fixture conventions and these assertions:

```python
from datetime import date, datetime, timezone

import pytest

from app.services.dropshipping_forecasting import (
    InvalidStoreTimezoneError,
    resolve_forecast_calendar,
)


def test_bogota_anchor_excludes_partial_current_day(store):
    store.timezone = "America/Bogota"
    calendar = resolve_forecast_calendar(
        store,
        datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc),
    )
    assert calendar.local_today == date(2026, 9, 13)
    assert calendar.anchor_date == date(2026, 9, 12)


def test_positive_offset_can_be_next_local_day(store):
    store.timezone = "Asia/Tokyo"
    calendar = resolve_forecast_calendar(
        store,
        datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc),
    )
    assert calendar.local_today == date(2026, 9, 14)


def test_invalid_timezone_is_not_silently_replaced(store):
    store.timezone = "Not/A_Zone"
    with pytest.raises(InvalidStoreTimezoneError):
        resolve_forecast_calendar(store, datetime.now(timezone.utc))
```

Add one DB-backed test that seeds delivered orders on Sep 8 and Sep 10 local dates, freezes local today Sep 13, calls `_load_historical_cohort`, and asserts dates Sep 8–12 exist with Sep 9/11/12 as zero-order days and no Sep 13 observation.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd backend && pytest -q tests/test_dropshipping_forecasting.py -k "anchor or offset or invalid or zero"`.

Expected: import failure because forecasting service does not exist.

- [ ] **Step 3: Implement calendar/cohort loading**

Create `backend/app/services/dropshipping_forecasting.py`:

```python
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from ..models import Order, OrderItem, Store
from .dropshipping_forecast_math import ForecastPoint, forecast_metric
from .dropshipping_unit_economics import calculate_order_resolvable_economics
from .unit_economics_config_service import get_unit_economics_config
from .unit_economics_meta import resolve_meta_ad_spend

MAX_HISTORY_DAYS = 365

class InvalidStoreTimezoneError(ValueError):
    code = "invalid_store_timezone"

@dataclass(frozen=True)
class ForecastCalendar:
    timezone: str
    local_today: date
    anchor_date: date
    candidate_start_date: date
    query_start_utc: datetime
    query_end_utc_exclusive: datetime

@dataclass(frozen=True)
class HistoricalCohort:
    calendar: ForecastCalendar
    dates: tuple[date, ...]
    orders: tuple[Order, ...]
    orders_by_date: dict[date, tuple[Order, ...]]


def _zone(store: Store) -> ZoneInfo:
    try:
        return ZoneInfo(store.timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise InvalidStoreTimezoneError(store.timezone) from exc


def _utc_naive(local_date: date, zone: ZoneInfo) -> datetime:
    local_midnight = datetime.combine(local_date, time.min, tzinfo=zone)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def resolve_forecast_calendar(store: Store, now_utc: datetime) -> ForecastCalendar:
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)
    zone = _zone(store)
    local_today = now_utc.astimezone(zone).date()
    anchor = local_today - timedelta(days=1)
    candidate_start = anchor - timedelta(days=MAX_HISTORY_DAYS - 1)
    return ForecastCalendar(
        timezone=store.timezone,
        local_today=local_today,
        anchor_date=anchor,
        candidate_start_date=candidate_start,
        query_start_utc=_utc_naive(candidate_start, zone),
        query_end_utc_exclusive=_utc_naive(local_today, zone),
    )


def _order_local_date(order: Order, zone: ZoneInfo) -> date:
    value = order.created_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.astimezone(zone).date()


def _date_range(start: date, end: date) -> tuple[date, ...]:
    count = (end - start).days + 1
    return tuple(start + timedelta(days=index) for index in range(count))


def _load_historical_cohort(
    db: Session,
    organization_id: int,
    store: Store,
    *,
    now_utc: datetime,
) -> HistoricalCohort:
    calendar = resolve_forecast_calendar(store, now_utc)
    orders = (
        db.query(Order)
        .filter(
            Order.organization_id == organization_id,
            Order.store_id == store.id,
            Order.created_at >= calendar.query_start_utc,
            Order.created_at < calendar.query_end_utc_exclusive,
        )
        .order_by(Order.created_at.asc(), Order.id.asc())
        .all()
    )
    if not orders:
        return HistoricalCohort(calendar, (), (), {})
    zone = _zone(store)
    grouped: dict[date, list[Order]] = defaultdict(list)
    for order in orders:
        grouped[_order_local_date(order, zone)].append(order)
    first_date = max(calendar.candidate_start_date, min(grouped))
    dates = _date_range(first_date, calendar.anchor_date)
    return HistoricalCohort(
        calendar=calendar,
        dates=dates,
        orders=tuple(orders),
        orders_by_date={day: tuple(grouped.get(day, [])) for day in dates},
    )


def _operational_points(cohort: HistoricalCohort) -> tuple[list[ForecastPoint], list[ForecastPoint]]:
    order_points: list[ForecastPoint] = []
    revenue_points: list[ForecastPoint] = []
    for day in cohort.dates:
        delivered = [
            order
            for order in cohort.orders_by_date[day]
            if order.lifecycle_status == "delivered"
        ]
        order_points.append(ForecastPoint(day, float(len(delivered))))
        revenue_points.append(
            ForecastPoint(
                day,
                float(sum(Decimal(str(order.total_amount)) for order in delivered)),
            )
        )
    return order_points, revenue_points
```

- [ ] **Step 4: Add and run boundary tests**

Append tests for `America/Los_Angeles`, DST-aware `America/New_York`, a UTC-midnight order that belongs to previous Bogota local date, a current-local-day order excluded by the query end, and a store with no completed orders returning `dates == ()`.

Run: `cd backend && pytest -q tests/test_dropshipping_forecasting.py`.

Expected: PASS for calendar/history tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dropshipping_forecasting.py backend/tests/test_dropshipping_forecasting.py
git commit -m "feat: build timezone-aware forecasting history"
```

---

### Task 4: Add contribution history, one-call Meta smoothing, and response assembly

**Files:**
- Modify: `backend/app/services/dropshipping_forecasting.py`
- Modify: `backend/tests/test_dropshipping_forecasting.py`

**Interfaces:**
- Produces `get_store_forecast(db, organization_id, store, *, now_utc=None) -> dict[str, Any]`.

- [ ] **Step 1: Write failing contribution and Meta-call tests**

Append tests that configure 14 completed days, patch `forecasting.resolve_meta_ad_spend`, and assert exactly one provider resolution plus partial naming when Meta is missing:

```python
def test_meta_resolved_once_and_complete_contribution_named_correctly(
    db, store, monkeypatch
):
    seed_complete_fourteen_day_history(db, store)
    calls = []

    def fake_meta(db_arg, organization_id, store_arg, date_from, date_to):
        calls.append((date_from, date_to))
        return {
            "amount": Decimal("1400"),
            "source": "meta_ads",
            "status": "actual",
            "reason": None,
            "metadata": {},
        }

    monkeypatch.setattr(forecasting, "resolve_meta_ad_spend", fake_meta)
    payload = forecasting.get_store_forecast(
        db,
        store.organization_id,
        store,
        now_utc=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )
    assert len(calls) == 1
    assert payload["history"]["contribution_data_quality"]["status"] == "complete"
    assert payload["horizons"]["7d"]["contribution"]["metric"] == "contribution_profit_forecast"


def test_missing_meta_yields_known_cost_contribution(db, store, monkeypatch):
    seed_complete_fourteen_day_history(db, store)
    monkeypatch.setattr(
        forecasting,
        "resolve_meta_ad_spend",
        lambda *args, **kwargs: {
            "amount": None,
            "source": "meta_ads",
            "status": "missing",
            "reason": "meta_not_connected",
            "metadata": {},
        },
    )
    payload = forecasting.get_store_forecast(
        db,
        store.organization_id,
        store,
        now_utc=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )
    quality = payload["history"]["contribution_data_quality"]
    assert quality["status"] == "incomplete"
    assert quality["missing_components"] == ["ad_spend"]
    assert payload["horizons"]["7d"]["contribution"]["metric"] == "known_cost_contribution_forecast"
```

Implement `seed_complete_fourteen_day_history` inside the test module using existing `Organization/Store/Order/OrderItem` constructors and `replace_unit_economics_config` with zero shipping/payment/COD/return costs; create one delivered order/item per day with known `unit_cost`.

- [ ] **Step 2: Run contribution tests and verify RED**

Run: `cd backend && pytest -q tests/test_dropshipping_forecasting.py -k "meta or contribution"`.

Expected: fail because `get_store_forecast` is not implemented.

- [ ] **Step 3: Add exact Meta allocation and contribution-series helpers**

Append to service:

```python
def _allocate_meta(total: Decimal, days: int) -> list[Decimal]:
    if days <= 0:
        return []
    base = total / Decimal(days)
    values = [base for _ in range(days - 1)]
    values.append(total - sum(values, Decimal("0")))
    return values


def _load_items(
    db: Session,
    organization_id: int,
    store_id: int,
    order_ids: list[int],
) -> list[OrderItem]:
    if not order_ids:
        return []
    return (
        db.query(OrderItem)
        .filter(
            OrderItem.organization_id == organization_id,
            OrderItem.store_id == store_id,
            OrderItem.order_id.in_(order_ids),
        )
        .all()
    )


def _contribution_points(
    db: Session,
    organization_id: int,
    store: Store,
    cohort: HistoricalCohort,
) -> tuple[list[ForecastPoint], dict[str, Any]]:
    if not cohort.dates:
        return [], {
            "status": "incomplete",
            "metric": "known_cost_contribution_forecast",
            "missing_components": [],
            "missing_reasons": {},
        }

    config = get_unit_economics_config(db, organization_id, store.id)
    items = _load_items(
        db,
        organization_id,
        store.id,
        [order.id for order in cohort.orders],
    )
    local_from = datetime.combine(cohort.dates[0], time.min)
    local_to = datetime.combine(cohort.calendar.local_today, time.min)
    meta = resolve_meta_ad_spend(
        db,
        organization_id,
        store,
        local_from,
        local_to,
    )
    meta_available = meta.get("status") == "actual"
    meta_total = Decimal(str(meta.get("amount") or 0)) if meta_available else Decimal("0")
    meta_allocations = _allocate_meta(meta_total, len(cohort.dates))

    missing_reasons: dict[str, str | None] = {}
    points: list[ForecastPoint] = []
    for index, day in enumerate(cohort.dates):
        economics = calculate_order_resolvable_economics(
            db,
            organization_id,
            store.id,
            list(cohort.orders_by_date[day]),
            config=config,
            prefetched_items=items,
        )
        for name, reason in economics["data_quality"]["missing_reasons"].items():
            missing_reasons.setdefault(name, reason)
        contribution = (
            Decimal(str(economics["recognized_revenue"]))
            - Decimal(str(economics["known_cost_subtotal"]))
        )
        if meta_available:
            contribution -= meta_allocations[index]
        points.append(ForecastPoint(day, float(contribution)))

    if not meta_available:
        missing_reasons.setdefault("ad_spend", meta.get("reason"))
    missing_components = sorted(missing_reasons)
    status = "incomplete" if missing_components else "complete"
    metric = (
        "known_cost_contribution_forecast"
        if missing_components
        else "contribution_profit_forecast"
    )
    return points, {
        "status": status,
        "metric": metric,
        "missing_components": missing_components,
        "missing_reasons": missing_reasons,
    }
```

This uses naive store-local calendar midnights for the existing Meta exact-period resolver while DB query boundaries remain UTC-converted.

- [ ] **Step 4: Add response assembly with exact horizons**

Append:

```python
def _metric_dict(result) -> dict[str, Any]:
    return asdict(result)


def _horizon(
    *,
    local_today: date,
    days: int,
    order_points: list[ForecastPoint],
    revenue_points: list[ForecastPoint],
    contribution_points: list[ForecastPoint],
    contribution_quality: dict[str, Any],
) -> dict[str, Any]:
    contribution = _metric_dict(
        forecast_metric(contribution_points, horizon_days=days, non_negative=False)
    )
    contribution["metric"] = contribution_quality["metric"]
    contribution["data_quality"] = contribution_quality
    return {
        "date_from": local_today.isoformat(),
        "date_to_exclusive": (local_today + timedelta(days=days)).isoformat(),
        "delivered_orders": _metric_dict(
            forecast_metric(order_points, horizon_days=days, non_negative=True)
        ),
        "delivered_revenue": _metric_dict(
            forecast_metric(revenue_points, horizon_days=days, non_negative=True)
        ),
        "contribution": contribution,
    }


def get_store_forecast(
    db: Session,
    organization_id: int,
    store: Store,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    effective_now = now_utc or datetime.now(timezone.utc)
    if effective_now.tzinfo is None:
        effective_now = effective_now.replace(tzinfo=timezone.utc)
    cohort = _load_historical_cohort(
        db,
        organization_id,
        store,
        now_utc=effective_now,
    )
    order_points, revenue_points = _operational_points(cohort)
    contribution_points, contribution_quality = _contribution_points(
        db, organization_id, store, cohort
    )
    history_from = cohort.dates[0].isoformat() if cohort.dates else None
    history_to = cohort.dates[-1].isoformat() if cohort.dates else None
    return {
        "store_id": store.id,
        "currency": store.currency,
        "timezone": store.timezone,
        "generated_at": effective_now.astimezone(timezone.utc).isoformat(),
        "forecast_anchor_date": cohort.calendar.anchor_date.isoformat(),
        "history": {
            "date_from": history_from,
            "date_to": history_to,
            "days": len(cohort.dates),
            "contribution_data_quality": contribution_quality,
        },
        "horizons": {
            "7d": _horizon(
                local_today=cohort.calendar.local_today,
                days=7,
                order_points=order_points,
                revenue_points=revenue_points,
                contribution_points=contribution_points,
                contribution_quality=contribution_quality,
            ),
            "30d": _horizon(
                local_today=cohort.calendar.local_today,
                days=30,
                order_points=order_points,
                revenue_points=revenue_points,
                contribution_points=contribution_points,
                contribution_quality=contribution_quality,
            ),
        },
    }
```

- [ ] **Step 5: Add exact tests for partial COGS and Meta reconciliation**

Add:

```python
def test_meta_allocation_reconciles_exactly():
    values = forecasting._allocate_meta(Decimal("100"), 3)
    assert sum(values, Decimal("0")) == Decimal("100")


def test_partial_cogs_keeps_known_cost_and_marks_partial(db, store, monkeypatch):
    seed_history_with_one_missing_item_cost(db, store)
    monkeypatch.setattr(
        forecasting,
        "resolve_meta_ad_spend",
        lambda *args, **kwargs: {
            "amount": Decimal("0"),
            "source": "meta_ads",
            "status": "actual",
            "reason": None,
            "metadata": {},
        },
    )
    payload = forecasting.get_store_forecast(
        db,
        store.organization_id,
        store,
        now_utc=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )
    quality = payload["history"]["contribution_data_quality"]
    assert quality["status"] == "incomplete"
    assert "cogs" in quality["missing_components"]
    assert quality["missing_reasons"]["cogs"] == "cogs_incomplete"
```

Implement `seed_history_with_one_missing_item_cost` in the same test module by creating at least 7 completed daily delivered orders; on one day create two items, one with a numeric cost and one `unit_cost=None`.

- [ ] **Step 6: Run service tests and V2.2 regressions**

Run:

```bash
cd backend
pytest -q tests/test_dropshipping_forecasting.py tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_edge_cases.py tests/test_unit_economics_meta.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dropshipping_forecasting.py backend/tests/test_dropshipping_forecasting.py
git commit -m "feat: assemble store forecasting service"
```

---

### Task 5: Expose the tenant-safe forecast API and route contract

**Files:**
- Modify: `backend/app/api/dropshipping_analytics.py`
- Create: `backend/tests/test_dropshipping_forecasting_api.py`
- Modify: `backend/tests/contracts/api_routes.json`

**Interfaces:**
- Produces `GET /api/stores/{store_id}/analytics/dropshipping/forecast` with permission `analytics.read`.

- [ ] **Step 1: Write failing API tests**

Follow `test_dropshipping_unit_economics_api.py` fixture style and include these tests:

```python
def test_forecast_endpoint_returns_store_contract(client, account, monkeypatch):
    _, _, _, store = account
    monkeypatch.setattr(
        forecast_service,
        "get_store_forecast",
        lambda db, organization_id, store_arg: {
            "store_id": store_arg.id,
            "currency": store_arg.currency,
            "timezone": store_arg.timezone,
            "generated_at": "2026-09-13T20:00:00+00:00",
            "forecast_anchor_date": "2026-09-12",
            "history": {"date_from": None, "date_to": None, "days": 0, "contribution_data_quality": {"status": "incomplete", "metric": "known_cost_contribution_forecast", "missing_components": [], "missing_reasons": {}}},
            "horizons": {"7d": {}, "30d": {}},
        },
    )
    response = client.get(f"/api/stores/{store.id}/analytics/dropshipping/forecast")
    assert response.status_code == 200
    assert response.json()["store_id"] == store.id


def test_forecast_restricted_membership_cannot_read_unassigned_store(client, db, account):
    org, _, membership, assigned_store = account
    unassigned = Store(
        organization_id=org.id,
        name="Unassigned Forecast Store",
        slug="unassigned-forecast-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
    )
    db.add(unassigned)
    db.flush()
    membership.all_stores = False
    membership.stores.append(assigned_store)
    db.commit()
    response = client.get(f"/api/stores/{unassigned.id}/analytics/dropshipping/forecast")
    assert response.status_code == 403
    assert response.json()["detail"] == "Store access denied"


def test_forecast_invalid_timezone_is_422(client, account, db):
    _, _, _, store = account
    store.timezone = "Not/A_Zone"
    db.commit()
    response = client.get(f"/api/stores/{store.id}/analytics/dropshipping/forecast")
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_store_timezone"
```

Also copy/adapt existing Unit Economics API tests for foreign store 404, inactive store 404, and role without `analytics.read` 403. Add one request with arbitrary `date_from/date_to` query strings and assert the service mock receives no date arguments.

- [ ] **Step 2: Run API tests and verify RED**

Run: `cd backend && pytest -q tests/test_dropshipping_forecasting_api.py`.

Expected: 404/route-not-found failures.

- [ ] **Step 3: Add the thin route**

In `dropshipping_analytics.py`, import:

```python
from ..services.dropshipping_forecasting import (
    InvalidStoreTimezoneError,
    get_store_forecast,
)
```

Add:

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

Do not add date query parameters and do not catch generic exceptions.

- [ ] **Step 4: Update strict route snapshot and verify exactly one route addition**

Run:

```bash
cd backend
python -m pytest tests/test_route_contract.py --update-snapshot
python -m pytest -q tests/test_route_contract.py
```

Review the snapshot diff. The only new pair must be:

```json
["GET", "/api/stores/{store_id}/analytics/dropshipping/forecast"]
```

- [ ] **Step 5: Run backend focused verification**

```bash
cd backend
pytest -q tests/test_dropshipping_forecast_math.py tests/test_dropshipping_forecasting.py tests/test_dropshipping_forecasting_api.py tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_api.py tests/test_route_contract.py
ruff check app/ tests/ tools/
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/dropshipping_analytics.py backend/tests/test_dropshipping_forecasting_api.py backend/tests/contracts/api_routes.json
git commit -m "feat: expose dropshipping store forecast API"
```

---

### Task 6: Add frontend forecast contract and pure presentation helpers

**Files:**
- Modify: `frontend/src/services/analytics.ts`
- Create: `frontend/src/utils/dropshippingForecast.ts`
- Create: `frontend/tests/dropshippingForecast.test.ts`

**Interfaces:**
- Produces typed `getDropshippingForecast(storeId)` with no date args.
- Produces pure es/en/pt-BR confidence/model/reason/contribution-label helpers.

- [ ] **Step 1: Write the failing pure tests**

Create:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import {
  contributionForecastLabel,
  forecastConfidenceLabel,
  forecastModelLabel,
  forecastUnavailableCopy,
} from "../src/utils/dropshippingForecast.ts";

test("confidence copy supports the three analytics locales", () => {
  assert.equal(forecastConfidenceLabel("low", "es"), "Baja confianza");
  assert.equal(forecastConfidenceLabel("medium", "en"), "Medium confidence");
  assert.equal(forecastConfidenceLabel("high", "pt-BR"), "Alta confiança");
});

test("partial contribution is never labeled as complete", () => {
  assert.equal(
    contributionForecastLabel("known_cost_contribution_forecast", "es"),
    "Contribución proyectada con costos conocidos",
  );
  assert.equal(
    contributionForecastLabel("contribution_profit_forecast", "es"),
    "Contribución proyectada",
  );
});

test("model and unavailable reason copy are stable", () => {
  assert.equal(forecastModelLabel("weekday_trend", "es"), "Tendencia + patrón semanal");
  assert.match(forecastUnavailableCopy("insufficient_history", "es"), /historial/i);
});
```

- [ ] **Step 2: Run test and verify RED**

Run: `cd frontend && node --test tests/dropshippingForecast.test.ts`.

Expected: module-not-found for `dropshippingForecast.ts`.

- [ ] **Step 3: Implement the pure copy helpers**

Create `frontend/src/utils/dropshippingForecast.ts`:

```ts
export type ForecastLocale = "es" | "en" | "pt-BR";
export type ForecastConfidence = "low" | "medium" | "high";
export type ForecastModel =
  | "recent_naive"
  | "weighted_moving_average"
  | "linear_trend"
  | "weekday_trend";
export type ContributionMetric =
  | "contribution_profit_forecast"
  | "known_cost_contribution_forecast";

function locale(language: string): ForecastLocale {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

const confidenceCopy = {
  es: { low: "Baja confianza", medium: "Confianza media", high: "Alta confianza" },
  en: { low: "Low confidence", medium: "Medium confidence", high: "High confidence" },
  "pt-BR": { low: "Baixa confiança", medium: "Confiança média", high: "Alta confiança" },
} satisfies Record<ForecastLocale, Record<ForecastConfidence, string>>;

const modelCopy = {
  es: { recent_naive: "Nivel reciente", weighted_moving_average: "Promedio ponderado", linear_trend: "Tendencia lineal", weekday_trend: "Tendencia + patrón semanal" },
  en: { recent_naive: "Recent level", weighted_moving_average: "Weighted average", linear_trend: "Linear trend", weekday_trend: "Trend + weekly pattern" },
  "pt-BR": { recent_naive: "Nível recente", weighted_moving_average: "Média ponderada", linear_trend: "Tendência linear", weekday_trend: "Tendência + padrão semanal" },
} satisfies Record<ForecastLocale, Record<ForecastModel, string>>;

const contributionCopy = {
  es: { contribution_profit_forecast: "Contribución proyectada", known_cost_contribution_forecast: "Contribución proyectada con costos conocidos" },
  en: { contribution_profit_forecast: "Projected contribution", known_cost_contribution_forecast: "Projected contribution with known costs" },
  "pt-BR": { contribution_profit_forecast: "Contribuição projetada", known_cost_contribution_forecast: "Contribuição projetada com custos conhecidos" },
} satisfies Record<ForecastLocale, Record<ContributionMetric, string>>;

const unavailableCopy: Record<ForecastLocale, Record<string, string>> = {
  es: { insufficient_history: "Aún no hay suficiente historial para pronosticar.", backtest_unavailable: "No hay suficiente historial validable para este pronóstico.", non_finite_model_output: "No fue posible producir un pronóstico numérico seguro." },
  en: { insufficient_history: "There is not enough history to forecast yet.", backtest_unavailable: "There is not enough validated history for this forecast.", non_finite_model_output: "A safe numeric forecast could not be produced." },
  "pt-BR": { insufficient_history: "Ainda não há histórico suficiente para prever.", backtest_unavailable: "Não há histórico validável suficiente para esta previsão.", non_finite_model_output: "Não foi possível produzir uma previsão numérica segura." },
};

export function forecastConfidenceLabel(value: ForecastConfidence, language: string): string {
  return confidenceCopy[locale(language)][value];
}

export function forecastModelLabel(value: ForecastModel, language: string): string {
  return modelCopy[locale(language)][value];
}

export function contributionForecastLabel(value: ContributionMetric, language: string): string {
  return contributionCopy[locale(language)][value];
}

export function forecastUnavailableCopy(reason: string | null, language: string): string {
  const copy = unavailableCopy[locale(language)];
  return copy[reason || ""] || copy.backtest_unavailable;
}
```

- [ ] **Step 4: Add exact DTOs and HTTP client**

In `analytics.ts` add:

```ts
export type DropshippingForecastConfidence = "low" | "medium" | "high";
export type DropshippingForecastStatus = "available" | "unavailable";
export type DropshippingForecastModel = "recent_naive" | "weighted_moving_average" | "linear_trend" | "weekday_trend";

export interface DropshippingForecastQuality {
  history_days: number;
  observations: number;
  non_zero_observations: number;
  backtest_windows: number;
  long_backtest_windows: number;
  error_metric: "smape" | "mae" | null;
  error_value: number | null;
  normalized_error_pct: number | null;
  confidence: DropshippingForecastConfidence;
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

export interface DropshippingContributionForecast extends DropshippingForecastMetric {
  metric: "contribution_profit_forecast" | "known_cost_contribution_forecast";
  data_quality: {
    status: "complete" | "incomplete";
    metric: "contribution_profit_forecast" | "known_cost_contribution_forecast";
    missing_components: string[];
    missing_reasons: Record<string, string | null>;
  };
}

export interface DropshippingForecastHorizon {
  date_from: string;
  date_to_exclusive: string;
  delivered_orders: DropshippingForecastMetric;
  delivered_revenue: DropshippingForecastMetric;
  contribution: DropshippingContributionForecast;
}

export interface DropshippingForecastResponse {
  store_id: number;
  currency: string;
  timezone: string;
  generated_at: string;
  forecast_anchor_date: string;
  history: {
    date_from: string | null;
    date_to: string | null;
    days: number;
    contribution_data_quality: DropshippingContributionForecast["data_quality"];
  };
  horizons: { "7d": DropshippingForecastHorizon; "30d": DropshippingForecastHorizon };
}

export async function getDropshippingForecast(storeId: number) {
  const response = await api.get<DropshippingForecastResponse>(
    `/api/stores/${storeId}/analytics/dropshipping/forecast`,
  );
  return response.data;
}
```

- [ ] **Step 5: Run pure tests and build**

Run:

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

### Task 7: Render Forecasting as the seventh isolated Analytics section

**Files:**
- Create: `frontend/src/components/DropshippingForecast.tsx`
- Create: `frontend/src/dropshipping-forecast.css`
- Modify: `frontend/src/utils/dropshippingAnalyticsState.ts`
- Modify: `frontend/tests/dropshippingAnalyticsState.test.ts`
- Modify: `frontend/src/components/DropshippingOverview.tsx`

**Interfaces:**
- Consumes `DropshippingForecastResponse` and pure copy helpers from Task 6.
- Produces isolated forecast UI; no chart library.

- [ ] **Step 1: Write the failing seventh-section tests**

Replace the expected section array and add isolation tests:

```ts
test("dropshipping analytics exposes seven isolated sections", () => {
  assert.deepEqual(DROPSHIPPING_ANALYTICS_SECTIONS, [
    "overview",
    "profitability",
    "products",
    "orders",
    "insights",
    "unitEconomics",
    "forecast",
  ]);
});

test("forecast can fail without hiding established analytics", () => {
  const results: PromiseSettledResult<unknown>[] = [
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: [] },
    { status: "fulfilled", value: {} },
    { status: "fulfilled", value: { insights: [] } },
    { status: "fulfilled", value: {} },
    { status: "rejected", reason: new Error("forecast failed") },
  ];
  const failed = getFailedDropshippingSections(results);
  assert.deepEqual(failed, ["forecast"]);
  assert.equal(allDropshippingSectionsFailed(failed), false);
});

test("all seven rejected results are a global failure", () => {
  const results = DROPSHIPPING_ANALYTICS_SECTIONS.map((section) => ({
    status: "rejected" as const,
    reason: section,
  }));
  assert.equal(allDropshippingSectionsFailed(getFailedDropshippingSections(results)), true);
});
```

- [ ] **Step 2: Run test and verify RED**

Run: `cd frontend && node --test tests/dropshippingAnalyticsState.test.ts`.

Expected: array mismatch because forecast is not registered.

- [ ] **Step 3: Register forecast and integrate the seventh fetch**

Update `dropshippingAnalyticsState.ts` to:

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

In `DropshippingOverview.tsx`, import `getDropshippingForecast`, `DropshippingForecastResponse`, and `DropshippingForecast`. Extend `DashboardData` with:

```ts
forecast: DropshippingForecastResponse | null;
```

Extend `SECTION_LABELS` with:

```ts
forecast: "pronóstico",
```

Use this exact request order:

```ts
Promise.allSettled([
  getDropshippingOverview(storeId, dateFrom, dateTo),
  getDropshippingProfitability(storeId, dateFrom, dateTo),
  getDropshippingProducts(storeId, dateFrom, dateTo),
  getDropshippingOrders(storeId, dateFrom, dateTo),
  getDropshippingDecisionInsights(storeId, dateFrom, dateTo),
  getDropshippingUnitEconomics(storeId, dateFrom, dateTo),
  getDropshippingForecast(storeId),
])
```

Map `forecast: settledValue(results[6])`. Do not pass dates to the forecast client.

- [ ] **Step 4: Implement the forecast component**

Create `DropshippingForecast.tsx` with this complete presentation skeleton; keep styling in CSS:

```tsx
import { AlertTriangle, CalendarRange, TrendingUp } from "lucide-react";
import type {
  DropshippingForecastMetric,
  DropshippingForecastResponse,
} from "../services/analytics";
import {
  contributionForecastLabel,
  forecastConfidenceLabel,
  forecastModelLabel,
  forecastUnavailableCopy,
} from "../utils/dropshippingForecast";
import "../dropshipping-forecast.css";

interface Props {
  data: DropshippingForecastResponse | null;
  unavailable: boolean;
  language: string;
  currency: string;
}

function MetricCard({
  label,
  metric,
  language,
  formatValue,
}: {
  label: string;
  metric: DropshippingForecastMetric;
  language: string;
  formatValue: (value: number) => string;
}) {
  if (metric.status === "unavailable" || metric.estimate === null) {
    return (
      <div className="forecast-metric is-unavailable">
        <span>{label}</span>
        <strong>—</strong>
        <small>{forecastUnavailableCopy(metric.reason, language)}</small>
      </div>
    );
  }
  const lower = metric.lower_bound === null ? metric.estimate : metric.lower_bound;
  const upper = metric.upper_bound === null ? metric.estimate : metric.upper_bound;
  return (
    <div className="forecast-metric">
      <span>{label}</span>
      <strong>{formatValue(metric.estimate)}</strong>
      <small>{formatValue(lower)} – {formatValue(upper)}</small>
      <div className={`forecast-confidence is-${metric.confidence}`}>
        {forecastConfidenceLabel(metric.confidence, language)}
      </div>
      {metric.model && (
        <small>{forecastModelLabel(metric.model, language)} · {metric.quality.backtest_windows} backtests</small>
      )}
    </div>
  );
}

export default function DropshippingForecast({ data, unavailable, language, currency }: Props) {
  const formatMoney = (value: number) => new Intl.NumberFormat(
    language.toLowerCase().startsWith("pt") ? "pt-BR" : language.toLowerCase().startsWith("en") ? "en-US" : "es-CO",
    { style: "currency", currency, maximumFractionDigits: 0 },
  ).format(value);
  const formatOrders = (value: number) => Math.round(value).toLocaleString();

  if (unavailable) {
    return <section className="dropshipping-forecast"><div className="forecast-empty"><AlertTriangle size={17} /> Pronóstico temporalmente no disponible.</div></section>;
  }
  if (!data) return null;

  return (
    <section className="dropshipping-forecast">
      <div className="forecast-header">
        <div><span>FORECASTING V2.3</span><h3><TrendingUp size={18} /> Pronóstico de tienda</h3></div>
        <small><CalendarRange size={14} /> Historial: {data.history.days} días</small>
      </div>
      <div className="dropshipping-forecast-horizons">
        {(["7d", "30d"] as const).map((key) => {
          const horizon = data.horizons[key];
          const partial = horizon.contribution.data_quality.status === "incomplete";
          return (
            <div className="forecast-horizon" key={key}>
              <h4>Próximos {key === "7d" ? "7" : "30"} días</h4>
              <MetricCard label="Pedidos entregados" metric={horizon.delivered_orders} language={language} formatValue={formatOrders} />
              <MetricCard label="Ingresos entregados" metric={horizon.delivered_revenue} language={language} formatValue={formatMoney} />
              <div className={partial ? "forecast-partial" : ""}>
                {partial && <span className="forecast-partial-badge">Parcial</span>}
                <MetricCard label={contributionForecastLabel(horizon.contribution.metric, language)} metric={horizon.contribution} language={language} formatValue={formatMoney} />
                {partial && <small>Faltan: {horizon.contribution.data_quality.missing_components.join(", ")}</small>}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
```

When polishing copy, use the Task 6 locale helpers for localized metric/section copy rather than adding a global i18n dependency; the structure above is the required data behavior.

Render the component immediately after `DropshippingUnitEconomics`:

```tsx
<DropshippingForecast
  data={forecast}
  unavailable={unavailableSections.includes("forecast")}
  language={i18n.resolvedLanguage || i18n.language || "es"}
  currency={effectiveCurrency}
/>
```

- [ ] **Step 5: Add responsive CSS**

Create:

```css
.dropshipping-forecast { margin-bottom: 18px; }
.forecast-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 14px; }
.forecast-header h3 { display: flex; gap: 8px; align-items: center; margin: 4px 0 0; }
.dropshipping-forecast-horizons { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.forecast-horizon { border: 1px solid var(--border); border-radius: 16px; padding: 16px; background: var(--surface); }
.forecast-metric { display: grid; gap: 4px; padding: 12px 0; border-bottom: 1px solid var(--border); }
.forecast-metric:last-child { border-bottom: 0; }
.forecast-metric strong { font-size: 1.2rem; }
.forecast-confidence { width: fit-content; border-radius: 999px; padding: 3px 8px; font-size: .75rem; }
.forecast-partial { margin-top: 8px; }
.forecast-partial-badge { display: inline-flex; border-radius: 999px; padding: 3px 8px; font-size: .75rem; }
.forecast-empty { display: flex; align-items: center; gap: 8px; padding: 16px; }
@media (max-width: 760px) {
  .forecast-header { flex-direction: column; }
  .dropshipping-forecast-horizons { grid-template-columns: 1fr; }
}
```

If the repository CSS variable is not `--surface` or `--border`, replace those two tokens with the existing analytics card variables discovered in `analytics-v2.css`; do not introduce hard-coded theme colors.

- [ ] **Step 6: Run frontend verification and verify GREEN**

Run:

```bash
cd frontend
npm test
npm run lint
npm run build
```

Expected: PASS. New code adds no lint errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/DropshippingForecast.tsx frontend/src/dropshipping-forecast.css frontend/src/components/DropshippingOverview.tsx frontend/src/utils/dropshippingAnalyticsState.ts frontend/tests/dropshippingAnalyticsState.test.ts
git commit -m "feat: render store forecasting in analytics"
```

---

### Task 8: Harden performance, finite serialization, and regressions

**Files:**
- Modify: `backend/tests/test_dropshipping_forecasting.py`
- Modify: `backend/tests/test_dropshipping_forecast_math.py`
- Modify V2.3 production files only if these tests expose a defect.

**Interfaces:** no new public interface.

- [ ] **Step 1: Add the provider-call-count test**

Add a test that seeds 60 days, patches `resolve_meta_ad_spend` with a counter, calls `get_store_forecast`, and asserts `calls == 1`. Also patch `_load_items` with a wrapper counter and assert one invocation. This guards against per-day provider/DB access.

```python
def test_forecast_uses_one_meta_resolution_and_one_item_preload(db, store, monkeypatch):
    seed_complete_sixty_day_history(db, store)
    meta_calls = 0
    item_calls = 0
    original_load_items = forecasting._load_items

    def fake_meta(*args, **kwargs):
        nonlocal meta_calls
        meta_calls += 1
        return {"amount": Decimal("0"), "source": "meta_ads", "status": "actual", "reason": None, "metadata": {}}

    def counted_items(*args, **kwargs):
        nonlocal item_calls
        item_calls += 1
        return original_load_items(*args, **kwargs)

    monkeypatch.setattr(forecasting, "resolve_meta_ad_spend", fake_meta)
    monkeypatch.setattr(forecasting, "_load_items", counted_items)
    forecasting.get_store_forecast(db, store.organization_id, store, now_utc=FIXED_NOW)
    assert meta_calls == 1
    assert item_calls == 1
```

- [ ] **Step 2: Add recursive finite-response test**

```python
def assert_finite_tree(value):
    if isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for child in value.values():
            assert_finite_tree(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            assert_finite_tree(child)

@pytest.mark.parametrize(
    "values",
    [
        [0.0] * 56,
        [0.0, 1000000.0] * 28,
        [1e12] * 56,
        [-1000.0] * 56,
        [10.0] * 55 + [1e9],
    ],
)
def test_metric_forecast_never_emits_non_finite_numbers(values):
    result = forecast_metric(points(values), horizon_days=30, non_negative=False)
    assert_finite_tree(asdict(result))
```

- [ ] **Step 3: Run all dropshipping regression tests**

```bash
cd backend
pytest -q tests/test_dropshipping_analytics.py tests/test_dropshipping_decision_intelligence.py tests/test_dropshipping_decision_intelligence_api.py tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_api.py tests/test_dropshipping_unit_economics_edge_cases.py tests/test_unit_economics_meta.py tests/test_dropshipping_forecast_math.py tests/test_dropshipping_forecasting.py tests/test_dropshipping_forecasting_api.py tests/test_route_contract.py
```

Expected: PASS.

- [ ] **Step 4: Run full CI-equivalent backend and frontend validation**

```bash
cd backend
ruff check app/ tests/ tools/
python -m pytest -q --tb=short
cd ../frontend
npm ci
npm run lint
npm test
npm run build
```

Expected: all commands PASS.

- [ ] **Step 5: Commit hardening changes if the tests added files/lines**

```bash
git add backend/tests/test_dropshipping_forecasting.py backend/tests/test_dropshipping_forecast_math.py backend/app/services/dropshipping_forecasting.py backend/app/services/dropshipping_forecast_math.py
git commit -m "test: harden dropshipping forecasting v2.3"
```

If production files did not change, omit them from `git add`. Do not create an empty commit.

---

### Task 9: PR and merge gate

**Files:** no planned source edits.

**Interfaces:** final integration gate only.

- [ ] **Step 1: Verify branch scope**

Run:

```bash
git fetch origin
git diff --name-only origin/main...HEAD
git diff --stat origin/main...HEAD
```

Expected scope: V2.3 spec/plan, forecast services/tests, narrow Unit Economics reuse refactor, one analytics route/snapshot change, forecast frontend files/integration. No migration/model persistence, no unrelated subsystem edits.

- [ ] **Step 2: Verify the approved spec acceptance criteria manually**

Read `docs/superpowers/specs/2026-09-13-dropshipping-forecasting-v2-3-design.md` and confirm all of these concrete conditions in the diff/test evidence: 7d+30d, store-local cutoff, adaptive deterministic selection, probable ranges, confidence evidence, complete/partial contribution naming, one Meta resolution, no inferred missing cost, tenant/store isolation, no date-filter dependency, seventh-section isolation, no NaN/Infinity, no heavyweight ML dependency.

- [ ] **Step 3: Open the PR**

Use title:

```text
feat: add dropshipping store forecasting v2.3
```

PR body must include the exact focused/full test commands from Tasks 5–8 and their observed results.

- [ ] **Step 4: Require fresh GitHub Actions on the exact final head**

The `Validate Pull Request` run must show success for Detect changed scopes, backend shard 0, backend shard 1, frontend validation, and final aggregator. Do not merge based on an older SHA or cancelled run.

- [ ] **Step 5: Fix failures only through systematic debugging**

If any CI job fails, load `superpowers:systematic-debugging`, reproduce the failure from logs, patch the feature branch, run the narrow test first, then full relevant validation, and require a new all-green workflow run on the new head.

- [ ] **Step 6: Squash merge and verify main**

After final-head CI is green, squash merge. Verify PR `merged == true`, record the merge commit SHA, and fetch `main` to confirm its HEAD equals that merge/squash commit before starting the next feature.

---

## Definition of Done

- [ ] Current partial store-local day is excluded.
- [ ] >=7 observations can produce deterministic 7d/30d order and revenue forecasts.
- [ ] Available forecasts include estimate, probable range, confidence, selected model, and diagnostics.
- [ ] Model selection is rolling-backtest-driven and deterministic.
- [ ] Short history cannot produce inflated confidence.
- [ ] Direct 30d high/medium confidence requires at least two 30-day validation windows.
- [ ] Zero-heavy/all-zero series are safe.
- [ ] Orders/revenue are non-negative; contribution may be negative.
- [ ] No NaN/Infinity or inverted range reaches JSON.
- [ ] V2.2 financial formulas have one authoritative implementation.
- [ ] Meta spend resolves at most once and smoothing reconciles exactly.
- [ ] Complete economics returns `contribution_profit_forecast`.
- [ ] Incomplete economics returns `known_cost_contribution_forecast` plus missing metadata.
- [ ] API enforces `analytics.read`, active store, tenant/store scope, and membership store access.
- [ ] Route snapshot contains exactly one approved route addition.
- [ ] Forecast client sends no dashboard date filters.
- [ ] Forecast is the seventh isolated `Promise.allSettled` section.
- [ ] Forecast failure cannot blank established Analytics sections.
- [ ] es/en/pt-BR presentation helpers pass.
- [ ] Backend Ruff + full pytest pass.
- [ ] Frontend lint + tests + build pass.
- [ ] Exact final PR head is fully green in GitHub Actions before merge.
