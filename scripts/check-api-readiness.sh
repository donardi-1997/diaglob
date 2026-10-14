#!/usr/bin/env bash
# Fail-closed DIAGLOB API readiness gate; safe for localhost or public HTTPS.
set -euo pipefail

url="${DIAGLOB_HEALTH_URL:-http://127.0.0.1:8000/health}"
attempts="${DIAGLOB_HEALTH_ATTEMPTS:-20}"
interval="${DIAGLOB_HEALTH_INTERVAL:-3}"
require_service="${DIAGLOB_READINESS_REQUIRE_SERVICE:-1}"

# Reject malformed inputs and unbounded waits.
if [[ ! "$attempts" =~ ^[1-9][0-9]?$ ]] || \
   [[ ! "$interval" =~ ^(0|[1-9][0-9]?)$ ]] || \
   [[ "$require_service" != 0 && "$require_service" != 1 ]]; then
  echo 'Invalid readiness configuration' >&2
  exit 2
fi
if (( attempts > 60 || interval > 30 )); then
  echo 'Invalid readiness configuration' >&2
  exit 2
fi
if [[ "$url" != http://127.0.0.1:8000/health && "$url" != https://api.diaglob.tech/health ]]; then
  echo 'Readiness URL is not an approved DIAGLOB endpoint' >&2
  exit 2
fi

for (( attempt=1; attempt<=attempts; attempt++ )); do
  # Do not print or persist the health response.
  if body="$(curl --fail --silent --show-error --connect-timeout 2 --max-time 6 "$url" 2>/dev/null)" && \
     printf '%s' "$body" | python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
    valid = (isinstance(payload, dict)
             and payload.get("status") == "ok"
             and payload.get("service") == "diaglob-api"
             and payload.get("database") == "connected"
             and payload.get("multitenant") is True
             and payload.get("multistore") is True)
except (ValueError, TypeError):
    valid = False
sys.exit(0 if valid else 1)
' ; then
    if [[ "$require_service" == 0 ]] || systemctl is-active --quiet diaglob-api.service; then
      echo "PASS: DIAGLOB API ready on attempt $attempt/$attempts ($url)"
      exit 0
    fi
  fi
  echo "WAIT: DIAGLOB API not ready ($attempt/$attempts)" >&2
  if (( attempt < attempts )); then
    sleep "$interval"
  fi
done

echo "FAIL: DIAGLOB API readiness deadline exceeded ($url)" >&2
if [[ "$require_service" == 1 ]]; then
  # Only metadata in CI logs; journal entries might include personal data.
  systemctl show diaglob-api.service \
    --property=ActiveState,SubState,MainPID,ExecMainStatus,NRestarts --no-pager >&2 || true
  echo 'Inspect sudo journalctl -u diaglob-api.service -n 80 --no-pager on the server.' >&2
fi
exit 1
