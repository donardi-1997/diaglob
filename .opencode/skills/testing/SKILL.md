---
name: testing
description: Diagnose regressions and validate Diaglob changes with pytest, Ruff, import checks, frontend builds, and characterization tests without weakening coverage.
compatibility: opencode
metadata:
  project: diaglob
  scope: validation
---

## Core principle

Tests are evidence about behavior, not obstacles to bypass.

## Failure diagnosis

When tests fail:

1. Find the first meaningful exception/root failure, not just the final failure count.
2. Determine whether the failure is implementation, test isolation, fixture/database state, migration/schema drift, environment, or dependency related.
3. Reproduce with the smallest relevant test selection.
4. Fix the root cause.
5. Add regression or characterization coverage when existing tests do not lock the intended behavior.
6. Re-run the targeted tests before the full suite.

## Prohibited shortcuts

- Do not delete, skip, xfail, or loosen assertions merely to make CI green.
- Do not catch broad exceptions solely to suppress failures.
- Do not remove authorization, tenant/store filters, constraints, or validation to satisfy tests.
- Do not assume a local green run proves CI is green when environment differences matter.

## Backend commands

```bash
cd backend
python -m pytest <target> -q --tb=short
ruff check app/ tests/
python -c "import app.main; print('OK')"
python -m pytest -q --tb=short
```

## Frontend commands

```bash
cd frontend
npm run build
npm run lint
```

## Final report

State exactly:

- root cause
- files changed
- targeted tests and result
- full backend suite result if run
- Ruff result if run
- frontend build/lint result if relevant
- any validation not run
- remaining risks
