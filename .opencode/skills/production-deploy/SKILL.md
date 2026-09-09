---
name: production-deploy
description: Review and execute Diaglob production deployment work safely, including deploy workflow changes, SSH deployment behavior, migrations, service health, and rollback planning.
compatibility: opencode
metadata:
  project: diaglob
  scope: production
---

## Production safety

Production changes require evidence before action.

The repository workflow deploys only after validation and remotely invokes `/opt/diaglob/scripts/deploy.sh`. Treat changes affecting this path as high impact.

## Before changing deployment behavior

- Inspect `.github/workflows/deploy-production.yml`.
- Inspect repository-side assumptions relevant to the deployment.
- If the remote deploy script is not present in the repository/context, do not invent its contents or claim how it behaves.
- Identify database migration requirements and compatibility risks.
- Identify a rollback strategy for code and schema changes.

## Guardrails

- Never commit credentials, private keys, tokens, or environment files.
- Never echo secrets into logs.
- Never bypass the validation job to force deployment.
- Do not run destructive database commands without explicit authorization.
- Prefer backward-compatible schema/application sequencing.
- Do not claim production is healthy until a real health/status check has been observed.

## Post-deploy verification

When access is available, verify the relevant application health endpoint/service state and a small critical-path smoke test. For migration-bearing releases, verify migration state as well.

If production access is unavailable, clearly distinguish repository validation from production verification.
