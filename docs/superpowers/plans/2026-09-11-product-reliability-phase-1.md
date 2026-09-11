# Product Reliability Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add privacy-safe backend Sentry observability and make frontend tests a mandatory production deployment gate.

**Architecture:** Add one optional observability boundary under `backend/app/runtime/` and call it from FastAPI bootstrap. Keep configuration in the existing Settings object, with safe defaults and no business-state coupling. CI hardening remains isolated to the production workflow.

**Tech Stack:** FastAPI, pydantic-settings, sentry-sdk 2.69.1, pytest, GitHub Actions, React/Vite frontend test script.

**Spec:** `docs/superpowers/specs/2026-09-11-product-reliability-phase-1.md`

## Global Constraints

- Sentry is optional: no DSN means no initialization.
- `send_default_pii=False` is mandatory.
- Default traces sample rate is `0.0`.
- No business API, DB schema, billing, Shopify, Knowledge, or AI behavior changes.
- Pin `sentry-sdk[fastapi]==2.69.1`.
- Production deploy validation must run frontend tests before build/deploy.

---

### Task 1: Add backend observability configuration contract

**Files:**
- Modify: `backend/app/settings.py`
- Create: `backend/app/runtime/observability.py`
- Create: `backend/tests/test_observability.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: existing `Settings` from `app.settings`.
- Produces: `initialize_observability(settings: Settings) -> bool` where `True` means Sentry initialization was attempted and `False` means it was skipped because no DSN is configured.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_observability.py` with tests that monkeypatch only the Sentry initialization boundary, never network transport:

```python
from app.settings import Settings
from app.runtime.observability import initialize_observability


def test_sentry_is_skipped_without_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr("app.runtime.observability.sentry_sdk.init", lambda **kwargs: calls.append(kwargs))

    enabled = initialize_observability(Settings(sentry_dsn=None))

    assert enabled is False
    assert calls == []


def test_sentry_uses_privacy_safe_configuration(monkeypatch):
    calls = []
    monkeypatch.setattr("app.runtime.observability.sentry_sdk.init", lambda **kwargs: calls.append(kwargs))

    settings = Settings(
        sentry_dsn="https://public@example.ingest.sentry.io/123",
        sentry_environment="production",
        sentry_release="diaglob@abc1234",
        sentry_traces_sample_rate=0.05,
    )

    enabled = initialize_observability(settings)

    assert enabled is True
    assert len(calls) == 1
    assert calls[0]["dsn"] == settings.sentry_dsn
    assert calls[0]["environment"] == "production"
    assert calls[0]["release"] == "diaglob@abc1234"
    assert calls[0]["traces_sample_rate"] == 0.05
    assert calls[0]["send_default_pii"] is False
```

Add a settings validation test if the current Settings style supports field constraints cleanly:

```python
import pytest
from pydantic import ValidationError


def test_sentry_sample_rate_rejects_values_above_one():
    with pytest.raises(ValidationError):
        Settings(sentry_traces_sample_rate=1.1)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend
python -m pytest tests/test_observability.py -q
```

Expected: FAIL because `app.runtime.observability` and/or Sentry settings fields do not yet exist.

- [ ] **Step 3: Add the dependency and minimal settings**

Append to `backend/requirements.txt`:

```text
sentry-sdk[fastapi]==2.69.1
```

Add these fields to the existing `Settings` model, following its current conventions:

```python
sentry_dsn: str | None = None
sentry_environment: str = "production" if is_production else "development"
sentry_release: str | None = None
sentry_traces_sample_rate: float = Field(default=0.0, ge=0.0, le=1.0)
```

If `is_production` is a property rather than a field available at declaration time, use a static safe default such as `"development"` and rely on `SENTRY_ENVIRONMENT` in production; do not create circular validation logic.

- [ ] **Step 4: Implement the minimal observability boundary**

Create `backend/app/runtime/observability.py`:

```python
from __future__ import annotations

import sentry_sdk

from ..settings import Settings


def initialize_observability(settings: Settings) -> bool:
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment,
        release=settings.sentry_release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
    return True
```

- [ ] **Step 5: Run focused tests and verify GREEN**

```bash
cd backend
python -m pytest tests/test_observability.py -q
```

Expected: PASS.

- [ ] **Step 6: Run relevant settings/runtime tests**

```bash
cd backend
python -m pytest -q --tb=short
```

Expected: all backend tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/settings.py backend/app/runtime/observability.py backend/tests/test_observability.py backend/requirements.txt
git commit -m "feat: add privacy-safe Sentry backend observability"
```

---

### Task 2: Initialize observability during FastAPI bootstrap

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_observability.py`

**Interfaces:**
- Consumes: `initialize_observability(settings: Settings) -> bool` from Task 1.
- Produces: Sentry initialization at process bootstrap without changing app routes or lifespan behavior.

- [ ] **Step 1: Write a failing bootstrap characterization test**

Extend `backend/tests/test_observability.py` with a focused test around the bootstrap helper if main import side effects make direct assertions brittle. Prefer extracting a tiny helper only if necessary. The behavior to prove is: the same validated `settings` object passed to app setup is passed into `initialize_observability` exactly once.

Example desired assertion if a helper is introduced:

```python
def test_configure_runtime_initializes_observability(monkeypatch):
    seen = []
    monkeypatch.setattr("app.main.initialize_observability", lambda settings: seen.append(settings) or True)

    app.main.configure_runtime(app.main.settings)

    assert seen == [app.main.settings]
```

- [ ] **Step 2: Verify RED**

```bash
cd backend
python -m pytest tests/test_observability.py -q
```

Expected: FAIL because bootstrap does not invoke the observability boundary yet.

- [ ] **Step 3: Add the minimal bootstrap call**

In `backend/app/main.py`, import and call the boundary before serving requests:

```python
from .runtime.observability import initialize_observability

settings = get_settings()
initialize_observability(settings)
```

Do not add request-specific tags or business context in this task.

- [ ] **Step 4: Verify GREEN and regression suite**

```bash
cd backend
python -m pytest tests/test_observability.py -q
python -m pytest -q --tb=short
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_observability.py
git commit -m "feat: initialize backend observability at startup"
```

---

### Task 3: Make frontend tests a production deployment gate

**Files:**
- Modify: `.github/workflows/deploy-production.yml`

**Interfaces:**
- Consumes: existing frontend script `npm test` from `frontend/package.json`.
- Produces: production `validate` job fails before deployment if frontend tests fail.

- [ ] **Step 1: Modify production validation in the smallest possible way**

Change:

```yaml
      - name: Frontend validation
        run: |
          cd frontend
          npm ci
          npm run lint
          npm run build
```

To:

```yaml
      - name: Frontend validation
        run: |
          cd frontend
          npm ci
          npm run lint
          npm test
          npm run build
```

- [ ] **Step 2: Validate workflow syntax and semantics**

Review the workflow diff and confirm:

- `deploy.needs` still points to `validate`.
- `npm test` runs after install/lint and before build.
- No secrets or deploy commands changed.

Then rely on the PR workflow plus production workflow after merge for executable validation.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-production.yml
git commit -m "ci: run frontend tests before production deploy"
```

---

### Task 4: Document production Sentry configuration

**Files:**
- Modify: `README.md` or the repository's existing deployment/environment documentation if a more specific file exists.

**Interfaces:**
- Consumes: settings introduced in Task 1.
- Produces: operator-facing configuration contract.

- [ ] **Step 1: Add a concise environment section**

Document:

```text
SENTRY_DSN=<backend project DSN>
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=diaglob@<git-sha>
SENTRY_TRACES_SAMPLE_RATE=0.05
```

State explicitly that leaving `SENTRY_DSN` empty disables Sentry and that default PII collection is disabled in code.

- [ ] **Step 2: Verify documentation matches exact settings names**

Compare against `backend/app/settings.py` and fix any mismatch before commit.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document backend Sentry configuration"
```

---

### Task 5: Full verification and PR

**Files:**
- No new production files.

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a reviewable PR with verified backend and frontend gates.

- [ ] **Step 1: Run full backend validation**

```bash
cd backend
ruff check app/ tests/
python -m pytest -q --tb=short
```

- [ ] **Step 2: Run full frontend validation**

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build
```

- [ ] **Step 3: Review privacy constraints**

Search the branch for Sentry calls and verify there is no `set_user`, no message-body capture, no auth/cookie injection, and `send_default_pii=False` is explicit.

- [ ] **Step 4: Open PR**

PR title:

```text
feat: add backend observability and harden production validation
```

PR body must summarize Sentry opt-in behavior, privacy defaults, the frontend-test deployment gate, verification commands, and the required production env vars.
