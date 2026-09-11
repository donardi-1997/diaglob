# Diaglob Production Observability

This runbook defines the minimum backend and frontend observability configuration for Diaglob production.

## Backend Sentry

Sentry is optional and disabled by default. The API initializes Sentry only when `SENTRY_DSN` contains a non-empty value.

Configure these values in the production environment (currently `/etc/diaglob/diaglob.env`):

```bash
SENTRY_DSN=<backend-project-dsn>
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=diaglob@<git-sha>
SENTRY_TRACES_SAMPLE_RATE=0.05
```

### Backend variable contract

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SENTRY_DSN` | No | empty | Enables backend Sentry when non-empty. |
| `SENTRY_ENVIRONMENT` | No | `development` | Separates production, staging, and development events. Set explicitly to `production` on the production host. |
| `SENTRY_RELEASE` | No | empty | Associates events with a deployed Diaglob revision. Prefer `diaglob@<git-sha>`. |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.0` | Transaction trace sample rate. Must be between `0.0` and `1.0`; production baseline is `0.05`. |

Leaving `SENTRY_DSN` empty disables Sentry without preventing FastAPI startup.

## Frontend Sentry

The React application uses the same opt-in model. Frontend Sentry initializes only when `VITE_SENTRY_DSN` is non-empty.

These values are Vite build-time variables and therefore must be present in the environment that executes the production frontend build:

```bash
VITE_SENTRY_DSN=<frontend-project-dsn>
VITE_SENTRY_ENVIRONMENT=production
VITE_SENTRY_RELEASE=diaglob@<git-sha>
VITE_SENTRY_TRACES_SAMPLE_RATE=0.05
```

### Frontend variable contract

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `VITE_SENTRY_DSN` | No | empty | Enables frontend Sentry when non-empty. |
| `VITE_SENTRY_ENVIRONMENT` | No | omitted | Separates production, staging, and development browser events. |
| `VITE_SENTRY_RELEASE` | No | omitted | Associates browser events with the deployed Diaglob revision. Prefer the same `diaglob@<git-sha>` used by the backend. |
| `VITE_SENTRY_TRACES_SAMPLE_RATE` | No | `0.0` | Browser transaction trace sample rate. Values outside `0.0` to `1.0` fall back to `0.0`; production baseline is `0.05`. |

Leaving `VITE_SENTRY_DSN` empty keeps the frontend SDK inactive. The application still renders normally.

The frontend initializes Sentry before React mounts and wraps the application tree in `Sentry.ErrorBoundary`. A render failure displays a minimal reload action rather than leaving the user on a blank screen.

Session Replay is intentionally disabled in this phase.

## Privacy defaults

Both frontend and backend initialize Sentry with PII collection disabled:

```text
sendDefaultPii / send_default_pii = false
```

This phase intentionally does **not** set Sentry user identity or global organization/store/customer tags.

Do not intentionally send any of the following to Sentry:

- authorization headers or cookies;
- OAuth/access tokens;
- API keys or provider secrets;
- passwords or raw credentials;
- customer message bodies;
- Knowledge source contents;
- customer email, phone, address, or other PII.

If scoped operational tags are added later, they must be sanitized and reviewed before production rollout.

## Deployment procedure

1. Create or select separate backend and frontend Sentry projects, or intentionally use one project if that is the operational policy.
2. Configure `SENTRY_DSN` for the API and `VITE_SENTRY_DSN` for the frontend build environment.
3. Set both environments to `production`.
4. Set both release values to the same deployed Git revision, for example `diaglob@abc1234`.
5. Start both trace sample rates at `0.05` and adjust only from measured production needs.
6. Build the frontend after the `VITE_` variables are available; changing them after the bundle is built has no effect.
7. Restart/deploy through the normal production workflow.
8. Verify `https://api.diaglob.tech/health` remains healthy and the frontend loads normally.
9. Verify controlled, non-sensitive backend and frontend test events appear in Sentry before relying on it for incident response.

Do not paste Sentry auth tokens or other credentials into issues, pull requests, logs, or chat messages. A DSN is an ingestion endpoint rather than an administrative token, but it should still be managed through deployment configuration rather than hard-coded into the repository.

## Release discipline

`SENTRY_RELEASE` and `VITE_SENTRY_RELEASE` should identify the same revision deployed by GitHub Actions. Prefer `diaglob@<git-sha>` for both surfaces.

The frontend release value is embedded at build time. When release automation is expanded, derive both release values from the deployment commit SHA rather than maintaining either value manually.

## Incident review

Once the Sentry projects and read-only API access are configured, review production issues by:

1. unresolved issue frequency;
2. last-seen recency;
3. affected release/environment;
4. whether the issue blocks activation, payments, Shopify/WhatsApp integration, AI replies, or order flow.

Use the severity definitions in `docs/pilot-runbook.md` for P0-P3 prioritization.
