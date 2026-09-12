# Dropshipping Analytics V2.1 — Decision Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, evidence-backed decision insights to Dropshipping Analytics without weakening existing analytics resilience or tenant/store isolation.

**Architecture:** A new backend decision-intelligence service consumes the existing product analytics metrics, evaluates deterministic rules, and exposes them through a new additive `/insights` endpoint. The frontend adds a typed client, a pure copy/presentation helper, a dedicated insights section, and an explicit controlled selection contract into Product Analytics V2.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React 19, TypeScript 6, Vite 8, node:test, react-i18next, existing Diaglob analytics services and CSS conventions.

**Spec:** `docs/superpowers/specs/2026-09-11-dropshipping-decision-intelligence-design.md`

## Global Constraints

- No database migration.
- No new background job.
- No LLM-generated diagnosis or recommendation.
- Preserve all existing dropshipping endpoints and response fields.
- Require `analytics.read` and strict `membership.organization_id` + `store_id` isolation.
- Reuse existing date parsing semantics; date-only `date_to` remains inclusive at the API boundary and exclusive internally.
- Suppress margin-dependent insights whenever `profitability_complete` is false.
- Stock runway exists only when both date bounds are present and define a positive range.
- Decision Intelligence failure must not make overview, profitability, products, or funnel unavailable.
- Frontend copy must be complete in ES, EN and PT-BR; raw backend keys must never be visible.
- No automatic price, stock, campaign, or fulfillment mutations.
- Evaluate all products with activity before applying the insight `limit`; do not reuse the existing API's 200-product cap as an evaluation cap.

---

## File Structure

### Backend
- Create `backend/app/services/dropshipping_decision_intelligence.py`: rule evaluation, runway, conflict suppression, deterministic ordering, summary.
- Modify `backend/app/services/dropshipping_analytics.py`: allow internal callers to request all product metrics with `limit=None` while preserving current API behavior.
- Modify `backend/app/api/dropshipping_analytics.py`: expose `GET /api/stores/{store_id}/analytics/dropshipping/insights` using existing guards.
- Create `backend/tests/test_dropshipping_decision_intelligence.py`: rule-engine and endpoint regressions.
- Modify `backend/tests/test_product_analytics_v2.py`: characterize `limit=None` as unbounded internal product evaluation.

### Frontend
- Modify `frontend/src/services/analytics.ts`: typed insight contract and API client.
- Create `frontend/src/utils/dropshippingDecisionInsights.ts`: locale/copy/evidence/severity/selection helpers.
- Create `frontend/tests/dropshippingDecisionInsights.test.ts`: pure presentation and selection tests.
- Create `frontend/src/components/DropshippingDecisionInsights.tsx`: insight section UI.
- Modify `frontend/src/components/DropshippingOverview.tsx`: independent insights load + parent-owned selected product state.
- Modify `frontend/src/components/ProductPerformanceAnalytics.tsx`: controlled product selection.
- Modify `frontend/src/utils/dropshippingAnalyticsState.ts`: add `insights` to partial-failure model.
- Modify `frontend/tests/dropshippingAnalyticsState.test.ts`: five-section resilience contract.
- Create `frontend/src/dropshipping-decision-insights.css`: responsive styles; import it directly from the new component.

---

### Task 1: Remove the Product Evaluation Cap for Internal Analytics

**Files:**
- Modify: `backend/app/services/dropshipping_analytics.py`
- Modify: `backend/tests/test_product_analytics_v2.py`

**Interfaces:**
- Change only the internal Python signature:
  ```python
  def get_product_profitability(
      db: Session,
      organization_id: int,
      store_id: int | None,
      date_from: Any,
      date_to: Any,
      limit: int | None = 50,
  ) -> list[dict[str, Any]]
  ```
- `limit=None` returns every evaluated product; integer limits preserve current slicing behavior.
- Existing API continues passing its validated integer limit and therefore keeps its public behavior unchanged.

- [ ] **Step 1: Write the failing characterization test**

Add a test that creates three products with delivered orders, then asserts:

```python
limited = get_product_profitability(db, org.id, store.id, None, None, limit=2)
unbounded = get_product_profitability(db, org.id, store.id, None, None, limit=None)

assert len(limited) == 2
assert len(unbounded) == 3
```

- [ ] **Step 2: Run the test and verify RED**

```bash
cd backend
pytest -q tests/test_product_analytics_v2.py -k unbounded
```

Expected: FAIL because the current implementation slices with `products[:limit]` and does not accept `None`.

- [ ] **Step 3: Implement the compatible internal behavior**

Replace the final return with:

```python
if limit is None:
    return products
return products[:limit]
```

Do not change sorting, SQL aggregation, endpoint defaults, or public response fields.

- [ ] **Step 4: Verify GREEN**

```bash
cd backend
pytest -q tests/test_product_analytics_v2.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dropshipping_analytics.py backend/tests/test_product_analytics_v2.py
git commit -m "refactor: allow unbounded internal product analytics"
```

---

### Task 2: Backend Decision Rule Engine

**Files:**
- Create: `backend/app/services/dropshipping_decision_intelligence.py`
- Create: `backend/tests/test_dropshipping_decision_intelligence.py`

**Interfaces:**
- Consumes `get_product_profitability(..., limit=None)` from Task 1.
- Produces this exact public service function:
  ```python
  def get_dropshipping_decision_insights(
      db: Session,
      organization_id: int,
      store_id: int,
      currency: str,
      date_from: datetime | None,
      date_to: datetime | None,
      limit: int = 20,
  ) -> dict[str, Any]
  ```
- Top-level keys: `generated_at`, `date_from`, `date_to`, `currency`, `summary`, `insights`.

- [ ] **Step 1: Build deterministic test fixtures**

In the new test file, define local helpers named `add_product`, `add_variant`, and `add_order_item`. They must insert `Product`, `ProductVariant`, `Order`, and `OrderItem` rows with explicit lifecycle status, price, cost, quantity, timestamp, inventory, organization, and store. Use the same model fields already exercised by `test_product_analytics_v2.py`; keep every scenario in one store unless the test explicitly validates isolation.

- [ ] **Step 2: Write RED tests for every approved rule**

Create separate tests with these exact inputs and expected outcomes:

| Case | Fixture | Expected |
| --- | --- | --- |
| empty store | no orders | `summary.products_evaluated == 0`, `insights == []` |
| incomplete costs | delivered product with at least one `unit_cost=None` | `cost_incomplete`; no `negative_margin`, `low_margin`, `winner`, `opportunity` |
| negative margin | complete costs; delivered revenue below COGS | `negative_margin`, `critical`, action `review_price_and_cost` |
| low margin | 3+ delivered; complete costs; margin 0–19.9% | `low_margin`, `warning` |
| delivery sample guard | 4 shipped-equivalent orders at <60% delivery | no `delivery_risk` |
| delivery threshold | 5 shipped-equivalent orders at <60% delivery | `delivery_risk` |
| cancellation threshold | 5 total orders and cancellation rate >25% | `cancellation_risk` |
| return threshold | 5 shipped-equivalent orders and return rate >15% | `return_risk` |
| stockout | inventory 0 and delivered units >0 | `stockout`; no `stock_runway` |
| runway critical | bounded 10-day range; 10 delivered units; inventory 2 | runway 2.0 days, `critical` |
| runway warning | bounded 10-day range; 10 delivered units; inventory 5 | runway 5.0 days, `warning` |
| runway no alert | bounded 10-day range; 10 delivered units; inventory 7 | no `stock_runway` |
| runway sample guard | bounded range; only 2 delivered units | no `stock_runway` |
| unbounded range | same profitable product with no dates | other rules still evaluate; no `stock_runway` |
| revenue concentration | at least 2 revenue-producing products; one >=50% share | `revenue_concentration` |
| profit concentration | at least 2 positive-profit products; one >=50% share | `profit_concentration` |
| winner | complete costs; total>=5; delivered>=3; margin>=30%; delivery>=70%; cancel<=20%; returns null or <=10%; positive profit | `winner`, `positive` |
| opportunity | complete costs; total>=5; delivered>=2; same quality gates; revenue share<15%; positive profit; not winner | `opportunity`, severity `opportunity` |
| suppression | product qualifies for winner conditions | no `opportunity` for that product |
| ordering | at least one critical, warning, opportunity, positive | order is critical → warning → opportunity → positive |
| limit | create >2 insights | evaluate all first, then return exactly first 2 sorted insights |
| serialization | all evidence numeric values finite | no `NaN` or `Infinity` |

For stable identifiers assert a product-specific insight ID equals `f"{type}:{product_id}"`.

- [ ] **Step 3: Run RED**

```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py
```

Expected: collection/import failure because the service module does not exist.

- [ ] **Step 4: Implement the rule engine**

Create exact ordering constants:

```python
SEVERITY_RANK = {
    "critical": 0,
    "warning": 1,
    "opportunity": 2,
    "positive": 3,
}

TYPE_PRIORITY = {
    "negative_margin": 0,
    "stockout": 1,
    "stock_runway": 2,
    "cost_incomplete": 3,
    "delivery_risk": 4,
    "cancellation_risk": 5,
    "return_risk": 6,
    "low_margin": 7,
    "revenue_concentration": 8,
    "profit_concentration": 9,
    "opportunity": 10,
    "winner": 11,
}
```

Use `datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")` for `generated_at`.

Build every product insight with:

```python
{
    "id": f"{type_}:{product_id}",
    "type": type_,
    "severity": severity,
    "product_id": product_id,
    "product_title": product_title,
    "title_key": title_key,
    "reason_key": reason_key,
    "action_key": action_key,
    "evidence": evidence,
}
```

Calculate bounded range velocity only when both dates are present and `(date_to - date_from).total_seconds() > 0`:

```python
period_days = (date_to - date_from).total_seconds() / 86400
units_per_day = units_delivered / period_days
stock_runway_days = inventory_quantity / units_per_day
```

Round `units_per_day` and `stock_runway_days` to one decimal in evidence. Implement the thresholds and suppressions exactly as written in the approved spec. Sort all insights before slicing `insights[:limit]`. Summary counts are calculated from the limited response list, while `products_evaluated` is the full evaluated product count.

- [ ] **Step 5: Verify GREEN**

```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py tests/test_product_analytics_v2.py tests/test_dropshipping_analytics.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/dropshipping_decision_intelligence.py backend/tests/test_dropshipping_decision_intelligence.py
git commit -m "feat: add dropshipping decision intelligence rules"
```

---

### Task 3: Insights API Contract and Isolation

**Files:**
- Modify: `backend/app/api/dropshipping_analytics.py`
- Modify: `backend/tests/test_dropshipping_decision_intelligence.py`

**Interfaces:**
- Produces `GET /api/stores/{store_id}/analytics/dropshipping/insights`.
- Query: `date_from`, `date_to`, `limit=20`, with `1 <= limit <= 50`.

- [ ] **Step 1: Add RED endpoint tests**

Cover these exact contracts:

```python
assert _parse_date("2026-09-11", inclusive_end=True) == datetime(2026, 9, 12)
```

Add endpoint tests using the repository's existing authenticated client/dependency override pattern and assert:
- authorized member with `analytics.read` receives 200;
- foreign or inactive store returns 404;
- missing permission returns the existing authorization failure used elsewhere in the app;
- `date_from=2026-09-01&date_to=2026-09-11` produces response `date_to == "2026-09-12T00:00:00"`;
- `limit=1` and `limit=50` are accepted;
- `limit=0` and `limit=51` return 422.

- [ ] **Step 2: Run RED**

```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py -k endpoint
```

Expected: FAIL with 404/no route until the endpoint exists.

- [ ] **Step 3: Add the endpoint using existing guards**

Add exactly this handler shape in `backend/app/api/dropshipping_analytics.py`:

```python
@router.get("/api/stores/{store_id}/analytics/dropshipping/insights")
def dropshipping_insights(
    store_id: int,
    membership=Depends(require_permission("analytics.read")),
    db: Session = Depends(get_db),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
):
    store = _validate_store(store_id, membership, db)
    parsed_from, parsed_to = _parse_range(date_from, date_to)
    return get_dropshipping_decision_insights(
        db,
        membership.organization_id,
        store_id,
        store.currency,
        parsed_from,
        parsed_to,
        limit,
    )
```

Import only the new service function. Do not add a router, permission, store query, or date parser.

- [ ] **Step 4: Verify endpoint + analytics regressions**

```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py tests/test_dropshipping_analytics.py tests/test_product_analytics_v2.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/dropshipping_analytics.py backend/tests/test_dropshipping_decision_intelligence.py
git commit -m "feat: expose dropshipping decision insights api"
```

---

### Task 4: Frontend Contract, Localization, and Presentation Model

**Files:**
- Modify: `frontend/src/services/analytics.ts`
- Create: `frontend/src/utils/dropshippingDecisionInsights.ts`
- Create: `frontend/tests/dropshippingDecisionInsights.test.ts`

**Interfaces:**
- Add unions for all approved insight `severity` and `type` values.
- Add `DropshippingInsight`, `DropshippingDecisionInsightsSummary`, `DropshippingDecisionInsightsResponse`.
- Add `getDropshippingDecisionInsights(storeId, dateFrom?, dateTo?, limit=20)`.
- Add pure functions:
  ```ts
  normalizeDecisionInsightLocale(language: string): "es" | "en" | "pt-BR"
  getDecisionInsightPresentation(insight: DropshippingInsight, language: string): DecisionInsightPresentation
  selectedProductIdFromInsight(insight: DropshippingInsight): number | null
  nextSelectedProductId(currentProductId: number | null, requestedProductId: number): number | null
  ```

- [ ] **Step 1: Write RED node:test coverage**

Create sample insight objects with complete required fields. Test:

```ts
assert.equal(normalizeDecisionInsightLocale("es-CO"), "es");
assert.equal(normalizeDecisionInsightLocale("en-US"), "en");
assert.equal(normalizeDecisionInsightLocale("pt-BR"), "pt-BR");
assert.equal(normalizeDecisionInsightLocale("fr-FR"), "es");
```

For each approved `title_key`, `reason_key`, and `action_key`, call `getDecisionInsightPresentation()` in ES, EN, and PT-BR and assert the returned strings are non-empty and do not equal the raw key. Include explicit assertions for stock runway:

```ts
const presentation = getDecisionInsightPresentation(stockInsight, "es");
assert.equal(presentation.title, "Stock crítico");
assert.equal(presentation.action, "Reponer inventario");
assert.equal(selectedProductIdFromInsight(stockInsight), 123);
assert.equal(nextSelectedProductId(null, 123), 123);
assert.equal(nextSelectedProductId(123, 123), null);
```

- [ ] **Step 2: Run RED**

```bash
cd frontend
node --test tests/dropshippingDecisionInsights.test.ts
```

Expected: FAIL because the utility module does not exist.

- [ ] **Step 3: Add typed API contract/client**

In `frontend/src/services/analytics.ts`, type `evidence` as `Record<string, number | string | null>` and add:

```ts
export async function getDropshippingDecisionInsights(
  storeId: number,
  dateFrom?: string,
  dateTo?: string,
  limit = 20,
) {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  params.set("limit", String(limit));
  const response = await api.get<DropshippingDecisionInsightsResponse>(
    `/api/stores/${storeId}/analytics/dropshipping/insights?${params.toString()}`,
  );
  return response.data;
}
```

Do not change the existing private `buildParams()` or any existing client contract.

- [ ] **Step 4: Implement pure copy/presentation helper**

Define exhaustive ES/EN/PT-BR maps for every approved backend title/reason/action key. `getDecisionInsightPresentation()` returns localized `title`, `reason`, `action`, `severityLabel`, and evidence display items. Unknown language falls back to Spanish. Unknown backend keys throw a descriptive error in development/test instead of leaking raw keys to the UI.

- [ ] **Step 5: Verify GREEN**

```bash
cd frontend
node --test tests/dropshippingDecisionInsights.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/services/analytics.ts frontend/src/utils/dropshippingDecisionInsights.ts frontend/tests/dropshippingDecisionInsights.test.ts
git commit -m "feat: add decision insight frontend contract"
```

---

### Task 5: Decision Insights UI, Failure Isolation, and Product Drill-Down

**Files:**
- Create: `frontend/src/components/DropshippingDecisionInsights.tsx`
- Create: `frontend/src/dropshipping-decision-insights.css`
- Modify: `frontend/src/components/DropshippingOverview.tsx`
- Modify: `frontend/src/components/ProductPerformanceAnalytics.tsx`
- Modify: `frontend/src/utils/dropshippingAnalyticsState.ts`
- Modify: `frontend/tests/dropshippingAnalyticsState.test.ts`
- Modify: `frontend/tests/dropshippingDecisionInsights.test.ts`

**Interfaces:**
- New component props:
  ```ts
  interface Props {
    response: DropshippingDecisionInsightsResponse | null;
    unavailable: boolean;
    language: string;
    currency: string;
    onSelectProduct: (productId: number) => void;
  }
  ```
- Change `ProductPerformanceAnalytics` props to add:
  ```ts
  selectedProductId: number | null;
  onSelectedProductChange: (productId: number | null) => void;
  ```
- `DropshippingOverview` becomes the single owner of selected product state.

- [ ] **Step 1: Extend partial-failure tests RED-first**

Update tests to expect this exact ordered section tuple:

```ts
[
  "overview",
  "profitability",
  "products",
  "orders",
  "insights",
]
```

Assert an insights-only rejection returns `failedSections === ["insights"]` and `allDropshippingSectionsFailed(failedSections) === false`. Assert five rejections return `true`.

- [ ] **Step 2: Run RED**

```bash
cd frontend
node --test tests/dropshippingAnalyticsState.test.ts
```

Expected: FAIL because the state model currently knows four sections.

- [ ] **Step 3: Add `insights` to the state model and dashboard loader**

Add insights as the fifth `Promise.allSettled` request in `DropshippingOverview`. Extend `DashboardData` with `insights: DropshippingDecisionInsightsResponse | null`. Page-level error remains reserved for failure of all five sections. An insights-only failure renders existing analytics plus an unavailable insights section.

- [ ] **Step 4: Make Product Analytics V2 controlled**

In `DropshippingOverview` create:

```ts
const [selectedProductId, setSelectedProductId] = useState<number | null>(null);
```

Reset it to `null` whenever `storeId`, `dateFrom`, or `dateTo` changes.

Remove the internal selected-product state from `ProductPerformanceAnalytics`. Row toggle must call:

```ts
onSelectedProductChange(
  selectedProductId === product.product_id ? null : product.product_id,
);
```

The detail close button calls `onSelectedProductChange(null)`. Detail fetching remains keyed by `selectedProductId`, store, and date range.

- [ ] **Step 5: Implement `DropshippingDecisionInsights`**

Import `../dropshipping-decision-insights.css` directly from the new component. Render the section before the KPI grid. Use only `getDecisionInsightPresentation()` for human copy. Product cards render a real button that calls `onSelectProduct(productId)`. Do not query the DOM or synthesize clicks.

Behavior:
- `unavailable=true` → localized temporary-unavailable state;
- available + `insights.length === 0` → localized healthy/empty state;
- otherwise render cards in backend-provided order;
- each card shows localized title, reason, 1–3 evidence items, action, product title, severity label;
- product-specific cards expose localized `View product` action.

- [ ] **Step 6: Add focused responsive CSS**

Use only classes prefixed `decision-insights-`. Reuse existing CSS variables/tokens. Desktop may use a multi-column card grid; mobile collapses to one column. Do not edit unrelated analytics selectors.

- [ ] **Step 7: Verify frontend**

```bash
cd frontend
npm test
npm run lint
npm run build
```

Expected: all tests PASS, lint 0 errors, production build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/DropshippingDecisionInsights.tsx frontend/src/dropshipping-decision-insights.css frontend/src/components/DropshippingOverview.tsx frontend/src/components/ProductPerformanceAnalytics.tsx frontend/src/utils/dropshippingAnalyticsState.ts frontend/tests/dropshippingAnalyticsState.test.ts frontend/tests/dropshippingDecisionInsights.test.ts
git commit -m "feat: surface dropshipping decision intelligence"
```

---

### Task 6: Final Verification, PR, and Merge Gate

**Files:**
- Review only the files changed in Tasks 1–5.
- Add no new feature behavior in this task.

- [ ] **Step 1: Run focused backend regression**

```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py tests/test_dropshipping_analytics.py tests/test_product_analytics_v2.py
```

Expected: PASS.

- [ ] **Step 2: Run the exact repository Ruff command**

```bash
cd backend
ruff check app/ tests/ tools/
```

Expected: 0 errors.

- [ ] **Step 3: Run full frontend validation**

```bash
cd frontend
npm test
npm run lint
npm run build
```

Expected: tests PASS, lint 0 errors, build succeeds.

- [ ] **Step 4: Review final diff against approved scope**

Confirm all of these are true:
- no migration or model change;
- no existing analytics endpoint/field removed or renamed;
- no LLM/provider call;
- no mutation endpoint or automated operational action;
- backend returns machine keys/evidence, not localized prose;
- endpoint uses `_validate_store`, `_parse_range`, and `analytics.read`;
- all products are evaluated before the insight result limit is applied;
- incomplete costs suppress margin-dependent claims;
- insights failure remains isolated;
- product drill-down uses explicit React state, not DOM coupling.

- [ ] **Step 5: Open a draft PR**

Use title:

```text
feat: add dropshipping decision intelligence
```

PR body must record the approved spec path, this plan path, RED/GREEN evidence, focused backend results, frontend test/lint/build results, and final head SHA.

- [ ] **Step 6: Run and verify normal repository CI on the exact final head**

Require `Validate Pull Request` to finish with:
- Detect changed scopes: success;
- Backend validation shard 0: success;
- Backend validation shard 1: success;
- Ruff step on shard 0: success;
- Frontend validation: success;
- Backend + Frontend validation gate: success.

A pending, failed, cancelled, or unexpectedly skipped required job blocks readiness and merge.

- [ ] **Step 7: Mark ready and squash merge with head protection**

After CI is green, mark the PR ready. Squash merge using `expected_head_sha` equal to the exact verified PR head. Refetch `main` after merge and record the resulting commit SHA.
