#!/usr/bin/env bash
# Enables permit-gated Shopify privacy processing. Nothing runs by itself:
# every export or redaction still needs a per-case permit signed offline.
#
#   sudo bash /opt/diaglob/app/scripts/enable-shopify-privacy-processing.sh \
#     <attestation_public_key_b64url> <execution_public_key_b64url>
#
# Idempotent. Never prints secret values. The suppression key is generated
# once and NEVER rotated: active tombstones are keyed by it.
set -Eeuo pipefail
umask 077

if [[ "$EUID" -ne 0 ]]; then
  echo "PRIVACY_ENABLE_ROOT_REQUIRED" >&2
  exit 1
fi
if [[ $# -ne 2 ]]; then
  echo "USAGE: enable-shopify-privacy-processing.sh <attestation_pub> <execution_pub>" >&2
  exit 1
fi

APP_DIR=/opt/diaglob/app
ENV_FILE=/etc/diaglob/diaglob.env
LOCK=/tmp/diaglob-production-deploy.lock
PY="$APP_DIR/backend/.venv/bin/python"

if [[ ! -f "$ENV_FILE" || ! -f "$LOCK" ]]; then
  echo "PRIVACY_ENV_OR_DEPLOY_LOCK_MISSING" >&2
  exit 1
fi

exec 9< "$LOCK"
flock -w 120 9

BACKUP="$(mktemp /etc/diaglob/.diaglob-env-privacy-processing-backup.XXXXXXXX)"
cp "$ENV_FILE" "$BACKUP"
chmod 600 "$BACKUP"

rollback() {
  status=$?
  trap - ERR
  cp "$BACKUP" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  systemctl restart diaglob-api.service diaglob-automation-worker.service || true
  rm -f "$BACKUP"
  echo "PRIVACY_PROCESSING_ROLLBACK=attempted" >&2
  exit "$status"
}
trap rollback ERR

"$PY" - "$ENV_FILE" "$1" "$2" "$APP_DIR/config/shopify-privacy-policy.json" <<'PY'
import base64
import hashlib
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

env_path, attestation_pub, execution_pub, policy_path = sys.argv[1:5]


def valid_public_key(value: str) -> str:
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    Ed25519PublicKey.from_public_bytes(raw)
    return value


if valid_public_key(attestation_pub) == valid_public_key(execution_pub):
    raise SystemExit("PRIVACY_KEYS_MUST_DIFFER")

lines = Path(env_path).read_text(encoding="utf-8").splitlines()
current = {}
for line in lines:
    name, sep, value = line.partition("=")
    if sep and not line.lstrip().startswith("#"):
        current[name.strip()] = value

updates = {
    "SHOPIFY_PRIVACY_ATTESTATION_PUBLIC_KEY": attestation_pub,
    "SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY": execution_pub,
    "SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256": hashlib.sha256(
        Path(policy_path).read_bytes()).hexdigest(),
    "SHOPIFY_PRIVACY_PROCESSING_ENABLED": "true",
}
existing_key = current.get("SHOPIFY_PRIVACY_SUPPRESSION_KEY", "")
if len(existing_key.encode()) < 32:
    updates["SHOPIFY_PRIVACY_SUPPRESSION_KEY"] = secrets.token_urlsafe(48)

kept = [line for line in lines if line.partition("=")[0].strip() not in updates]
kept += [f"{name}={value}" for name, value in updates.items()]
Path(env_path).write_text("\n".join(kept) + "\n", encoding="utf-8")
print("PRIVACY_ENV_UPDATED=" + ",".join(sorted(updates)))
PY

systemctl restart diaglob-api.service diaglob-automation-worker.service
bash "$APP_DIR/scripts/check-api-readiness.sh"

# Verify the running API loaded every setting, without printing values.
PID="$(systemctl show -p MainPID --value diaglob-api.service)"
"$PY" - "$PID" <<'PY'
import sys
from pathlib import Path

pid = int(sys.argv[1])
if pid <= 0:
    raise SystemExit("PRIVACY_SERVICE_PID_INVALID")
loaded = {
    entry.partition(b"=")[0].decode()
    for entry in Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    if entry.partition(b"=")[2]
}
required = {
    "SHOPIFY_PRIVACY_ATTESTATION_PUBLIC_KEY", "SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY",
    "SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256", "SHOPIFY_PRIVACY_PROCESSING_ENABLED",
    "SHOPIFY_PRIVACY_SUPPRESSION_KEY",
}
missing = sorted(required - loaded)
if missing:
    raise SystemExit("PRIVACY_RUNTIME_MISSING=" + ",".join(missing))
print("PRIVACY_RUNTIME=verified")
PY

trap - ERR
rm -f "$BACKUP"
echo "PRIVACY_PROCESSING_ENABLED=true"
echo "PER_CASE_PERMIT_REQUIRED=true"
