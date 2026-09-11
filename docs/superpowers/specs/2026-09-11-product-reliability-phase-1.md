# Diaglob Product Reliability Phase 1

Date: 2026-09-11
Branch: `feature/product-reliability-phase-1`
Status: Approved for implementation

## Goal

Improve production reliability before adding more product surface area by adding backend observability with Sentry, making frontend tests part of the production deployment gate, and documenting the minimum production configuration required for both.

## Scope

### In scope

- Add Sentry SDK to the FastAPI backend as an optional integration.
- Keep Sentry disabled when no DSN is configured.
- Configure environment and release metadata explicitly.
- Disable default PII collection.
- Avoid sending organization/store/customer identifiers automatically.
- Keep traces sampling conservative and configurable.
- Add tests that prove Sentry initialization is opt-in and privacy-safe.
- Add `npm test` to the production validation workflow before deployment.
- Document the environment variables needed to enable Sentry in production.

### Out of scope

- Frontend Sentry instrumentation; handle in a follow-up after backend rollout is verified.
- Performance tuning based on Sentry data before real data exists.
- Session Replay.
- User feedback widgets.
- Playwright/E2E setup; that is the next reliability slice.
- Automatic issue resolution or mutation through Sentry.
- Changes to business APIs, database schema, billing, Shopify, Knowledge, or AI behavior.

## Architecture

Create `backend/app/runtime/observability.py` as the single backend boundary for observability initialization. `main.py` calls this boundary during app bootstrap using validated settings. The module imports/configures Sentry but owns no business logic.

Settings remain in `backend/app/settings.py`:

- `sentry_dsn: str | None`
- `sentry_environment: str`
- `sentry_release: str | None`
- `sentry_traces_sample_rate: float`

Defaults must be safe: no DSN means no initialization, `send_default_pii=False`, and traces sampling defaults to `0.0` unless configured.

## Privacy and Security Requirements

- Never send auth headers, cookies, access tokens, OAuth secrets, API keys, message bodies, Knowledge source contents, or customer data intentionally.
- `send_default_pii` must remain `False`.
- Do not call `set_user` with email/name/customer identifiers as part of this phase.
- Do not add organization/store identifiers as global tags in this phase; add scoped, sanitized tags later only where operationally necessary.
- Sentry must never block FastAPI startup when unconfigured.

## CI Requirement

The production workflow currently runs frontend lint/build but not frontend tests. Change `.github/workflows/deploy-production.yml` so the `validate` job runs:

```bash
cd frontend
npm ci
npm run lint
npm test
npm run build
```

The deploy job must continue to depend on the validate job.

## Dependency

Pin `sentry-sdk[fastapi]==2.69.1` in `backend/requirements.txt` to match the repository's current exact-pinning style.

## Acceptance Criteria

- With an empty/missing DSN, Sentry initialization is skipped.
- With a DSN, Sentry is initialized with the configured environment/release/sample rate and `send_default_pii=False`.
- Invalid traces sample rates are rejected by settings validation or normalized safely before initialization.
- Existing FastAPI startup remains functional when Sentry is disabled.
- Backend tests cover the initialization contract without sending network traffic.
- Production deployment validation runs frontend tests before build/deploy.
- Required environment variables are documented.
