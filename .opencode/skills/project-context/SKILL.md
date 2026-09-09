---
name: project-context
description: Core Diaglob architecture, repository layout, invariants, and engineering rules. Load for any non-trivial Diaglob task before making cross-cutting changes.
compatibility: opencode
metadata:
  project: diaglob
  scope: global
---

## Purpose

Use this skill to orient work in Diaglob before changing architecture or behavior.

## Repository shape

- `backend/`: FastAPI application, SQLAlchemy models, Alembic migrations, services, integrations, and pytest suite.
- `frontend/`: React + TypeScript + Vite SPA.
- `.github/workflows/deploy-production.yml`: validation and production deployment pipeline.
- `AGENTS.md`: authoritative architecture rules for the Knowledge domain. Read it before touching Knowledge code.

## Global invariants

1. Preserve multi-tenant and multi-store isolation. Any data access tied to tenant/store context must keep the relevant organization/store filters and authorization checks.
2. Do not weaken authentication, authorization, ownership, idempotency, or validation to make a test pass.
3. Diagnose root cause before editing code.
4. Prefer the smallest coherent change that fixes the underlying problem.
5. Preserve existing API contracts unless the task explicitly requires a contract change.
6. When behavior changes, add or update regression coverage.
7. Never hardcode production secrets, credentials, tokens, host keys, or environment-specific values.
8. Do not perform destructive production operations unless explicitly requested.

## Required workflow

1. Inspect the relevant implementation, tests, and callers.
2. Identify invariants that must remain true.
3. Make the minimal implementation change.
4. Run targeted validation first.
5. Run the broader relevant suite/build when practical.
6. Report changed files, tests run, failures, and remaining risks.

## Knowledge domain

`AGENTS.md` is mandatory reading for Knowledge work. Its service-extraction rules take precedence over generic preferences in this skill.
