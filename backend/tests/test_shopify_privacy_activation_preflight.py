"""Guard the production privacy-activation script against self-approval."""
from pathlib import Path
import shutil
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "enable-shopify-privacy-processing.sh"


def test_activation_script_has_no_self_approved_policy_or_rotated_suppression_key():
    data = SCRIPT.read_text(encoding="utf-8")
    assert 'current.get("SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256") != policy_digest' in data
    assert 'PRIVACY_INDEPENDENT_POLICY_APPROVAL_REQUIRED' in data
    assert 'PRIVACY_PERSISTENT_SUPPRESSION_KEY_REQUIRED' in data
    assert 'PRIVACY_INDEPENDENT_RESTORE_CHECKPOINT_REQUIRED' in data
    assert 'PRIVACY_LEGAL_REVIEW_KEY_REQUIRED' in data
    assert 'PRIVACY_LEGAL_REVIEW_INDEPENDENCE_REQUIRED' in data
    assert 'secrets.token_urlsafe' not in data
    assert '"SHOPIFY_PRIVACY_OPERATOR_APPROVED_POLICY_SHA256": hashlib.sha256' not in data
    assert 'SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS' in data
    assert 'SHOPIFY_PRIVACY_WORM_LEDGER_BUCKET' in data
    assert 'SHOPIFY_PRIVACY_WORM_LEDGER_PREFIX' in data
    assert 'SHOPIFY_PRIVACY_WORM_LEDGER_PUBLIC_KEY' in data
    assert 'PRIVACY_WORM_LEDGER_PREFLIGHT_FAILED' in data
    assert 'PRIVACY_WORM_LEDGER_PREFLIGHT=verified' in data
    assert 'verify_worm_ledger(' in data
    assert 'minimum_remaining_days=int(retention_horizon)' in data
    assert 'PRIVACY_WORM_RETENTION_HORIZON_REQUIRED' in data
    assert 'SHOPIFY_PRIVACY_WORM_MIN_REMAINING_DAYS' in data
    assert 'verify_shopify_suppression_restore(' in data
    assert 'anchor["last_checkpoint_hmac"] != checkpoint' in data
    assert 'anchor["last_policy_sha256"] != policy_digest' in data


def test_embedded_activation_python_has_valid_syntax():
    data = SCRIPT.read_text(encoding="utf-8")
    part = data.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
    compile(part, str(SCRIPT), "exec")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash unavailable")
def test_activation_bash_has_valid_syntax():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
