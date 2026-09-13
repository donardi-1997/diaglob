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
- Invalid `Store.timezone` is explicit; never use server timezone as fallback.
- Use at most 365 completed local days. Materialize missing calendar dates as zero observations.
- Fewer than 7 observations makes a metric unavailable. Fewer than 28 forces confidence `low`.
- Candidate simplicity order is `recent_naive`, `weighted_moving_average`, `linear_trend`, `weekday_trend`.
- Probable ranges come from out-of-sample residuals.
- Never emit NaN/Infinity or an inverted range.
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
```

Backtesting is fixed as follows:

- 7–13 observations: expanding one-day validation cutoffs, beginning after 3 training observations.
- 14+ observations: newest eight rolling 7-day validation windows, minimum 7 training observations.
- Direct 30-day validation: newest eight rolling 30-day windows, minimum 28 training observations. Two direct 30-day windows first exist at 88 observations.
- Without two direct 30-day windows, use the model selected by shorter out-of-sample validation, scale range width by `30/7` from 7-day residuals or by `30` from one-day residuals, and force 30-day confidence `low`.
- Use sMAPE only when at least 25% of held-out point pairs have `abs(actual) + abs(predicted) > 0`; otherwise use MAE.
- For confidence, MAE normalizes as `MAE / mean(abs(actual)) * 100` when scale is positive. All-zero actual/predicted has normalized error 0; zero actual with non-zero MAE has normalized error 100.
- Candidate score ties within `1e-9` use the simplicity order.

Probable range uses nearest-rank q80:

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

For 30d, fewer than two direct 30-day validation windows overrides the result to `low`.

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

### Task 1: Reuse V2.2 order economics without semantic drift

**Files:**
- Modify: `backend/app/services/dropshipping_unit_economics.py`
- Modify: `backend/tests/test_dropshipping_unit_economics.py`

**Interfaces:**
- Consumes existing V2.2 cost resolvers and `get_unit_economics_config`.
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

Also add:

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

- [ ] **Step 2: Verify RED plus existing characterization GREEN**

```bash
cd backend
pytest -q tests/test_dropshipping_unit_economics.py -k "prefetched or stable"
```

Expected: prefetched test fails because the public helper does not exist; stable contract assertion passes.

- [ ] **Step 3: Implement reusable non-ad economics**

Change `_resolve_cogs` to accept `prefetched_items` and use this exact branch:

```python
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
```

Leave the current `items == []`, known COGS, completeness percentage, and missing-state arithmetic unchanged after that branch.

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
    delivered_orders = [order for order in orders if order.lifecycle_status == "delivered"]
    returned_orders = [order for order in orders if order.lifecycle_status == "returned"]
    cancelled_orders = [order for order in orders if order.lifecycle_status == "cancelled"]
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
        "reverse_logistics": _resolve_reverse_logistics(effective_config, returned_orders),
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

Refactor `get_store_unit_economics()` so the five non-ad components come from this helper, then append `_resolve_ad_component(resolve_meta_ad_spend(...))`, recompute six-component `_data_quality`, recompute `known_cost_subtotal`, and keep all existing V2.2 response keys/formulas unchanged.

- [ ] **Step 4: Verify GREEN with all V2.2 finance regressions**

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

### Task 2: Build the pure deterministic forecasting engine

**Files:**
- Create: `backend/app/services/dropshipping_forecast_math.py`
- Create: `backend/tests/test_dropshipping_forecast_math.py`

**Interfaces:**
- Produces `ForecastPoint`, `ForecastQuality`, `MetricForecast`, and `forecast_metric(history, *, horizon_days, non_negative)`.
- This file imports no DB/provider code.

- [ ] **Step 1: Write failing algorithm tests**

Create `backend/tests/test_dropshipping_forecast_math.py`:

```python
from dataclasses import asdict
from datetime import date, timedelta
import math

import pytest

from app.services.dropshipping_forecast_math import ForecastPoint, forecast_metric


def points(values, start=date(2026, 1, 1)):
    return [
        ForecastPoint(start + timedelta(days=index), float(value))
        for index, value in enumerate(values)
    ]


def assert_finite_tree(value):
    if isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for child in value.values():
            assert_finite_tree(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            assert_finite_tree(child)


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


def test_weekday_pattern_selects_weekday_trend():
    values = [30 if index % 7 in (1, 5) else 4 for index in range(112)]
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
    result = forecast_metric(
        points([20, 18, 16, 14, 12, 10, 8] * 8),
        horizon_days=30,
        non_negative=True,
    )
    assert result.estimate is not None and result.estimate >= 0
    assert result.lower_bound is not None and result.lower_bound >= 0
    assert result.upper_bound is not None and result.upper_bound >= result.estimate


def test_contribution_can_be_negative():
    result = forecast_metric(points([-10] * 56), horizon_days=7, non_negative=False)
    assert result.estimate == pytest.approx(-70.0)
    assert result.lower_bound is not None and result.lower_bound <= result.estimate


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

- [ ] **Step 2: Verify RED**

```bash
cd backend
pytest -q tests/test_dropshipping_forecast_math.py
```

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement model primitives**

Create `backend/app/services/dropshipping_forecast_math.py` beginning with:

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
        level = sum(value * weight for value, weight in zip(window, weights)) / sum(weights)
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
        effects = {}
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

- [ ] **Step 4: Implement backtesting, scoring, ranges, confidence, and public API**

Append:

```python
def _validation_cutoffs(length: int, validation_days: int) -> list[int]:
    if validation_days == 1:
        return list(range(MIN_SIMPLE_MODEL_TRAIN_DAYS, length))[-MAX_BACKTEST_WINDOWS:]
    minimum_train = 28 if validation_days == 30 else 7
    latest = length - validation_days
    if latest < minimum_train:
        return []
    cutoffs = []
    cutoff = latest
    while cutoff >= minimum_train and len(cutoffs) < MAX_BACKTEST_WINDOWS:
        cutoffs.append(cutoff)
        cutoff -= validation_days
    return sorted(cutoffs)


def _smape(actual: Sequence[float], predicted: Sequence[float]) -> tuple[float | None, float]:
    informative = [(a, p) for a, p in zip(actual, predicted) if abs(a) + abs(p) > 0]
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
    actual_values = []
    predicted_values = []
    aggregate_residuals = []
    windows = 0
    for cutoff in _validation_cutoffs(len(history), validation_days):
        train = history[:cutoff]
        validation = history[cutoff:cutoff + validation_days]
        prediction = _forecast_candidate(
            model,
            train,
            [point.date for point in validation],
            non_negative=non_negative,
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
    metric, error_value, normalized_error, signal_ratio = _score(actual_values, predicted_values)
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
    candidates = [
        result
        for model in MODEL_PRIORITY
        if (
            result := _backtest_model(
                model,
                history,
                validation_days=validation_days,
                non_negative=non_negative,
            )
        ) is not None
    ]
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
    if history_days >= 56 and backtest_windows >= 4 and signal_ratio >= 0.25 and normalized_error_pct <= 20.0:
        return "high"
    return "medium"


def _unavailable(history: Sequence[ForecastPoint], reason: str) -> MetricForecast:
    quality = ForecastQuality(
        history_days=len(history),
        observations=len(history),
        non_zero_observations=sum(1 for point in history if point.value != 0),
        backtest_windows=0,
        long_backtest_windows=0,
        error_metric=None,
        error_value=None,
        normalized_error_pct=None,
        confidence="low",
    )
    return MetricForecast("unavailable", reason, None, None, None, "low", None, quality)


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
        return _unavailable(history, "insufficient_history")

    short_validation = 1 if len(history) < 14 else 7
    short = _select_backtest(history, validation_days=short_validation, non_negative=non_negative)
    long_result = _select_backtest(history, validation_days=30, non_negative=non_negative)
    chosen = (
        long_result
        if horizon_days == 30 and long_result is not None and long_result.windows >= LONG_BACKTEST_MIN_WINDOWS
        else short
    )
    if chosen is None:
        return _unavailable(history, "backtest_unavailable")

    future_dates = [history[-1].date + timedelta(days=offset) for offset in range(1, horizon_days + 1)]
    prediction = _forecast_candidate(chosen.model, history, future_dates, non_negative=non_negative)
    if prediction is None:
        return _unavailable(history, "non_finite_model_output")
    estimate = sum(prediction)
    width = _range_width(chosen.aggregate_residuals)
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
        return _unavailable(history, "non_finite_model_output")

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

- [ ] **Step 5: Verify GREEN**

```bash
cd backend
pytest -q tests/test_dropshipping_forecast_math.py
```

Expected: PASS. If a synthetic winner fixture is not uniquely discriminative, change only that test's synthetic values; do not change the approved constants to satisfy a fixture.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dropshipping_forecast_math.py backend/tests/test_dropshipping_forecast_math.py
git commit -m "feat: add deterministic forecast engine"
```

---

### Task 3: Build timezone-correct historical store series

**Files:**
- Create: `backend/app/services/dropshipping_forecasting.py`
- Create: `backend/tests/test_dropshipping_forecasting.py`

**Interfaces:**
- Produces `resolve_forecast_calendar`, `_load_historical_cohort`, `_operational_points`, and shared test seed helpers inside the test module.

- [ ] **Step 1: Create exact DB fixtures and seed helpers in the new test file**

Create `backend/tests/test_dropshipping_forecasting.py` beginning with:

```python
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Order, OrderItem, Organization, Store
from app.services.unit_economics_config_service import replace_unit_economics_config
import app.services.dropshipping_forecasting as forecasting

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_dropshipping_forecasting.db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
FIXED_NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("./test_dropshipping_forecasting.db")
    except FileNotFoundError:
        pass

@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture()
def store(db):
    organization = Organization(
        name="Forecast Org",
        slug="forecast-org",
        plan="growth",
        subscription_status="active",
    )
    db.add(organization)
    db.flush()
    result = Store(
        organization_id=organization.id,
        name="Forecast Store",
        slug="forecast-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def configure_zero_operating_costs(db, store):
    return replace_unit_economics_config(
        db,
        store.organization_id,
        store.id,
        {
            "outbound_shipping_cost": 0,
            "return_logistics_cost": 0,
            "default_payment_fee_percent": 0,
            "default_payment_fee_fixed": 0,
            "default_cod_fee_percent": 0,
            "payment_methods": [],
        },
    )


def add_delivered_day(db, store, local_day, *, amount=100000, unit_cost=40000, suffix="A"):
    created_at = datetime(local_day.year, local_day.month, local_day.day, 17, 0, 0)
    order = Order(
        organization_id=store.organization_id,
        store_id=store.id,
        order_number=f"F-{local_day.isoformat()}-{suffix}",
        total_amount=amount,
        currency=store.currency,
        lifecycle_status="delivered",
        payment_method="card",
        created_at=created_at,
    )
    db.add(order)
    db.flush()
    db.add(
        OrderItem(
            order_id=order.id,
            organization_id=store.organization_id,
            store_id=store.id,
            title="Forecast item",
            sku=f"SKU-{local_day.isoformat()}-{suffix}",
            quantity=1,
            unit_price=amount,
            unit_cost=unit_cost,
            currency=store.currency,
        )
    )
    db.commit()
    return order


def seed_complete_days(db, store, days):
    configure_zero_operating_costs(db, store)
    first = date(2026, 9, 14) - timedelta(days=days - 1)
    for index in range(days):
        add_delivered_day(db, store, first + timedelta(days=index), suffix=str(index))
```

`created_at=17:00 UTC` maps to midday in Bogota, avoiding boundary ambiguity in generic seed helpers.

- [ ] **Step 2: Write failing calendar/history tests**

Append:

```python
def test_bogota_anchor_excludes_current_partial_day(store):
    calendar = forecasting.resolve_forecast_calendar(store, FIXED_NOW)
    assert calendar.local_today == date(2026, 9, 15)
    assert calendar.anchor_date == date(2026, 9, 14)


def test_positive_offset_can_be_next_local_day(store):
    store.timezone = "Asia/Tokyo"
    calendar = forecasting.resolve_forecast_calendar(
        store,
        datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc),
    )
    assert calendar.local_today == date(2026, 9, 14)


def test_invalid_timezone_is_explicit(store):
    store.timezone = "Not/A_Zone"
    with pytest.raises(forecasting.InvalidStoreTimezoneError):
        forecasting.resolve_forecast_calendar(store, FIXED_NOW)


def test_missing_calendar_days_become_zero_observations(db, store):
    add_delivered_day(db, store, date(2026, 9, 10), suffix="10")
    add_delivered_day(db, store, date(2026, 9, 12), suffix="12")
    cohort = forecasting._load_historical_cohort(
        db,
        store.organization_id,
        store,
        now_utc=FIXED_NOW,
    )
    order_points, revenue_points = forecasting._operational_points(cohort)
    assert [point.date for point in order_points] == [
        date(2026, 9, 10),
        date(2026, 9, 11),
        date(2026, 9, 12),
        date(2026, 9, 13),
        date(2026, 9, 14),
    ]
    assert [point.value for point in order_points] == [1.0, 0.0, 1.0, 0.0, 0.0]
    assert revenue_points[1].value == 0.0
```

- [ ] **Step 3: Verify RED**

```bash
cd backend
pytest -q tests/test_dropshipping_forecasting.py
```

Expected: import/module errors because the service does not exist.

- [ ] **Step 4: Implement calendar, cohort loading, and operational points**

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
    effective_now = now_utc.replace(tzinfo=timezone.utc) if now_utc.tzinfo is None else now_utc.astimezone(timezone.utc)
    zone = _zone(store)
    local_today = effective_now.astimezone(zone).date()
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
    value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return value.astimezone(zone).date()


def _date_range(start: date, end: date) -> tuple[date, ...]:
    return tuple(start + timedelta(days=index) for index in range((end - start).days + 1))


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
    grouped = defaultdict(list)
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
    order_points = []
    revenue_points = []
    for day in cohort.dates:
        delivered = [order for order in cohort.orders_by_date[day] if order.lifecycle_status == "delivered"]
        order_points.append(ForecastPoint(day, float(len(delivered))))
        revenue_points.append(
            ForecastPoint(
                day,
                float(sum(Decimal(str(order.total_amount)) for order in delivered)),
            )
        )
    return order_points, revenue_points
```

- [ ] **Step 5: Add exact boundary tests**

Append:

```python
def test_los_angeles_calendar_uses_local_date(store):
    store.timezone = "America/Los_Angeles"
    calendar = forecasting.resolve_forecast_calendar(
        store,
        datetime(2026, 9, 15, 2, 0, tzinfo=timezone.utc),
    )
    assert calendar.local_today == date(2026, 9, 14)


def test_new_york_dst_zone_is_supported(store):
    store.timezone = "America/New_York"
    calendar = forecasting.resolve_forecast_calendar(
        store,
        datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc),
    )
    assert calendar.local_today == date(2026, 11, 1)


def test_current_local_day_order_is_excluded(db, store):
    add_delivered_day(db, store, date(2026, 9, 14), suffix="complete")
    current = Order(
        organization_id=store.organization_id,
        store_id=store.id,
        order_number="CURRENT-DAY",
        total_amount=90000,
        currency="COP",
        lifecycle_status="delivered",
        payment_method="card",
        created_at=datetime(2026, 9, 15, 14, 0, 0),
    )
    db.add(current)
    db.commit()
    cohort = forecasting._load_historical_cohort(db, store.organization_id, store, now_utc=FIXED_NOW)
    assert all(order.order_number != "CURRENT-DAY" for order in cohort.orders)


def test_empty_store_has_no_fabricated_history(db, store):
    cohort = forecasting._load_historical_cohort(db, store.organization_id, store, now_utc=FIXED_NOW)
    assert cohort.dates == ()
    assert cohort.orders == ()
```

- [ ] **Step 6: Verify GREEN**

```bash
cd backend
pytest -q tests/test_dropshipping_forecasting.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/dropshipping_forecasting.py backend/tests/test_dropshipping_forecasting.py
git commit -m "feat: build timezone-aware forecasting history"
```

---

### Task 4: Add contribution history, one Meta resolution, and response assembly

**Files:**
- Modify: `backend/app/services/dropshipping_forecasting.py`
- Modify: `backend/tests/test_dropshipping_forecasting.py`

**Interfaces:**
- Produces `get_store_forecast(db, organization_id, store, *, now_utc=None) -> dict[str, Any]`.

- [ ] **Step 1: Add exact contribution seed helpers and failing tests**

Append these helpers to the test module:

```python
def seed_history_with_missing_cogs(db, store):
    configure_zero_operating_costs(db, store)
    first = date(2026, 9, 8)
    for index in range(7):
        day = first + timedelta(days=index)
        if index != 3:
            add_delivered_day(db, store, day, suffix=str(index))
            continue
        order = Order(
            organization_id=store.organization_id,
            store_id=store.id,
            order_number="PARTIAL-COGS",
            total_amount=100000,
            currency="COP",
            lifecycle_status="delivered",
            payment_method="card",
            created_at=datetime(day.year, day.month, day.day, 17, 0, 0),
        )
        db.add(order)
        db.flush()
        db.add_all([
            OrderItem(
                order_id=order.id,
                organization_id=store.organization_id,
                store_id=store.id,
                title="Known item",
                sku="KNOWN-COST",
                quantity=1,
                unit_price=50000,
                unit_cost=20000,
                currency="COP",
            ),
            OrderItem(
                order_id=order.id,
                organization_id=store.organization_id,
                store_id=store.id,
                title="Missing item",
                sku="MISSING-COST",
                quantity=1,
                unit_price=50000,
                unit_cost=None,
                currency="COP",
            ),
        ])
        db.commit()


def actual_zero_meta(*args, **kwargs):
    return {
        "amount": Decimal("0"),
        "source": "meta_ads",
        "status": "actual",
        "reason": None,
        "metadata": {},
    }
```

Append failing tests:

```python
def test_meta_resolved_once_and_complete_contribution_named_correctly(db, store, monkeypatch):
    seed_complete_days(db, store, 14)
    calls = []

    def fake_meta(*args, **kwargs):
        calls.append((args, kwargs))
        return {
            "amount": Decimal("1400"),
            "source": "meta_ads",
            "status": "actual",
            "reason": None,
            "metadata": {},
        }

    monkeypatch.setattr(forecasting, "resolve_meta_ad_spend", fake_meta)
    payload = forecasting.get_store_forecast(db, store.organization_id, store, now_utc=FIXED_NOW)
    assert len(calls) == 1
    assert payload["history"]["contribution_data_quality"]["status"] == "complete"
    assert payload["horizons"]["7d"]["contribution"]["metric"] == "contribution_profit_forecast"


def test_missing_meta_yields_known_cost_contribution(db, store, monkeypatch):
    seed_complete_days(db, store, 14)
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
    payload = forecasting.get_store_forecast(db, store.organization_id, store, now_utc=FIXED_NOW)
    quality = payload["history"]["contribution_data_quality"]
    assert quality["status"] == "incomplete"
    assert quality["missing_components"] == ["ad_spend"]
    assert payload["horizons"]["7d"]["contribution"]["metric"] == "known_cost_contribution_forecast"


def test_partial_cogs_keeps_known_amount_but_marks_partial(db, store, monkeypatch):
    seed_history_with_missing_cogs(db, store)
    monkeypatch.setattr(forecasting, "resolve_meta_ad_spend", actual_zero_meta)
    payload = forecasting.get_store_forecast(db, store.organization_id, store, now_utc=FIXED_NOW)
    quality = payload["history"]["contribution_data_quality"]
    assert quality["status"] == "incomplete"
    assert "cogs" in quality["missing_components"]
    assert quality["missing_reasons"]["cogs"] == "cogs_incomplete"
```

- [ ] **Step 2: Verify RED**

```bash
cd backend
pytest -q tests/test_dropshipping_forecasting.py -k "meta or contribution or cogs"
```

Expected: failures because `get_store_forecast` is not implemented.

- [ ] **Step 3: Implement contribution helpers**

Append to the service:

```python
def _allocate_meta(total: Decimal, days: int) -> list[Decimal]:
    if days <= 0:
        return []
    base = total / Decimal(days)
    values = [base for _ in range(days - 1)]
    values.append(total - sum(values, Decimal("0")))
    return values


def _load_items(db: Session, organization_id: int, store_id: int, order_ids: list[int]) -> list[OrderItem]:
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
    items = _load_items(db, organization_id, store.id, [order.id for order in cohort.orders])
    meta = resolve_meta_ad_spend(
        db,
        organization_id,
        store,
        datetime.combine(cohort.dates[0], time.min),
        datetime.combine(cohort.calendar.local_today, time.min),
    )
    meta_available = meta.get("status") == "actual"
    meta_total = Decimal(str(meta.get("amount") or 0)) if meta_available else Decimal("0")
    meta_allocations = _allocate_meta(meta_total, len(cohort.dates))

    missing_reasons = {}
    points = []
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
        contribution = Decimal(str(economics["recognized_revenue"])) - Decimal(str(economics["known_cost_subtotal"]))
        if meta_available:
            contribution -= meta_allocations[index]
        points.append(ForecastPoint(day, float(contribution)))

    if not meta_available:
        missing_reasons.setdefault("ad_spend", meta.get("reason"))
    missing_components = sorted(missing_reasons)
    return points, {
        "status": "incomplete" if missing_components else "complete",
        "metric": "known_cost_contribution_forecast" if missing_components else "contribution_profit_forecast",
        "missing_components": missing_components,
        "missing_reasons": missing_reasons,
    }
```

- [ ] **Step 4: Implement response assembly**

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
    contribution = _metric_dict(forecast_metric(contribution_points, horizon_days=days, non_negative=False))
    contribution["metric"] = contribution_quality["metric"]
    contribution["data_quality"] = contribution_quality
    return {
        "date_from": local_today.isoformat(),
        "date_to_exclusive": (local_today + timedelta(days=days)).isoformat(),
        "delivered_orders": _metric_dict(forecast_metric(order_points, horizon_days=days, non_negative=True)),
        "delivered_revenue": _metric_dict(forecast_metric(revenue_points, horizon_days=days, non_negative=True)),
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
    cohort = _load_historical_cohort(db, organization_id, store, now_utc=effective_now)
    order_points, revenue_points = _operational_points(cohort)
    contribution_points, contribution_quality = _contribution_points(db, organization_id, store, cohort)
    return {
        "store_id": store.id,
        "currency": store.currency,
        "timezone": store.timezone,
        "generated_at": effective_now.astimezone(timezone.utc).isoformat(),
        "forecast_anchor_date": cohort.calendar.anchor_date.isoformat(),
        "history": {
            "date_from": cohort.dates[0].isoformat() if cohort.dates else None,
            "date_to": cohort.dates[-1].isoformat() if cohort.dates else None,
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

- [ ] **Step 5: Add Meta reconciliation and horizon-date assertions**

Append:

```python
def test_meta_allocation_reconciles_exactly():
    values = forecasting._allocate_meta(Decimal("100"), 3)
    assert sum(values, Decimal("0")) == Decimal("100")


def test_horizon_dates_start_today_and_are_half_open(db, store, monkeypatch):
    seed_complete_days(db, store, 14)
    monkeypatch.setattr(forecasting, "resolve_meta_ad_spend", actual_zero_meta)
    payload = forecasting.get_store_forecast(db, store.organization_id, store, now_utc=FIXED_NOW)
    assert payload["horizons"]["7d"]["date_from"] == "2026-09-15"
    assert payload["horizons"]["7d"]["date_to_exclusive"] == "2026-09-22"
    assert payload["horizons"]["30d"]["date_to_exclusive"] == "2026-10-15"
```

- [ ] **Step 6: Verify GREEN plus V2.2 regressions**

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
- Produces `GET /api/stores/{store_id}/analytics/dropshipping/forecast`, permission `analytics.read`.

- [ ] **Step 1: Create exact API fixtures and failing tests**

Create `backend/tests/test_dropshipping_forecasting_api.py`:

```python
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app, get_current_membership, get_current_user
from app.models import Organization, OrganizationMembership, Store, User
import app.api.dropshipping_analytics as analytics_api

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///./test_dropshipping_forecasting_api.db"
engine = create_engine(SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.remove("./test_dropshipping_forecasting_api.db")
    except FileNotFoundError:
        pass

@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()

@pytest.fixture()
def account(db):
    org = Organization(name="Forecast API Org", slug="forecast-api-org", plan="growth", subscription_status="active")
    db.add(org)
    db.flush()
    user = User(email="forecast-api@test.com", name="Forecast API Tester", external_auth_id="forecast-api-sub")
    db.add(user)
    db.flush()
    membership = OrganizationMembership(user_id=user.id, organization_id=org.id, role="manager", all_stores=True)
    db.add(membership)
    db.flush()
    store = Store(
        organization_id=org.id,
        name="Forecast API Store",
        slug="forecast-api-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(store)
    db.commit()
    return org, user, membership, store

@pytest.fixture()
def client(db, account):
    _, user, membership, _ = account
    original_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: iter([db])
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_membership] = lambda: membership
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


def stub_payload(store):
    return {
        "store_id": store.id,
        "currency": store.currency,
        "timezone": store.timezone,
        "generated_at": "2026-09-13T20:00:00+00:00",
        "forecast_anchor_date": "2026-09-12",
        "history": {
            "date_from": None,
            "date_to": None,
            "days": 0,
            "contribution_data_quality": {
                "status": "incomplete",
                "metric": "known_cost_contribution_forecast",
                "missing_components": [],
                "missing_reasons": {},
            },
        },
        "horizons": {"7d": {}, "30d": {}},
    }


def test_forecast_endpoint_returns_contract_and_ignores_dashboard_dates(client, account, monkeypatch):
    _, _, _, store = account
    calls = []

    def fake_get(db_arg, organization_id, store_arg):
        calls.append((organization_id, store_arg.id))
        return stub_payload(store_arg)

    monkeypatch.setattr(analytics_api, "get_store_forecast", fake_get)
    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/forecast?date_from=2020-01-01&date_to=2020-01-02"
    )
    assert response.status_code == 200
    assert response.json()["store_id"] == store.id
    assert calls == [(store.organization_id, store.id)]


def test_forecast_restricted_membership_cannot_read_unassigned_store(client, db, account):
    org, _, membership, assigned_store = account
    unassigned = Store(
        organization_id=org.id,
        name="Unassigned Forecast Store",
        slug="unassigned-forecast-store",
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        default_language="es",
    )
    db.add(unassigned)
    db.flush()
    membership.all_stores = False
    membership.stores.append(assigned_store)
    db.commit()
    response = client.get(f"/api/stores/{unassigned.id}/analytics/dropshipping/forecast")
    assert response.status_code == 403
    assert response.json()["detail"] == "Store access denied"


def test_forecast_invalid_timezone_is_422(client, db, account):
    _, _, _, store = account
    store.timezone = "Not/A_Zone"
    db.commit()
    response = client.get(f"/api/stores/{store.id}/analytics/dropshipping/forecast")
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_store_timezone"


def test_forecast_foreign_store_is_404(client, db):
    other = Organization(name="Other Forecast Org", slug="other-forecast-org", plan="growth", subscription_status="active")
    db.add(other)
    db.flush()
    foreign = Store(organization_id=other.id, name="Foreign", slug="foreign-forecast", country_code="MX", currency="MXN", timezone="America/Mexico_City", default_language="es")
    db.add(foreign)
    db.commit()
    response = client.get(f"/api/stores/{foreign.id}/analytics/dropshipping/forecast")
    assert response.status_code == 404


def test_forecast_inactive_store_is_404(client, db, account):
    _, _, _, store = account
    store.active = False
    db.commit()
    response = client.get(f"/api/stores/{store.id}/analytics/dropshipping/forecast")
    assert response.status_code == 404


def test_forecast_requires_analytics_read(client, db, account):
    _, _, membership, store = account
    membership.role = "operator"
    db.commit()
    response = client.get(f"/api/stores/{store.id}/analytics/dropshipping/forecast")
    assert response.status_code == 403
```

If the lambda generator override for `get_db` is rejected by FastAPI in this repository, replace it with the exact generator function below, not another pattern:

```python
def override_db():
    yield db
app.dependency_overrides[get_db] = override_db
```

- [ ] **Step 2: Verify RED**

```bash
cd backend
pytest -q tests/test_dropshipping_forecasting_api.py
```

Expected: route-not-found failures.

- [ ] **Step 3: Add the thin route and correct import alias**

In `backend/app/api/dropshipping_analytics.py` import:

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

The API test patches `app.api.dropshipping_analytics.get_store_forecast`, which is the symbol actually invoked by this route.

- [ ] **Step 4: Update strict route snapshot**

```bash
cd backend
python -m pytest tests/test_route_contract.py --update-snapshot
python -m pytest -q tests/test_route_contract.py
```

Review the snapshot diff. The only new pair is:

```json
["GET", "/api/stores/{store_id}/analytics/dropshipping/forecast"]
```

- [ ] **Step 5: Verify backend focus suite**

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

### Task 6: Add frontend contract and complete localized presentation helpers

**Files:**
- Modify: `frontend/src/services/analytics.ts`
- Create: `frontend/src/utils/dropshippingForecast.ts`
- Create: `frontend/tests/dropshippingForecast.test.ts`

**Interfaces:**
- Produces typed `getDropshippingForecast(storeId)` with no date args.
- Produces all es/en/pt-BR Forecasting copy used by the component.

- [ ] **Step 1: Write failing pure localization tests**

Create `frontend/tests/dropshippingForecast.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import {
  contributionForecastLabel,
  forecastConfidenceLabel,
  forecastCopy,
  forecastModelLabel,
  forecastUnavailableCopy,
} from "../src/utils/dropshippingForecast.ts";

test("confidence copy supports the three analytics locales", () => {
  assert.equal(forecastConfidenceLabel("low", "es"), "Baja confianza");
  assert.equal(forecastConfidenceLabel("medium", "en"), "Medium confidence");
  assert.equal(forecastConfidenceLabel("high", "pt-BR"), "Alta confiança");
});

test("partial contribution is never labeled as complete", () => {
  assert.equal(contributionForecastLabel("known_cost_contribution_forecast", "es"), "Contribución proyectada con costos conocidos");
  assert.equal(contributionForecastLabel("contribution_profit_forecast", "es"), "Contribución proyectada");
});

test("section copy is localized, not Spanish-hardcoded", () => {
  assert.equal(forecastCopy("en").title, "Store forecast");
  assert.equal(forecastCopy("pt-BR").partial, "Parcial");
  assert.equal(forecastCopy("es").deliveredOrders, "Pedidos entregados");
});

test("model and unavailable reason copy are stable", () => {
  assert.equal(forecastModelLabel("weekday_trend", "es"), "Tendencia + patrón semanal");
  assert.match(forecastUnavailableCopy("insufficient_history", "es"), /historial/i);
});
```

- [ ] **Step 2: Verify RED**

```bash
cd frontend
node --test tests/dropshippingForecast.test.ts
```

Expected: module-not-found.

- [ ] **Step 3: Implement pure localized copy**

Create `frontend/src/utils/dropshippingForecast.ts`:

```ts
export type ForecastLocale = "es" | "en" | "pt-BR";
export type ForecastConfidence = "low" | "medium" | "high";
export type ForecastModel = "recent_naive" | "weighted_moving_average" | "linear_trend" | "weekday_trend";
export type ContributionMetric = "contribution_profit_forecast" | "known_cost_contribution_forecast";

function locale(language: string): ForecastLocale {
  if (language.toLowerCase().startsWith("pt")) return "pt-BR";
  if (language.toLowerCase().startsWith("en")) return "en";
  return "es";
}

const COPY = {
  es: {
    title: "Pronóstico de tienda",
    unavailable: "Pronóstico temporalmente no disponible.",
    history: "Historial",
    days: "días",
    next7: "Próximos 7 días",
    next30: "Próximos 30 días",
    deliveredOrders: "Pedidos entregados",
    deliveredRevenue: "Ingresos entregados",
    probableRange: "Rango probable",
    partial: "Parcial",
    missing: "Faltan",
    backtests: "backtests",
  },
  en: {
    title: "Store forecast",
    unavailable: "Forecast is temporarily unavailable.",
    history: "History",
    days: "days",
    next7: "Next 7 days",
    next30: "Next 30 days",
    deliveredOrders: "Delivered orders",
    deliveredRevenue: "Delivered revenue",
    probableRange: "Probable range",
    partial: "Partial",
    missing: "Missing",
    backtests: "backtests",
  },
  "pt-BR": {
    title: "Previsão da loja",
    unavailable: "A previsão está temporariamente indisponível.",
    history: "Histórico",
    days: "dias",
    next7: "Próximos 7 dias",
    next30: "Próximos 30 dias",
    deliveredOrders: "Pedidos entregues",
    deliveredRevenue: "Receita entregue",
    probableRange: "Faixa provável",
    partial: "Parcial",
    missing: "Faltam",
    backtests: "backtests",
  },
} satisfies Record<ForecastLocale, Record<string, string>>;

const CONFIDENCE = {
  es: { low: "Baja confianza", medium: "Confianza media", high: "Alta confianza" },
  en: { low: "Low confidence", medium: "Medium confidence", high: "High confidence" },
  "pt-BR": { low: "Baixa confiança", medium: "Confiança média", high: "Alta confiança" },
} satisfies Record<ForecastLocale, Record<ForecastConfidence, string>>;

const MODEL = {
  es: { recent_naive: "Nivel reciente", weighted_moving_average: "Promedio ponderado", linear_trend: "Tendencia lineal", weekday_trend: "Tendencia + patrón semanal" },
  en: { recent_naive: "Recent level", weighted_moving_average: "Weighted average", linear_trend: "Linear trend", weekday_trend: "Trend + weekly pattern" },
  "pt-BR": { recent_naive: "Nível recente", weighted_moving_average: "Média ponderada", linear_trend: "Tendência linear", weekday_trend: "Tendência + padrão semanal" },
} satisfies Record<ForecastLocale, Record<ForecastModel, string>>;

const CONTRIBUTION = {
  es: { contribution_profit_forecast: "Contribución proyectada", known_cost_contribution_forecast: "Contribución proyectada con costos conocidos" },
  en: { contribution_profit_forecast: "Projected contribution", known_cost_contribution_forecast: "Projected contribution with known costs" },
  "pt-BR": { contribution_profit_forecast: "Contribuição projetada", known_cost_contribution_forecast: "Contribuição projetada com custos conhecidos" },
} satisfies Record<ForecastLocale, Record<ContributionMetric, string>>;

const UNAVAILABLE: Record<ForecastLocale, Record<string, string>> = {
  es: { insufficient_history: "Aún no hay suficiente historial para pronosticar.", backtest_unavailable: "No hay suficiente historial validable para este pronóstico.", non_finite_model_output: "No fue posible producir un pronóstico numérico seguro." },
  en: { insufficient_history: "There is not enough history to forecast yet.", backtest_unavailable: "There is not enough validated history for this forecast.", non_finite_model_output: "A safe numeric forecast could not be produced." },
  "pt-BR": { insufficient_history: "Ainda não há histórico suficiente para prever.", backtest_unavailable: "Não há histórico validável suficiente para esta previsão.", non_finite_model_output: "Não foi possível produzir uma previsão numérica segura." },
};

export function forecastCopy(language: string) { return COPY[locale(language)]; }
export function forecastConfidenceLabel(value: ForecastConfidence, language: string) { return CONFIDENCE[locale(language)][value]; }
export function forecastModelLabel(value: ForecastModel, language: string) { return MODEL[locale(language)][value]; }
export function contributionForecastLabel(value: ContributionMetric, language: string) { return CONTRIBUTION[locale(language)][value]; }
export function forecastUnavailableCopy(reason: string | null, language: string) {
  const copy = UNAVAILABLE[locale(language)];
  return copy[reason || ""] || copy.backtest_unavailable;
}
```

- [ ] **Step 4: Add exact DTOs and HTTP client to `analytics.ts`**

Add:

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

- [ ] **Step 5: Verify GREEN**

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
- Consumes Task 6 DTOs/copy.
- Produces a fully localized independent forecast section.

- [ ] **Step 1: Write failing seventh-section tests**

Update `frontend/tests/dropshippingAnalyticsState.test.ts` so its first assertion is:

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
```

Add:

```ts
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
  const results = DROPSHIPPING_ANALYTICS_SECTIONS.map((section) => ({ status: "rejected" as const, reason: section }));
  assert.equal(allDropshippingSectionsFailed(getFailedDropshippingSections(results)), true);
});
```

Update every older six-element result fixture in this file by appending a seventh fulfilled forecast result unless that test intentionally rejects forecast.

- [ ] **Step 2: Verify RED**

```bash
cd frontend
node --test tests/dropshippingAnalyticsState.test.ts
```

Expected: section-array mismatch.

- [ ] **Step 3: Register forecast and integrate the seventh fetch**

Set `DROPSHIPPING_ANALYTICS_SECTIONS` to the exact seven-element array above.

In `DropshippingOverview.tsx`:

```ts
import DropshippingForecast from "./DropshippingForecast";
```

Add `getDropshippingForecast` and `DropshippingForecastResponse` to the existing analytics service import. Extend `DashboardData`:

```ts
forecast: DropshippingForecastResponse | null;
```

Extend labels:

```ts
forecast: "pronóstico",
```

Use this request order:

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

Map `forecast: settledValue(results[6])`. Destructure `forecast` from data. Render immediately after Unit Economics:

```tsx
<DropshippingForecast
  data={forecast}
  unavailable={unavailableSections.includes("forecast")}
  language={i18n.resolvedLanguage || i18n.language || "es"}
  currency={effectiveCurrency}
/>
```

- [ ] **Step 4: Implement the fully localized component**

Create `frontend/src/components/DropshippingForecast.tsx`:

```tsx
import { AlertTriangle, CalendarRange, TrendingUp } from "lucide-react";
import type { DropshippingForecastMetric, DropshippingForecastResponse } from "../services/analytics";
import {
  contributionForecastLabel,
  forecastConfidenceLabel,
  forecastCopy,
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

function MetricCard({ label, metric, language, formatValue }: {
  label: string;
  metric: DropshippingForecastMetric;
  language: string;
  formatValue: (value: number) => string;
}) {
  const copy = forecastCopy(language);
  if (metric.status === "unavailable" || metric.estimate === null) {
    return <div className="forecast-metric is-unavailable"><span>{label}</span><strong>—</strong><small>{forecastUnavailableCopy(metric.reason, language)}</small></div>;
  }
  const lower = metric.lower_bound === null ? metric.estimate : metric.lower_bound;
  const upper = metric.upper_bound === null ? metric.estimate : metric.upper_bound;
  return (
    <div className="forecast-metric">
      <span>{label}</span>
      <strong>{formatValue(metric.estimate)}</strong>
      <small>{copy.probableRange}: {formatValue(lower)} – {formatValue(upper)}</small>
      <div className={`forecast-confidence is-${metric.confidence}`}>{forecastConfidenceLabel(metric.confidence, language)}</div>
      {metric.model && <small>{forecastModelLabel(metric.model, language)} · {metric.quality.backtest_windows} {copy.backtests}</small>}
    </div>
  );
}

export default function DropshippingForecast({ data, unavailable, language, currency }: Props) {
  const copy = forecastCopy(language);
  const locale = language.toLowerCase().startsWith("pt") ? "pt-BR" : language.toLowerCase().startsWith("en") ? "en-US" : "es-CO";
  const formatMoney = (value: number) => new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
  const formatOrders = (value: number) => new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(Math.round(value));

  if (unavailable) {
    return <section className="dropshipping-forecast"><div className="forecast-empty"><AlertTriangle size={17} /><span>{copy.unavailable}</span></div></section>;
  }
  if (!data) return null;

  return (
    <section className="dropshipping-forecast">
      <div className="forecast-header">
        <div><span className="forecast-kicker">FORECASTING V2.3</span><h3><TrendingUp size={18} /> {copy.title}</h3></div>
        <small><CalendarRange size={14} /> {copy.history}: {data.history.days} {copy.days}</small>
      </div>
      <div className="dropshipping-forecast-horizons">
        {(["7d", "30d"] as const).map((key) => {
          const horizon = data.horizons[key];
          const partial = horizon.contribution.data_quality.status === "incomplete";
          return (
            <div className="forecast-horizon" key={key}>
              <h4>{key === "7d" ? copy.next7 : copy.next30}</h4>
              <MetricCard label={copy.deliveredOrders} metric={horizon.delivered_orders} language={language} formatValue={formatOrders} />
              <MetricCard label={copy.deliveredRevenue} metric={horizon.delivered_revenue} language={language} formatValue={formatMoney} />
              <div className={partial ? "forecast-partial" : ""}>
                {partial && <span className="forecast-partial-badge">{copy.partial}</span>}
                <MetricCard label={contributionForecastLabel(horizon.contribution.metric, language)} metric={horizon.contribution} language={language} formatValue={formatMoney} />
                {partial && horizon.contribution.data_quality.missing_components.length > 0 && (
                  <small>{copy.missing}: {horizon.contribution.data_quality.missing_components.join(", ")}</small>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Add CSS using the repository's existing theme variables**

Create `frontend/src/dropshipping-forecast.css`:

```css
.dropshipping-forecast {
  margin-bottom: 18px;
  padding: 20px;
  border: 1px solid var(--border-color, rgba(148, 163, 184, 0.18));
  border-radius: 18px;
  background: var(--surface-primary, rgba(15, 23, 42, 0.55));
}
.forecast-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 14px; }
.forecast-header h3 { display: flex; gap: 8px; align-items: center; margin: 5px 0 0; }
.forecast-header small { display: inline-flex; align-items: center; gap: 6px; color: var(--text-muted, #94a3b8); }
.forecast-kicker { color: #a5b4fc; font-size: .68rem; font-weight: 850; letter-spacing: .12em; }
.dropshipping-forecast-horizons { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.forecast-horizon { border: 1px solid var(--border-color, rgba(148, 163, 184, 0.14)); border-radius: 14px; padding: 16px; background: rgba(148, 163, 184, 0.04); }
.forecast-horizon h4 { margin: 0 0 6px; color: var(--text-primary, #e5e7eb); }
.forecast-metric { display: grid; gap: 5px; padding: 12px 0; border-bottom: 1px solid var(--border-color, rgba(148, 163, 184, 0.12)); }
.forecast-metric > span, .forecast-metric small { color: var(--text-muted, #94a3b8); }
.forecast-metric strong { color: var(--text-primary, #e5e7eb); font-size: 1.1rem; }
.forecast-confidence, .forecast-partial-badge { width: fit-content; border-radius: 999px; padding: 4px 8px; font-size: .68rem; font-weight: 800; }
.forecast-confidence.is-high { color: #86efac; background: rgba(22, 101, 52, .18); }
.forecast-confidence.is-medium { color: #c4b5fd; background: rgba(99, 102, 241, .14); }
.forecast-confidence.is-low, .forecast-partial-badge { color: #fcd34d; background: rgba(120, 53, 15, .18); }
.forecast-partial { margin-top: 8px; }
.forecast-partial > small { display: block; margin-top: 6px; color: #fcd34d; }
.forecast-empty { display: flex; align-items: center; gap: 8px; color: var(--text-secondary, #cbd5e1); }
[data-theme="light"] .forecast-kicker { color: #4f46e5; }
[data-theme="light"] .forecast-confidence.is-high { color: #15803d; background: #f0fdf4; }
[data-theme="light"] .forecast-confidence.is-low,
[data-theme="light"] .forecast-partial-badge { color: #92400e; background: #fffbeb; }
@media (max-width: 760px) {
  .forecast-header { flex-direction: column; }
  .dropshipping-forecast-horizons { grid-template-columns: 1fr; }
}
```

- [ ] **Step 6: Verify frontend GREEN**

```bash
cd frontend
npm test
npm run lint
npm run build
```

Expected: PASS and no new lint errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/DropshippingForecast.tsx frontend/src/dropshipping-forecast.css frontend/src/components/DropshippingOverview.tsx frontend/src/utils/dropshippingAnalyticsState.ts frontend/tests/dropshippingAnalyticsState.test.ts
git commit -m "feat: render store forecasting in analytics"
```

---

### Task 8: Harden bounded access and run full regressions

**Files:**
- Modify: `backend/tests/test_dropshipping_forecasting.py`
- Modify V2.3 production files only if this new test exposes a defect.

**Interfaces:** no new public interface.

- [ ] **Step 1: Add an exact one-Meta/one-item-preload regression**

Append to `backend/tests/test_dropshipping_forecasting.py`:

```python
def test_forecast_uses_one_meta_resolution_and_one_item_preload(db, store, monkeypatch):
    seed_complete_days(db, store, 60)
    meta_calls = 0
    item_calls = 0
    original_load_items = forecasting._load_items

    def fake_meta(*args, **kwargs):
        nonlocal meta_calls
        meta_calls += 1
        return {
            "amount": Decimal("0"),
            "source": "meta_ads",
            "status": "actual",
            "reason": None,
            "metadata": {},
        }

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

- [ ] **Step 2: Run all dropshipping regressions**

```bash
cd backend
pytest -q tests/test_dropshipping_analytics.py tests/test_dropshipping_decision_intelligence.py tests/test_dropshipping_decision_intelligence_api.py tests/test_dropshipping_unit_economics.py tests/test_dropshipping_unit_economics_api.py tests/test_dropshipping_unit_economics_edge_cases.py tests/test_unit_economics_meta.py tests/test_dropshipping_forecast_math.py tests/test_dropshipping_forecasting.py tests/test_dropshipping_forecasting_api.py tests/test_route_contract.py
```

Expected: PASS.

- [ ] **Step 3: Run CI-equivalent backend and frontend validation**

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

Expected: every command PASS.

- [ ] **Step 4: Commit hardening test and any minimal fix it required**

```bash
git add backend/tests/test_dropshipping_forecasting.py backend/app/services/dropshipping_forecasting.py
git commit -m "test: harden dropshipping forecasting v2.3"
```

If `backend/app/services/dropshipping_forecasting.py` did not change, omit it from `git add`. Do not create an empty commit.

---

### Task 9: Final PR and merge gate

**Files:** no planned source edits.

**Interfaces:** final integration gate only.

- [ ] **Step 1: Verify branch scope**

```bash
git fetch origin
git diff --name-only origin/main...HEAD
git diff --stat origin/main...HEAD
```

Expected scope: V2.3 spec/plan, forecast services/tests, narrow Unit Economics reuse refactor, one analytics route/snapshot change, forecast frontend files/integration. No migration, persistence model, unrelated subsystem edit, or ML dependency.

- [ ] **Step 2: Verify the approved spec acceptance criteria**

Read `docs/superpowers/specs/2026-09-13-dropshipping-forecasting-v2-3-design.md` and explicitly verify: 7d+30d, store-local cutoff, adaptive deterministic selection, probable ranges, confidence evidence, complete/partial contribution naming, one Meta resolution, no inferred missing cost, tenant/store isolation, no date-filter dependency, seventh-section isolation, no NaN/Infinity, no heavyweight ML dependency.

- [ ] **Step 3: Open PR**

Title:

```text
feat: add dropshipping store forecasting v2.3
```

PR body includes the exact focused/full validation commands from Tasks 5–8 and their observed results.

- [ ] **Step 4: Require fresh GitHub Actions on the exact final head**

The `Validate Pull Request` run must show success for Detect changed scopes, backend shard 0, backend shard 1, frontend validation, and the final aggregator. Do not merge based on an older SHA or cancelled run.

- [ ] **Step 5: Fix any failure through systematic debugging**

If CI fails, load `superpowers:systematic-debugging`, use the failing job logs to identify the root cause, patch the feature branch, run the narrow test first, then full relevant validation, and require another fresh all-green run.

- [ ] **Step 6: Squash merge and verify `main`**

After final-head CI is green, squash merge. Verify PR `merged == true`, record the returned merge commit SHA, and confirm `main` HEAD equals that commit before beginning the next feature.

---

## Definition of Done

- [ ] Current partial store-local day is excluded.
- [ ] 7+ observations can produce deterministic 7d/30d order and revenue forecasts.
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
- [ ] es/en/pt-BR presentation tests pass.
- [ ] Backend Ruff + full pytest pass.
- [ ] Frontend lint + tests + build pass.
- [ ] Exact final PR head is fully green in GitHub Actions before merge.
