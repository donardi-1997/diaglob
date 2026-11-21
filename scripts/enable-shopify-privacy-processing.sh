#!/usr/bin/env bash
# Enables permit-gated Shopify privacy processing. Nothing runs by itself:
# every export or redaction still needs a per-case permit signed offline.
# Prerequisites (set independently beforehand): legal-policy approval, unique
# legal reviewer key, suppression key and offsite restore checkpoint. This
# script MUST NEVER self-approve a policy or bootstrap the tombstone key.
#
#   sudo bash /opt/diaglob/app/scripts/enable-shopify-privacy-processing.sh \
#     <attestation_public_key_b64url> <execution_public_key_b64url>
#
# Idempotent. Never prints secret values. The suppression key must already
# exist and NEVER be rotated: active tombstones are keyed by it.
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
  # A failed read-only ledger preflight must not restart services using the
  # old (possibly restored) environment. Roll back only if we actually edited
  # the environment file.
  if ! cmp -s "$BACKUP" "$ENV_FILE"; then
    cp "$BACKUP" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    systemctl restart diaglob-api.service diaglob-automation-worker.service || true
    echo "PRIVACY_PROCESSING_ROLLBACK=env_restored" >&2
  else
    echo "PRIVACY_PROCESSING_BLOCKED=preflight_failed_without_restart" >&2
  fi
  rm -f "$BACKUP"
  exit "$status"
}
trap rollback ERR

"$PY" - "$ENV_FILE" "$1" "$2" "$APP_DIR/config/shopify-privacy-policy.json" "$APP_DIR/backend" <<'PY'
import base64
import hashlib
import os
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

env_path, attestation_pub, execution_pub, policy_path, backend_path = sys.argv[1:6]


def valid_public_key(value: str) -> str:
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    Ed25519PublicKey.from_public_bytes(raw)
    return value


attestation_pub = valid_public_key(attestation_pub)
execution_pub = valid_public_key(execution_pub)
if attestation_pub == execution_pub:
    raise SystemExit("PRIVACY_KEYS_MUST_DIFFER")

lines = Path(env_path).read_text(encoding="utf-8").splitlines()
current = {}
for line in lines:
    name, sep, value = line.partition("=")
    if sep and not line.lstrip().startswith("#"):
        current[name.strip()] = value

# Fail closed: legal and restore clearance must predate activation.
# A digest written automatically by this script is NOT a human approval.
policy_digest = hashlib.sha256(
    Path(policy_path).read_bytes().replace(b"\r\n", b"\n")
).hexdigest()
if current.get("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256") != policy_digest:
    raise SystemExit("PRIVACY_INDEPENDENT_POLICY_APPROVAL_REQUIRED")
review_pub = current.get("SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY", "")
try:
    valid_public_key(review_pub)
except Exception:
    raise SystemExit("PRIVACY_LEGAL_REVIEW_KEY_REQUIRED") from None
if review_pub in {attestation_pub, execution_pub}:
    raise SystemExit("PRIVACY_LEGAL_REVIEW_INDEPENDENCE_REQUIRED")
if len(current.get("SHOPIFY_PRIVACY_SUPPRESSION_KEY", "").encode()) < 32:
    raise SystemExit("PRIVACY_PERSISTENT_SUPPRESSION_KEY_REQUIRED")
checkpoint = current.get("SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC", "")
minimum = current.get("SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS", "")
if not re.fullmatch(r"[0-9a-f]{64}", checkpoint):
    raise SystemExit("PRIVACY_INDEPENDENT_RESTORE_CHECKPOINT_REQUIRED")
if not minimum.isascii() or not minimum.isdecimal() or int(minimum) < 0:
    raise SystemExit("PRIVACY_RESTORE_RECORD_COUNT_REQUIRED")

# The signed WORM ledger must be fetched directly from an independent S3
# bucket before processing is enabled. Comparing an env checkpoint only with
# the database is unsafe if both were restored to the same old snapshot.
bucket = current.get("SHOPIFY_PRIVACY_WORM_LEDGER_BUCKET", "")
prefix = current.get("SHOPIFY_PRIVACY_WORM_LEDGER_PREFIX", "")
ledger_key = current.get("SHOPIFY_PRIVACY_WORM_LEDGER_PUBLIC_KEY", "")
retention_horizon = current.get("SHOPIFY_PRIVACY_WORM_MIN_REMAINING_DAYS", "")
if (not retention_horizon.isascii() or not retention_horizon.isdecimal()
        or not 1 <= int(retention_horizon) <= 3650):
    raise SystemExit("PRIVACY_WORM_RETENTION_HORIZON_REQUIRED")
try:
    if not bucket or not prefix:
        raise ValueError
    valid_public_key(ledger_key)
except Exception:
    raise SystemExit("PRIVACY_WORM_LEDGER_CONFIGURATION_REQUIRED") from None
if ledger_key in {attestation_pub, execution_pub, review_pub}:
    raise SystemExit("PRIVACY_WORM_LEDGER_SIGNER_INDEPENDENCE_REQUIRED")

# EnvironmentFile is read as key=value by the existing activation script;
# propagate trusted root-owned settings before importing app DB configuration.
# No values, tokens, raw selectors, or customer content are logged.
os.environ.update(current)
sys.path.insert(0, backend_path)
try:
    import boto3
    from app.db import SessionLocal
    from app.services.shopify_privacy_restore import verify_shopify_suppression_restore
    from app.services.shopify_privacy_worm_ledger import verify_worm_ledger
    public = Ed25519PublicKey.from_public_bytes(
        base64.b64decode(ledger_key + "=" * (-len(ledger_key) % 4), altchars=b"-_", validate=True)
    )
    s3 = boto3.client(
        "s3", region_name=current.get("AWS_REGION", current.get("AWS_DEFAULT_REGION", "us-east-2"))
    )
    anchor = verify_worm_ledger(
        s3, bucket=bucket, prefix=prefix, public_key=public,
        minimum_remaining_days=int(retention_horizon),
    )
    if (anchor["record_count"] <= 0
            or anchor["last_checkpoint_hmac"] != checkpoint
            or anchor["last_min_records"] != int(minimum)
            or anchor["last_policy_sha256"] != policy_digest):
        raise RuntimeError("WORM_LEDGER_HEAD_MISMATCH")
    with SessionLocal() as db:
        restored = verify_shopify_suppression_restore(
            db, externally_stored_hmac=anchor["last_checkpoint_hmac"],
            minimum_records=anchor["last_min_records"],
        )
    if restored["recovery_verified"] is not True:
        raise RuntimeError("WORM_LEDGER_RESTORE_FAILED")
except Exception:
    raise SystemExit("PRIVACY_WORM_LEDGER_PREFLIGHT_FAILED") from None
print("PRIVACY_WORM_LEDGER_PREFLIGHT=verified")

updates = {
    "SHOPIFY_PRIVACY_ATTESTATION_PUBLIC_KEY": attestation_pub,
    "SHOPIFY_PRIVACY_EXECUTION_PUBLIC_KEY": execution_pub,
    "SHOPIFY_PRIVACY_PROCESSING_ENABLED": "true",
}

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
    "SHOPIFY_PRIVACY_SUPPRESSION_KEY", "SHOPIFY_PRIVACY_LEGAL_REVIEW_PUBLIC_KEY",
    "SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC", "SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS",
    "SHOPIFY_PRIVACY_WORM_LEDGER_BUCKET", "SHOPIFY_PRIVACY_WORM_LEDGER_PREFIX",
    "SHOPIFY_PRIVACY_WORM_LEDGER_PUBLIC_KEY",
    "SHOPIFY_PRIVACY_WORM_MIN_REMAINING_DAYS",
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
