# Dropshipping Analytics V2.1 — Decision Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic, evidence-backed decision insights to Dropshipping Analytics without weakening existing analytics resilience or tenant/store isolation.

**Architecture:** Add a focused backend decision-intelligence service that consumes existing product analytics metrics and emits structured insight objects under a new `/insights` endpoint. Add a typed frontend client, a pure presentation/selection helper, and a dedicated insight component near the top of the existing dropshipping dashboard; keep Product Analytics V2 as the drill-down surface through an explicit controlled product-selection contract.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React 19, TypeScript 6, Vite 8, node:test, react-i18next, existing Diaglob analytics services and CSS conventions.

**Spec:** `docs/superpowers/specs/2026-09-11-dropshipping-decision-intelligence-design.md`

## Global Constraints

- No database migration.
- No new background job.
- No LLM-generated diagnosis or recommendation.
- Preserve existing dropshipping endpoints and response fields.
- Require `analytics.read` and strict `membership.organization_id` + `store_id` isolation.
- Reuse existing date parsing semantics; date-only `date_to` remains inclusive at the API boundary and exclusive internally.
- Suppress margin-dependent insights whenever `profitability_complete` is false.
- Stock runway exists only when both date bounds are present and define a positive range.
- New insight failure must not make existing overview, profitability, products, or funnel unavailable.
- Frontend copy must be complete in ES, EN and PT-BR; raw backend keys must never be shown to users.
- No automatic price, stock, campaign, or fulfillment mutations.

---

## File Structure

### Backend
- Create `backend/app/services/dropshipping_decision_intelligence.py`: rule engine, runway calculation, conflict suppression, deterministic ordering, summary construction.
- Modify `backend/app/api/dropshipping_analytics.py`: expose `GET /api/stores/{store_id}/analytics/dropshipping/insights` using existing `_validate_store` and `_parse_range`.
- Create `backend/tests/test_dropshipping_decision_intelligence.py`: rule-engine and API regression coverage.

### Frontend
- Modify `frontend/src/services/analytics.ts`: typed insight contract and `getDropshippingDecisionInsights()` client.
- Create `frontend/src/utils/dropshippingDecisionInsights.ts`: locale normalization, copy maps, evidence formatting metadata, severity metadata, product-selection helper.
- Create `frontend/tests/dropshippingDecisionInsights.test.ts`: pure frontend contract tests runnable with existing `node --test` setup.
- Create `frontend/src/components/DropshippingDecisionInsights.tsx`: section UI only; no rule logic.
- Modify `frontend/src/components/DropshippingOverview.tsx`: load insights independently and preserve partial-failure behavior.
- Modify `frontend/src/components/ProductPerformanceAnalytics.tsx`: accept controlled product selection from the parent.
- Create `frontend/src/dropshipping-decision-insights.css`: focused responsive styles for insight cards and severity states.
- Modify the existing frontend style import entry point that already imports analytics styles, only if needed to include the new stylesheet.

---

### Task 1: Backend Decision Rule Engine

**Files:**
- Create: `backend/app/services/dropshipping_decision_intelligence.py`
- Create: `backend/tests/test_dropshipping_decision_intelligence.py`
- Read/consume: `backend/app/services/dropshipping_analytics.py`

**Interfaces:**
- Consumes: `get_product_profitability(db, organization_id, store_id, date_from, date_to, limit=200) -> list[dict[str, Any]]`.
- Produces:
  ```python
  def get_dropshipping_decision_insights(
      db: Session,
      organization_id: int,
      store_id: int,
      currency: str,
      date_from: datetime | None,
      date_to: datetime | None,
      limit: int = 20,
  ) -> dict[str, Any]:
      ...
  ```
- Returned keys: `generated_at`, `date_from`, `date_to`, `currency`, `summary`, `insights`.

- [ ] **Step 1: Write the failing rule-engine tests**

Create fixtures analogous to `backend/tests/test_product_analytics_v2.py`, then add focused tests that assert structured keys/evidence rather than prose. Include at minimum these exact behavioral cases:

```python
def test_incomplete_cost_suppresses_margin_dependent_insights(db, org_store):
    # Delivered product with one cost and one missing cost.
    result = get_dropshipping_decision_insights(...)
    types = {item["type"] for item in result["insights"]}
    assert "cost_incomplete" in types
    assert "negative_margin" not in types
    assert "low_margin" not in types
    assert "winner" not in types
    assert "opportunity" not in types


def test_negative_margin_is_critical(db, org_store):
    result = get_dropshipping_decision_insights(...)
    insight = next(item for item in result["insights"] if item["type"] == "negative_margin")
    assert insight["severity"] == "critical"
    assert insight["action_key"] == "review_price_and_cost"
    assert insight["evidence"]["gross_profit"] < 0


def test_rate_thresholds_are_sample_guarded(db, org_store):
    # Four orders with bad rates must not alert; the fifth qualifying observation may alert.
    ...


def test_stock_runway_boundaries(db, org_store):
    # Bounded range with >= 3 delivered units.
    # <3 days => critical; 3<=days<7 => warning; >=7 => no runway alert.
    ...


def test_unbounded_range_omits_runway_but_keeps_other_rules(db, org_store):
    result = get_dropshipping_decision_insights(..., date_from=None, date_to=None)
    assert all(item["type"] != "stock_runway" for item in result["insights"])


def test_winner_suppresses_opportunity(db, org_store):
    types = [item["type"] for item in get_dropshipping_decision_insights(...)["insights"]]
    assert "winner" in types
    assert "opportunity" not in types


def test_insights_are_sorted_then_limited(db, org_store):
    result = get_dropshipping_decision_insights(..., limit=2)
    assert len(result["insights"]) == 2
    assert [item["severity"] for item in result["insights"]] == ["critical", "warning"]
```

Also cover empty store, low margin, delivery risk, cancellation risk, return risk, stockout, revenue concentration, profit concentration, opportunity, stable IDs, summary counts, and no `NaN`/`Infinity` values.

- [ ] **Step 2: Run the new backend test file and verify RED**

Run:
```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py
```
Expected: FAIL because `app.services.dropshipping_decision_intelligence` and `get_dropshipping_decision_insights` do not yet exist.

- [ ] **Step 3: Implement minimal deterministic rule engine**

Create constants matching the approved spec:

```python
SEVERITY_RANK = {"critical": 0, "warning": 1, "opportunity": 2, "positive": 3}
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

Use one helper to construct insight payloads with stable IDs:

```python
def _insight(*, type_: str, severity: str, product: dict[str, Any], title_key: str,
             reason_key: str, action_key: str, evidence: dict[str, Any]) -> dict[str, Any]:
    product_id = int(product["product_id"])
    return {
        "id": f"{type_}:{product_id}",
        "type": type_,
        "severity": severity,
        "product_id": product_id,
        "product_title": product["title"],
        "title_key": title_key,
        "reason_key": reason_key,
        "action_key": action_key,
        "evidence": evidence,
    }
```

Calculate bounded period days as:

```python
period_days = None
if date_from is not None and date_to is not None:
    seconds = (date_to - date_from).total_seconds()
    if seconds > 0:
        period_days = seconds / 86400
```

Implement exactly the approved thresholds and suppressions. For runway use:

```python
units_per_day = units_delivered / period_days
stock_runway_days = inventory_quantity / units_per_day
```

Round `units_per_day` and `stock_runway_days` to one decimal in evidence. Do not emit runway when `units_delivered < 3`, when no bounded range exists, or when inventory is zero (emit `stockout` instead).

For concentration, first compute store-level counts of products with positive delivered revenue / positive gross profit so a single-product store cannot trigger concentration.

- [ ] **Step 4: Run the rule-engine tests and verify GREEN**

Run:
```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py
```
Expected: all tests in the file PASS.

- [ ] **Step 5: Commit the backend rule engine**

```bash
git add backend/app/services/dropshipping_decision_intelligence.py backend/tests/test_dropshipping_decision_intelligence.py
git commit -m "feat: add dropshipping decision intelligence rules"
```

---

### Task 2: Insights API Contract and Isolation

**Files:**
- Modify: `backend/app/api/dropshipping_analytics.py`
- Modify: `backend/tests/test_dropshipping_decision_intelligence.py`

**Interfaces:**
- Consumes: `get_dropshipping_decision_insights(...)` from Task 1.
- Produces: `GET /api/stores/{store_id}/analytics/dropshipping/insights?date_from=...&date_to=...&limit=...`.

- [ ] **Step 1: Add failing API/scoping tests**

Cover these contracts using the repository's existing API test patterns:

```python
def test_insights_endpoint_requires_analytics_read(...):
    ...


def test_insights_endpoint_rejects_foreign_store(...):
    response = client.get(f"/api/stores/{foreign_store.id}/analytics/dropshipping/insights")
    assert response.status_code == 404


def test_insights_endpoint_passes_inclusive_date_range_and_limit(...):
    response = client.get(
        f"/api/stores/{store.id}/analytics/dropshipping/insights"
        "?date_from=2026-09-01&date_to=2026-09-11&limit=7"
    )
    assert response.status_code == 200
    assert response.json()["date_to"] == "2026-09-12T00:00:00"
```

Assert `limit` accepts 1–50 and returns 422 outside that range.

- [ ] **Step 2: Run endpoint tests and verify RED**

Run:
```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py -k endpoint
```
Expected: FAIL/404 because the endpoint does not exist.

- [ ] **Step 3: Add the API endpoint with existing guards**

In `backend/app/api/dropshipping_analytics.py`, import the service and add:

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

Do not create a new permission, router, store lookup, or date parser.

- [ ] **Step 4: Run endpoint + existing dropshipping regressions**

Run:
```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py tests/test_dropshipping_analytics.py tests/test_product_analytics_v2.py
```
Expected: PASS.

- [ ] **Step 5: Commit the endpoint**

```bash
git add backend/app/api/dropshipping_analytics.py backend/tests/test_dropshipping_decision_intelligence.py
git commit -m "feat: expose dropshipping decision insights api"
```

---

### Task 3: Frontend Insight Contract and Pure Presentation Model

**Files:**
- Modify: `frontend/src/services/analytics.ts`
- Create: `frontend/src/utils/dropshippingDecisionInsights.ts`
- Create: `frontend/tests/dropshippingDecisionInsights.test.ts`

**Interfaces:**
- Produces `DropshippingInsightSeverity`, `DropshippingInsightType`, `DropshippingInsight`, `DropshippingDecisionInsightsResponse`.
- Produces `getDropshippingDecisionInsights(storeId, dateFrom?, dateTo?, limit=20)`.
- Produces pure helpers:
  ```ts
  normalizeDecisionInsightLocale(language: string): "es" | "en" | "pt-BR"
  getDecisionInsightCopy(language: string): DecisionInsightCopy
  getDecisionInsightPresentation(insight: DropshippingInsight, language: string): DecisionInsightPresentation
  selectedProductIdFromInsight(insight: DropshippingInsight): number | null
  ```

- [ ] **Step 1: Write failing node:test contracts**

Create `frontend/tests/dropshippingDecisionInsights.test.ts` with direct imports from the new utility. Cover ES, EN, PT-BR, every stable backend type/action/reason key used by the spec, evidence rendering metadata, severity tone, and product selection:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import {
  getDecisionInsightPresentation,
  selectedProductIdFromInsight,
} from "../src/utils/dropshippingDecisionInsights.ts";

test("maps known keys without leaking raw backend keys", () => {
  const presentation = getDecisionInsightPresentation(sampleStockInsight, "es");
  assert.equal(presentation.title, "Stock crítico");
  assert.equal(presentation.action, "Reponer inventario");
  assert.equal(presentation.title.includes("stock_runway"), false);
});

test("returns product id for product drill-down", () => {
  assert.equal(selectedProductIdFromInsight(sampleStockInsight), 123);
});
```

Include a test that unknown language falls back to Spanish. Do not silently accept unknown backend keys: utility tests should make missing copy entries obvious during development.

- [ ] **Step 2: Run frontend test and verify RED**

Run:
```bash
cd frontend
npm test -- tests/dropshippingDecisionInsights.test.ts
```
Expected: FAIL because the utility does not exist.

- [ ] **Step 3: Add exact TypeScript API types and client**

In `frontend/src/services/analytics.ts`, define unions for the approved enums and the evidence payload as `Record<string, number | string | null>`. Add:

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

Keep the existing private `buildParams` unchanged so existing callers do not change behavior.

- [ ] **Step 4: Implement the pure presentation model**

In `frontend/src/utils/dropshippingDecisionInsights.ts`, keep all human copy and formatting labels outside React. Define complete copy maps for ES/EN/PT-BR keyed by all approved `title_key`, `reason_key`, `action_key` values. Return a presentation object containing `title`, `reason`, `action`, `severityLabel`, and evidence label/value pairs.

`selectedProductIdFromInsight()` must return `insight.product_id` when it is a number and `null` otherwise; it must contain no DOM logic.

- [ ] **Step 5: Run focused frontend tests and verify GREEN**

Run:
```bash
cd frontend
npm test -- tests/dropshippingDecisionInsights.test.ts
```
Expected: PASS.

- [ ] **Step 6: Commit frontend contract/model**

```bash
git add frontend/src/services/analytics.ts frontend/src/utils/dropshippingDecisionInsights.ts frontend/tests/dropshippingDecisionInsights.test.ts
git commit -m "feat: add decision insight frontend contract"
```

---

### Task 4: Decision Insights UI and Partial-Failure Isolation

**Files:**
- Create: `frontend/src/components/DropshippingDecisionInsights.tsx`
- Create: `frontend/src/dropshipping-decision-insights.css`
- Modify: `frontend/src/components/DropshippingOverview.tsx`
- Modify: `frontend/src/utils/dropshippingAnalyticsState.ts`
- Modify: `frontend/tests/dropshippingAnalyticsState.test.ts`
- Modify the analytics style import entry point only if the component stylesheet is not imported directly.

**Interfaces:**
- `DropshippingDecisionInsights` props:
  ```ts
  interface Props {
    response: DropshippingDecisionInsightsResponse | null;
    unavailable: boolean;
    language: string;
    currency: string;
    onSelectProduct: (productId: number) => void;
  }
  ```
- `DropshippingOverview` owns `selectedProductId: number | null` and passes selection to Product Analytics V2 in Task 5.

- [ ] **Step 1: Extend partial-state tests RED-first**

Extend `DropshippingAnalyticsSection` to include `"insights"` only after first writing tests that expect five settled sections. Assert that failure of only insights does **not** make `allDropshippingSectionsFailed()` true, while failure of all five does.

Run:
```bash
cd frontend
npm test -- tests/dropshippingAnalyticsState.test.ts
```
Expected: FAIL until the section model includes insights.

- [ ] **Step 2: Update partial-state helper minimally**

Update the ordered section tuple to:

```ts
export const DROPSHIPPING_ANALYTICS_SECTIONS = [
  "overview",
  "profitability",
  "products",
  "orders",
  "insights",
] as const;
```

Keep `settledValue()` generic and preserve existing behavior for the original four sections.

- [ ] **Step 3: Add insights to the independent loader**

In `DropshippingOverview.tsx`, add `getDropshippingDecisionInsights(...)` as the fifth promise in `Promise.allSettled`. Extend `DashboardData` with `insights: DropshippingDecisionInsightsResponse | null` and map result index 4 with `settledValue(results[4])`.

Important behavior:
- If insights alone fail, existing dashboard data renders normally.
- `DropshippingDecisionInsights` receives `unavailable={unavailableSections.includes("insights")}`.
- A failed insights request must not set the page-level `error` unless every analytics section failed.

- [ ] **Step 4: Implement the dedicated insight component**

Render the section before the KPI grid. Use `getDecisionInsightPresentation()` for all user-facing copy. Each product-specific card gets a real button:

```tsx
<button type="button" onClick={() => onSelectProduct(insight.product_id!)}>
  {copy.viewProduct}
</button>
```

Do not inspect the DOM, query rows, or synthesize clicks. Empty response renders a localized healthy/empty state; unavailable response renders a localized temporary-unavailable state.

- [ ] **Step 5: Add responsive styles**

Create CSS classes prefixed `decision-insights-` with distinct severity treatment using existing design tokens/CSS variables where available. Provide a one-column mobile layout and multi-column desktop card grid. Do not change unrelated analytics styles.

- [ ] **Step 6: Run frontend tests, lint and build**

Run:
```bash
cd frontend
npm test
npm run lint
npm run build
```
Expected: all tests PASS, lint 0 errors, TypeScript/Vite build succeeds.

- [ ] **Step 7: Commit the insight UI**

```bash
git add frontend/src/components/DropshippingDecisionInsights.tsx frontend/src/dropshipping-decision-insights.css frontend/src/components/DropshippingOverview.tsx frontend/src/utils/dropshippingAnalyticsState.ts frontend/tests/dropshippingAnalyticsState.test.ts
git commit -m "feat: surface dropshipping decision insights"
```

---

### Task 5: Explicit Product Analytics V2 Drill-Down Contract

**Files:**
- Modify: `frontend/src/components/ProductPerformanceAnalytics.tsx`
- Modify: `frontend/src/components/DropshippingOverview.tsx`
- Modify: `frontend/src/utils/dropshippingDecisionInsights.ts`
- Modify: `frontend/tests/dropshippingDecisionInsights.test.ts`

**Interfaces:**
- Change Product Analytics props to include:
  ```ts
  selectedProductId: number | null;
  onSelectedProductChange: (productId: number | null) => void;
  ```
- `DropshippingOverview` is the single owner of selection state.
- `DropshippingDecisionInsights.onSelectProduct(id)` calls the parent setter.

- [ ] **Step 1: Add a RED test for deterministic selection behavior**

Add a pure helper if needed:

```ts
export function nextSelectedProductId(
  currentProductId: number | null,
  requestedProductId: number,
): number | null {
  return currentProductId === requestedProductId ? null : requestedProductId;
}
```

Test insight selection always resolves to the requested product, while table toggle can close an already selected row. Keep this state logic outside React so it is covered by `node:test`.

- [ ] **Step 2: Run the focused frontend test and verify RED**

Run:
```bash
cd frontend
npm test -- tests/dropshippingDecisionInsights.test.ts
```
Expected: FAIL until the new selection helper/contract exists.

- [ ] **Step 3: Make ProductPerformanceAnalytics controlled**

Remove its internal `useState<number | null>` for `selectedProductId`. Keep detail fetching keyed from the controlled prop. Replace row toggle with:

```ts
onSelectedProductChange(
  selectedProductId === product.product_id ? null : product.product_id,
)
```

Close button calls `onSelectedProductChange(null)`.

- [ ] **Step 4: Wire insight selection through DropshippingOverview**

Add:

```ts
const [selectedProductId, setSelectedProductId] = useState<number | null>(null);
```

Pass `onSelectProduct={setSelectedProductId}` to `DropshippingDecisionInsights` and pass both controlled props to `ProductPerformanceAnalytics`.

When store/date range changes, reset selection to `null` before loading new analytics so an old product detail cannot remain open under a different cohort/store.

- [ ] **Step 5: Run full frontend verification**

Run:
```bash
cd frontend
npm test
npm run lint
npm run build
```
Expected: PASS / 0 lint errors / successful production build.

- [ ] **Step 6: Commit controlled drill-down**

```bash
git add frontend/src/components/ProductPerformanceAnalytics.tsx frontend/src/components/DropshippingOverview.tsx frontend/src/utils/dropshippingDecisionInsights.ts frontend/tests/dropshippingDecisionInsights.test.ts
git commit -m "feat: connect insights to product analytics drilldown"
```

---

### Task 6: Final Backend/Frontend Regression and PR Validation

**Files:**
- Review all files changed by Tasks 1–5.
- No new behavior should be added in this task.

**Interfaces:**
- Produces a reviewable PR with final evidence; does not change public contracts beyond the approved additive `/insights` endpoint and frontend types.

- [ ] **Step 1: Run focused backend regression**

```bash
cd backend
pytest -q tests/test_dropshipping_decision_intelligence.py tests/test_dropshipping_analytics.py tests/test_product_analytics_v2.py tests/test_sales_attribution.py
```
Expected: PASS.

- [ ] **Step 2: Run Ruff on backend**

Use the repository's normal Ruff command (the same command used by `Validate Pull Request`) against the backend. Expected: 0 errors.

- [ ] **Step 3: Run full frontend regression**

```bash
cd frontend
npm test
npm run lint
npm run build
```
Expected: all tests PASS, lint 0 errors, production build succeeds.

- [ ] **Step 4: Review final diff for scope**

Confirm:
- no migration/model change;
- no existing analytics response field removed/renamed;
- no raw localized prose generated by backend;
- no LLM/provider call;
- no mutation endpoint/action;
- endpoint uses existing store validation and `analytics.read`;
- frontend insights failure remains isolated;
- selection is explicit state, not DOM coupling.

- [ ] **Step 5: Open/update the PR and run normal repository CI**

PR title:
```text
feat: add dropshipping decision intelligence
```

PR body must include RED/GREEN evidence, focused test results, frontend test/lint/build results, final head SHA, and a link/path to the approved spec and this plan.

- [ ] **Step 6: Verify final CI on the exact PR head**

Wait for the repository `Validate Pull Request` workflow on the final head. Require:
- backend shard 0 success;
- backend shard 1 success;
- Ruff success;
- frontend validation success;
- combined validation gate success.

Do not mark ready or merge if any required job is pending, skipped unexpectedly, cancelled, or failed.

- [ ] **Step 7: Mark PR ready and merge only after green**

Use squash merge with `expected_head_sha` equal to the final verified PR head. Refetch `main` afterwards and record the resulting commit SHA.
