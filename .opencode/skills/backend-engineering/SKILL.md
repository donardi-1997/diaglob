---
name: backend-engineering
description: Implement and review Diaglob backend changes in FastAPI, SQLAlchemy, Alembic, APIs, services, and integrations while preserving tenant isolation and contracts.
compatibility: opencode
metadata:
  project: diaglob
  scope: backend
---

## Stack

The backend uses FastAPI, SQLAlchemy 2.x, Alembic, Pydantic, PostgreSQL/psycopg, pytest, and Ruff.

## Engineering rules

- Inspect existing patterns before introducing a new abstraction.
- Keep HTTP concerns in API/router code and domain/business logic in appropriate service/domain modules.
- For Knowledge work, follow root `AGENTS.md` exactly.
- Preserve organization/store ownership checks in every query and mutation that requires them.
- Do not silently broaden query scope.
- Do not expose provider errors, credentials, tokens, or internal secrets through API responses.
- Keep external-provider calls behind existing client/service boundaries when those boundaries exist.
- Preserve idempotency semantics for operations that create external resources/orders.
- Map domain/provider failures deliberately; do not convert all failures into generic success or 200 responses.

## Database changes

- Inspect current models and Alembic history before proposing schema changes.
- Prefer additive, backward-compatible migrations when possible.
- Consider existing production rows, nullability, defaults, constraints, indexes, and downgrade behavior.
- Never edit an already-applied migration to represent a new production change; create a new migration.
- Do not change `backend/app/models.py` when working in the Knowledge domain because root `AGENTS.md` explicitly forbids it.

## Validation

Run the narrowest relevant tests first, then broader validation:

```bash
cd backend
python -m pytest <relevant tests> -q
ruff check app/ tests/
python -c "import app.main; print('OK')"
python -m pytest -q
```

Do not claim the full suite passed unless it was actually executed successfully.
