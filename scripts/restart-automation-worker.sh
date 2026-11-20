#!/usr/bin/env bash
# Restart the automation worker so it runs the code that was just deployed.
#
# The API is restarted by /opt/diaglob/scripts/deploy.sh, but the worker that
# executes flows, campaigns and WhatsApp sends is a separate systemd service
# and kept running old code after every deploy. Flows/leases are durable:
# a restart only interrupts the current poll; leased work is reclaimed.
#
# Fails (non-zero) if the worker does not stay active, so the deploy job
# reports it instead of silently leaving automations stopped.
set -euo pipefail

SERVICE="${DIAGLOB_WORKER_SERVICE:-diaglob-automation-worker}"
STABLE_SECONDS="${DIAGLOB_WORKER_STABLE_SECONDS:-15}"

if ! systemctl list-unit-files "${SERVICE}.service" --no-legend 2>/dev/null | grep -q "^${SERVICE}.service"; then
  echo "SKIP: ${SERVICE}.service is not installed on this host."
  exit 0
fi

before_restarts="$(systemctl show -p NRestarts --value "$SERVICE")"
sudo systemctl restart "$SERVICE"
started_at="$(systemctl show -p ActiveEnterTimestamp --value "$SERVICE")"

# Active right after restart is not enough: require it to stay up without
# systemd auto-restarting it (Restart=always would hide a crash loop).
sleep "$STABLE_SECONDS"
state="$(systemctl is-active "$SERVICE" || true)"
restarts="$(systemctl show -p NRestarts --value "$SERVICE")"

if [[ "$state" != "active" || "$restarts" != "$before_restarts" ]]; then
  echo "FAIL: ${SERVICE} state=${state} restarts=${before_restarts}->${restarts} after deploy." >&2
  sudo journalctl -u "$SERVICE" --since "$started_at" --no-pager -o cat \
    | grep -viE 'token|secret|authorization|password' | tail -n 40 >&2 || true
  exit 1
fi

echo "OK: ${SERVICE} active since ${started_at}, stable for ${STABLE_SECONDS}s (restarts=${restarts})."
