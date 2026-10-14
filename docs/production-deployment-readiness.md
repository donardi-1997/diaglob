# DIAGLOB — production readiness-gated deployments

## Observed incident (2026-10-14)

The API returned a transient Nginx **502** while systemd was restarting
Uvicorn on `127.0.0.1:8000`. The preceding automation had two
database-migration stages and an extra `systemctl restart` **after** the
existing deploy script. Because `systemctl is-active` can succeed before
Uvicorn finishes startup, immediate curl checks can fail for a few seconds.

## Changes to automated production deployment

- Keep the existing `/opt/diaglob/scripts/deploy.sh` as-is: its contents are
  maintained outside this repository and must be audited before replacement.
- Run pre-deploy migrations **once within the workflow** in the existing
  "Prepare production schema before restart" stage. Remove the redundant
  post-deploy migrations and second explicit restart. The external `deploy.sh`
  has not been audited for any migration behavior of its own.
- Continue serializing GitHub deployments using
  `concurrency: diaglob-production` and use the advisory remote lock
  `/tmp/diaglob-production-deploy.lock` during the legacy deploy script.
- If that script exits with code 22 from its immediate health check, recovery
  is accepted ONLY after the independent upstream and public HTTPS readiness
  probes pass. All other non-zero codes remain fatal.
- Both probes require HTTP 200 and exact structured signals:
  `status=ok`, `service=diaglob-api`, `database=connected`,
  `multitenant=true`, `multistore=true`. Defaults: 20 attempts,
  3-second delay, 6-second HTTP timeout per attempt.
- On a failed probe, CI reports a failure and only systemd metadata; detailed
  logs are available on the server to avoid disclosing private data in CI.
- PR and production validation run offline regression tests for the helper.

**Important:** health gating and fewer restarts REDUCE the incidence and
duration of 502s. They do NOT guarantee zero downtime on a single Uvicorn
instance. Zero-downtime deploys need an independently validated blue/green
upstream or equivalent and a careful Nginx switch.

## Normal deployment

Prefer the existing GitHub Actions "Deploy Production" run after merging
to `main`. Avoid manually running `git pull` followed by an additional
`systemctl restart` when the workflow already deployed the commit:
that causes an unnecessary second interruption.

Do not run a second manual deployment while GitHub Actions is preparing
dependencies/migrations; the advisory host lock covers the deploy script
and the checked-in manual restart helper, not the entire multi-job workflow.

## Manual recovery/restart (only when necessary)

From the server, with the desired commit already deployed:

```bash
cd /opt/diaglob/app
bash scripts/restart-api-verified.sh
git log -1 --oneline
```

This helper takes the advisory host lock, restarts the API only once, then
checks both the local Uvicorn health and public HTTPS. It does not fetch
code or run migrations. It intentionally fails rather than claiming success
when the database or service is unavailable.

For non-mutating diagnosis:

```bash
sudo systemctl status diaglob-api.service --no-pager -l
sudo journalctl -u diaglob-api.service -n 80 --no-pager
sudo tail -n 50 /var/log/nginx/error.log
```

Do not copy secret-bearing log contents or environment files into CI.
If a deployment fails with migrations applied, do NOT blindly reset to an
older commit: review schema compatibility and the recovery procedure first.

## Next stage: zero-downtime deployment

Before switching Nginx upstreams, inspect actual server-managed
`/opt/diaglob/scripts/deploy.sh`, its Nginx configuration, and existing
systemd units. Validate that there is sufficient memory to briefly run two
Uvicorn instances. Implement standby readiness checks, an atomic Nginx
switch, a drain window for in-flight requests and a tested rollback.
