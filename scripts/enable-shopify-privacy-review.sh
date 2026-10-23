#!/usr/bin/env bash
# Enables authenticated internal privacy review ONLY. No export/deletion.
# Run once as: sudo bash /opt/diaglob/app/scripts/enable-shopify-privacy-review.sh
set -Eeuo pipefail
umask 077

if [[ "$EUID" -ne 0 ]]; then
  echo "REVIEW_ROOT_REQUIRED" >&2
  exit 1
fi

APP_DIR=/opt/diaglob/app
ENV_FILE=/etc/diaglob/diaglob.env
LOCK=/tmp/diaglob-production-deploy.lock

if [[ ! -f "$ENV_FILE" || ! -r "$ENV_FILE" || ! -f "$LOCK" ]]; then
  echo "REVIEW_ENV_OR_DEPLOY_LOCK_MISSING" >&2
  exit 1
fi

# Open in read mode to avoid protected /tmp O_TRUNC permissions and serialize
# with the same deployment lock used by the API rollout.
exec 9< "$LOCK"
flock -w 120 9

BACKUP="$(mktemp /etc/diaglob/.diaglob-env-privacy-backup.XXXXXXXX)"
cp "$ENV_FILE" "$BACKUP"
chmod 600 "$BACKUP"

rollback() {
  status=$?
  trap - ERR
  cp "$BACKUP" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  systemctl restart diaglob-api.service || true
  rm -f "$BACKUP"
  echo "REVIEW_SECRET_ROLLBACK=attempted" >&2
  exit "$status"
}
trap rollback ERR

python3 "$APP_DIR/scripts/shopify_privacy_review_secret.py" "$ENV_FILE"
systemctl restart diaglob-api.service
bash "$APP_DIR/scripts/check-api-readiness.sh"

# Check that the newly started service process actually loaded this secret.
# Never print, hash, or return the token.
PID="$(systemctl show -p MainPID --value diaglob-api.service)"
python3 - "$PID" <<'PY'
import sys
from pathlib import Path

pid = int(sys.argv[1])
if pid <= 0:
    raise SystemExit("REVIEW_SERVICE_PID_INVALID")
records = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
values = [
    entry.partition(b"=")[2] for entry in records
    if entry.startswith(b"DIAGLOB_INTERNAL_SECRET=")
]
if len(values) != 1 or len(values[0]) < 40:
    raise SystemExit("REVIEW_SECRET_RUNTIME_NOT_VERIFIED")
print("REVIEW_SECRET_RUNTIME=verified")
PY

trap - ERR
rm -f "$BACKUP"
echo "REVIEW_INTERNAL_AUTH_ENABLED=true"
echo "PRIVACY_ERASURE_AUTHORIZED=false"
