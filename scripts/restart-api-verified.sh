#!/usr/bin/env bash
# Manual restart when needed. CI uses the same advisory deployment lock.
# NOTE: A single-instance restart still causes a brief upstream gap.
set -euo pipefail

cd /opt/diaglob/app
exec 9>/tmp/diaglob-production-deploy.lock
if ! flock -w 120 9; then
  echo 'Another DIAGLOB deployment or restart is already in progress' >&2
  exit 1
fi

echo 'Restarting DIAGLOB API under deployment lock...'
sudo -n systemctl restart diaglob-api.service

# Require real Uvicorn readiness, not just systemd ActiveState.
bash scripts/check-api-readiness.sh

# Also verify public Nginx/TLS after the upstream is ready.
DIAGLOB_HEALTH_URL=https://api.diaglob.tech/health \
  DIAGLOB_READINESS_REQUIRE_SERVICE=0 \
  bash scripts/check-api-readiness.sh

echo 'PASS: API restart completed and HTTPS readiness verified'
