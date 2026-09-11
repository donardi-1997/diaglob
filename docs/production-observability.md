# Diaglob Production Observability

This runbook defines the minimum backend observability configuration for Diaglob production.

## Backend Sentry

Sentry is optional and disabled by default. The API initializes Sentry only when `SENTRY_DSN` contains a non-empty value.

Configure these values in the production environment (currently `/etc/diaglob/diaglob.env`):

```bash
SENTRY_DSN=<backend-project-dsn>
SENTRY_ENVIRONMENT=production
SENTRY_RELEASE=diaglob@<git-sha>
SENTRY_TRACES_SAMPLE_RATE=0.05
```

### Variable contract

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `SENTRY_DSN` | No | empty | Enables backend Sentry when non-empty. |
| `SENTRY_ENVIRONMENT` | No | `development` | Separates production, staging, and development events. Set explicitly to `production` on the production host. |
| `SENTRY_RELEASE` | No | empty | Associates events with a deployed Diaglob revision. Prefer `diaglob@<git-sha>`. |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.0` | Transaction trace sample rate. Must be between `0.0` and `1.0`; production baseline is `0.05`. |

Leaving `SENTRY_DSN` empty disables Sentry without preventing FastAPI startup.

## Privacy defaults

The backend initializes Sentry with:

```python
send_default_pii=False
```

Phase 1 intentionally does **not** set Sentry user identity or global organization/store/customer tags.

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

1. Create or select the backend Sentry project.
2. Copy the project DSN into `/etc/diaglob/diaglob.env` as `SENTRY_DSN`.
3. Set `SENTRY_ENVIRONMENT=production`.
4. Set `SENTRY_RELEASE` to the deployed Git revision, for example `diaglob@abc1234`.
5. Start with `SENTRY_TRACES_SAMPLE_RATE=0.05` and adjust only from measured production needs.
6. Restart `diaglob-api` through the normal deployment workflow.
7. Verify `https://api.diaglob.tech/health` remains healthy.
8. Verify a controlled non-sensitive test event appears in the backend Sentry project before relying on Sentry for incident response.

Do not paste Sentry auth tokens or other credentials into issues, pull requests, logs, or chat messages.

## Release discipline

`SENTRY_RELEASE` should identify the same revision deployed by GitHub Actions. When release automation is added, prefer deriving it from the deployment commit SHA rather than maintaining the value manually.

## Incident review

Once the Sentry project and read-only API access are configured, review production issues by:

1. unresolved issue frequency;
2. last-seen recency;
3. affected release/environment;
4. whether the issue blocks activation, payments, Shopify/WhatsApp integration, AI replies, or order flow.

Use the severity definitions in `docs/pilot-runbook.md` for P0-P3 prioritization.
