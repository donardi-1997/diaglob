---
name: github-actions
description: Diagnose and repair Diaglob GitHub Actions validation and production deployment failures without bypassing CI gates or weakening tests.
compatibility: opencode
metadata:
  project: diaglob
  scope: ci
---

## Current production workflow

`.github/workflows/deploy-production.yml` runs on pushes to `main` and manual dispatch.

Validation currently performs:

1. checkout
2. Python 3.10 setup
3. backend dependency installation
4. `ruff check app/ tests/`
5. `python -m pytest -q --tb=short`
6. frontend `npm ci`
7. frontend `npm run build`

Deployment only runs after validation succeeds. It configures SSH from GitHub secrets and invokes `/opt/diaglob/scripts/deploy.sh` on production. A final job sends deployment status to Telegram.

## Debugging procedure

1. Identify the exact failed job and step.
2. Read the failure logs before editing workflow YAML.
3. If validation failed, reproduce the exact command locally/repository-side where possible.
4. Determine whether the cause is code, test state, dependency/version, CI environment, or workflow configuration.
5. Fix the root cause at the appropriate layer.
6. Do not bypass validation to deploy.

## Guardrails

- Never remove Ruff, pytest, or frontend build gates just to obtain a green workflow.
- Never add `|| true`, blanket `continue-on-error`, mass test exclusions, or equivalent bypasses for required validation.
- Never print or expose GitHub secrets, SSH private keys, Telegram tokens, or other credentials.
- Preserve `needs: validate` semantics for production deployment.
- Keep production concurrency protection unless there is a deliberate reason to change it.
- Changes to deployment commands require extra scrutiny because successful validation can trigger production deployment from `main`.

## Reporting

Explain whether the failure originated in application code or CI configuration, and provide the exact failing command plus the validation performed after the fix.
