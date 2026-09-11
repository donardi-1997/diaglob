# Operations Center Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Diaglob Operations Center report real operational health, accurate AI metric semantics, prioritized alerts, and live refresh behavior.

**Architecture:** Keep `/api/stores/{store_id}/operations/summary` as the single frontend contract. Compute health in the backend service from existing real summary/integration data, then let the React dashboard render that contract without duplicating business rules. No schema changes are required.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, TypeScript, Vite.

**Spec:** `docs/superpowers/specs/2026-09-11-operations-center-health.md`

## Global Constraints

- No database migrations.
- Do not modify `backend/app/models.py`.
- Preserve tenant/store isolation and the existing `analytics.read` endpoint permission.
- Business-health rules live in backend services, not the React page.
- `degraded` means dependency/status-read degradation, not a false disconnected state.
- Automatic refresh interval: 30 seconds while the dashboard is mounted.
- Use TDD for behavior changes.
- Do not merge before final PR CI is green.

---

### Task 1: Backend health contract and AI metric semantics

**Files:**
- Modify: `backend/tests/test_operations.py`
- Modify: `backend/tests/test_operations_integrations.py`
- Modify: `backend/tests/test_operations_resilience.py`
- Modify: `backend/app/operations.py`
- Modify: `backend/app/services/operations_integrations.py`

**Interfaces:**
- Consumes: existing `get_operations_summary(db, organization_id, store_id)` and `get_dynamic_operations_summary(db, organization_id, store_id)`.
- Produces: top-level `health: {status, issues, critical_issues}` and `conversations.ai_message_share_pct`.

- [ ] **Step 1: Write failing backend tests**

Add assertions that:

```python
assert summary["conversations"]["ai_message_share_pct"] == 50.0
assert "ai_resolved_pct" not in summary["conversations"]
assert summary["health"] == {
    "status": "operational",
    "issues": 0,
    "critical_issues": 0,
}
```

Add one test that inserts an `AutomationExecution(status="failed")` in the last 7 days and expects `health.status == "attention"`. Add one resilience test using an intentionally dropped integration table and expect `health.status == "degraded"` with `critical_issues >= 1`.

- [ ] **Step 2: Run focused backend tests and verify RED**

Run:

```bash
cd backend && python -m pytest -q tests/test_operations.py tests/test_operations_integrations.py tests/test_operations_resilience.py
```

Expected: failures for missing `health` / `ai_message_share_pct`, proving the new contract is not implemented yet.

- [ ] **Step 3: Implement minimal backend health calculation**

In `backend/app/operations.py`, rename the calculated field from `ai_resolved_pct` to `ai_message_share_pct` without changing the underlying ratio calculation.

In `backend/app/services/operations_integrations.py`, add a small pure helper:

```python
def _operations_health(summary: dict[str, Any]) -> dict[str, Any]:
    alerts = summary.get("alerts", [])
    degraded = [a for a in alerts if a.get("type") == "integration_status_degraded"]
    warnings = [
        a for a in alerts
        if a.get("severity") in {"warning", "error"}
        and a.get("type") != "integration_status_degraded"
    ]
    if degraded:
        status = "degraded"
    elif warnings:
        status = "attention"
    else:
        status = "operational"
    return {
        "status": status,
        "issues": len(degraded) + len(warnings),
        "critical_issues": len(degraded),
    }
```

Call it after the final alert list is assembled and assign `summary["health"]`.

- [ ] **Step 4: Re-run focused backend tests and verify GREEN**

Run the same pytest command. Expected: all focused Operations Center tests pass.

- [ ] **Step 5: Commit backend contract**

Commit message:

```text
feat: add real Operations Center health status
```

---

### Task 2: Frontend status rendering and refresh behavior

**Files:**
- Modify: `frontend/src/services/operations.ts`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/utils/operationsStatus.ts`
- Create or modify the nearest existing frontend unit test files for Operations Center utilities/dashboard behavior.
- Modify CSS only if needed for the status/refresh controls, reusing existing dashboard classes where possible.

**Interfaces:**
- Consumes: `OperationsSummary.health` and `OperationsConversation.ai_message_share_pct`.
- Produces: localized health label, severity-prioritized alerts, manual refresh, and 30-second background refresh.

- [ ] **Step 1: Write failing frontend tests**

Test the pure status/copy utilities rather than implementation details. Required cases:

```ts
expect(operationsHealthLabel("operational", "es")).toBe("Operativo");
expect(operationsHealthLabel("attention", "es")).toBe("Requiere atención");
expect(operationsHealthLabel("degraded", "es")).toBe("Degradado");
```

Also test an exported alert-ordering helper with error before warning before info.

- [ ] **Step 2: Run frontend tests and verify RED**

Use the repository's existing frontend test command discovered from `frontend/package.json`, targeting the Operations Center test file when supported. Expected: failure because the new helpers/contract do not exist.

- [ ] **Step 3: Implement frontend contract**

Update TypeScript types:

```ts
export interface OperationsHealth {
  status: "operational" | "attention" | "degraded";
  issues: number;
  critical_issues: number;
}
```

Rename `ai_resolved_pct` to `ai_message_share_pct` and add `health` to `OperationsSummary`.

Implement localized labels for ES/EN/PT and a severity sorter in `operationsStatus.ts`.

In `DashboardPage.tsx`:
- replace the hardcoded healthy hero label with `health.status`;
- change metric copy from “resolved by AI” to “AI message share” equivalents;
- sort alerts before rendering;
- refactor loading into `loadSummary({initial?: boolean})` so initial load shows the skeleton while background refresh preserves current data;
- call the loader immediately when `storeId` changes;
- schedule `window.setInterval(..., 30_000)` and clear it on cleanup;
- add a manual refresh button that invokes the same loader.

- [ ] **Step 4: Verify frontend GREEN and build**

Run focused frontend tests, then:

```bash
cd frontend && npm run build
```

Expected: tests pass and TypeScript/Vite build succeeds.

- [ ] **Step 5: Commit frontend behavior**

Commit message:

```text
feat: make Operations Center health live
```

---

### Task 3: Regression verification and PR

**Files:**
- No new behavior files unless verification exposes a regression.
- Update plan/spec only if implementation intentionally diverges from the approved contract.

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: reviewable PR with green CI.

- [ ] **Step 1: Run focused backend suite again**

```bash
cd backend && python -m pytest -q tests/test_operations.py tests/test_operations_integrations.py tests/test_operations_resilience.py
```

Expected: pass.

- [ ] **Step 2: Run broader local verification available through repository CI**

Run backend lint/tests and frontend build/test commands supported by the repository. Record exact outputs in the PR body.

- [ ] **Step 3: Review branch diff**

Confirm:
- no model/schema/migration changes;
- endpoint path and permission unchanged;
- no mock/hardcoded operational status remains in the hero;
- no `ai_resolved_pct` frontend contract remains;
- the only periodic network work is the 30-second Operations summary refresh.

- [ ] **Step 4: Open draft PR**

Title:

```text
feat: make Operations Center health real-time
```

The PR body must summarize health semantics, AI metric correction, refresh behavior, tests, and note that there are no migrations.

- [ ] **Step 5: Wait for and inspect final CI result**

Fetch the workflow run for the final head SHA. Do not mark ready or merge unless required backend/frontend validation is green.

- [ ] **Step 6: Mark ready and squash merge**

Use the verified final head SHA as the merge guard. Refetch `main` after merge and report the final main commit.
