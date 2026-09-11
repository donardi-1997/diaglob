# CI Validation Speedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce pull-request feedback time by skipping irrelevant backend/frontend validation and running relevant validation jobs in parallel, without weakening merge safety.

**Architecture:** Keep a single `Validate Pull Request` workflow and preserve the existing final check name `Backend + Frontend validation`. Add a lightweight change-detection job that classifies PR files into backend and frontend scopes, run backend and frontend validation as independent jobs guarded by those outputs, then aggregate their results in a final always-running compatibility gate.

**Tech Stack:** GitHub Actions, Bash, Python 3.10, pytest, Ruff, Node 22, npm, Vite.

**Spec:** Conversation-approved bounded CI optimization; no separate design spec is required.

## Global Constraints

- Do not reduce backend test coverage when backend files change.
- Do not reduce frontend lint/test/build coverage when frontend files change.
- Preserve the final required-check name `Backend + Frontend validation`.
- Changes to `.github/workflows/validate-pr.yml` itself must force both backend and frontend validation.
- Documentation-only changes may skip both expensive suites while still producing a successful final validation check.
- Do not add pytest parallelism in this slice; profile and evaluate `pytest-xdist` separately after this optimization is measured.
- Do not change application code.

---

### Task 1: Make PR validation scope-aware and parallel

**Files:**
- Modify: `.github/workflows/validate-pr.yml`

**Interfaces:**
- Consumes: `github.event.pull_request.base.sha`, `github.event.pull_request.head.sha`.
- Produces: `changes.outputs.backend` and `changes.outputs.frontend`, each the literal string `true` or `false`; final job named `Backend + Frontend validation`.

- [ ] **Step 1: Replace the monolithic validation job with a lightweight change detector**

Use `actions/checkout@v4` with `fetch-depth: 0`, run `git diff --name-only BASE_SHA HEAD_SHA`, and classify:

```bash
backend=false
frontend=false

while IFS= read -r file; do
  case "$file" in
    backend/*)
      backend=true
      ;;
    frontend/*)
      frontend=true
      ;;
    .github/workflows/validate-pr.yml)
      backend=true
      frontend=true
      ;;
  esac
done <<< "$files"

echo "backend=$backend" >> "$GITHUB_OUTPUT"
echo "frontend=$frontend" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 2: Create an independent backend job**

Guard the job with:

```yaml
if: needs.changes.outputs.backend == 'true'
```

Keep the existing backend contract unchanged:

```yaml
- actions/setup-python@v5 with Python 3.10 and pip caching
- install `backend/requirements.txt`, Ruff, and pytest
- `ruff check app/ tests/`
- `python -m pytest -q --tb=short`
```

- [ ] **Step 3: Create an independent frontend job**

Guard the job with:

```yaml
if: needs.changes.outputs.frontend == 'true'
```

Keep the existing frontend contract unchanged:

```yaml
- actions/setup-node@v4 with Node 22 and npm caching
- `npm ci`
- `npm run lint`
- `npm test`
- `npm run build`
```

- [ ] **Step 4: Add the compatibility gate**

Add a final job with:

```yaml
name: Backend + Frontend validation
if: always()
needs: [changes, backend, frontend]
```

Its shell check must fail if change detection failed, or if either relevant validation job failed/cancelled; `success` and `skipped` are acceptable for backend/frontend because irrelevant scopes intentionally skip.

- [ ] **Step 5: Commit the workflow change**

Commit message:

```text
ci: run PR validation selectively in parallel
```

### Task 2: Verify behavior and measure the improvement

**Files:**
- No application files changed.
- The PR itself is the integration test for the workflow.

**Interfaces:**
- Consumes: workflow run/job states on the CI branch PR.
- Produces: measured frontend-only validation duration and evidence that the final compatibility gate succeeds.

- [ ] **Step 1: Open a draft PR against `main`**

The PR changes the workflow and plan document, so the workflow-file change must intentionally force both backend and frontend suites once. Verify both run concurrently after change detection.

- [ ] **Step 2: Verify the first run**

Expected:

```text
changes: success
backend: success
frontend: success
Backend + Frontend validation: success
```

Confirm backend and frontend jobs overlap in time rather than running serially.

- [ ] **Step 3: Exercise a frontend-only commit on the same branch**

Make a harmless, reversible change under `frontend/` that can be removed before final merge, or rebase/test the workflow using a dedicated frontend-only verification branch if needed. Expected behavior:

```text
changes: success
backend: skipped
frontend: success
Backend + Frontend validation: success
```

Record total workflow duration and compare with the current ~4m39s backend-suite baseline.

- [ ] **Step 4: Remove any temporary verification-only file/change**

The final PR must contain only the workflow optimization and this plan document.

- [ ] **Step 5: Final verification**

Inspect the final PR diff. Confirm no application code changed and that the final check remains compatible with existing branch protection.
