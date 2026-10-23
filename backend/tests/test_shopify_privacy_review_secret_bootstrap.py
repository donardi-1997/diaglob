"""No secrets in logs, no surprise rotations, no unsafe global enablement."""
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "shopify_privacy_review_secret.py"
WRAPPER = ROOT / "scripts" / "enable-shopify-privacy-review.sh"


def run(path: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True, text=True, check=False,
    )


def test_bootstrap_creates_random_internal_secret_without_logging_it(tmp_path):
    file = tmp_path / "diaglob.env"
    file.write_text("DB_PASSWORD=do-not-leak\n", encoding="utf-8")
    os.chmod(file, 0o640)

    result = run(file)
    assert result.returncode == 0
    assert result.stdout.strip() == "REVIEW_SECRET_STATUS=created"
    assert result.stderr == ""
    content = file.read_text(encoding="utf-8")
    match = re.search(r"^DIAGLOB_INTERNAL_SECRET=([A-Za-z0-9_-]+)$", content, re.M)
    assert match and len(match.group(1)) >= 40
    assert match.group(1) not in result.stdout
    assert "do-not-leak" not in result.stdout
    assert "DB_PASSWORD=do-not-leak" in content
    assert stat.S_IMODE(file.stat().st_mode) == 0o600


def test_bootstrap_is_idempotent_and_never_rotates_existing_secret(tmp_path):
    file = tmp_path / "diaglob.env"
    file.write_text("DIAGLOB_INTERNAL_SECRET=existing-operator-secret\n")
    original = file.read_bytes()
    result = run(file)
    assert result.returncode == 0
    assert result.stdout.strip() == "REVIEW_SECRET_STATUS=present"
    assert file.read_bytes() == original


@pytest.mark.parametrize(
    "contents",
    [
        "DIAGLOB_INTERNAL_SECRET=\n",
        "DIAGLOB_INTERNAL_SECRET=one\nDIAGLOB_INTERNAL_SECRET=two\n",
    ],
)
def test_invalid_existing_secret_fails_without_modifying_file(tmp_path, contents):
    file = tmp_path / "diaglob.env"
    file.write_text(contents)
    result = run(file)
    assert result.returncode != 0
    assert result.stderr.strip() == "REVIEW_SECRET_BOOTSTRAP_FAILED"
    assert file.read_text() == contents


def test_bootstrap_refuses_symlink_to_sensitive_file(tmp_path):
    real = tmp_path / "real.env"
    real.write_text("DB_PASSWORD=separate-private\n")
    link = tmp_path / "link.env"
    link.symlink_to(real)
    result = run(link)
    assert result.returncode != 0
    assert real.read_text() == "DB_PASSWORD=separate-private\n"
    assert "separate-private" not in result.stderr


def test_wrapper_never_prints_secret_and_preserves_manual_deletion_gate():
    source = WRAPPER.read_text(encoding="utf-8")
    assert 'exec 9< "$LOCK"' in source
    assert "flock -w 120 9" in source
    assert "REVIEW_SECRET_RUNTIME=verified" in source
    assert "PRIVACY_ERASURE_AUTHORIZED=false" in source
    assert "print(values[0])" not in source
    assert "echo ${DIAGLOB_INTERNAL_SECRET}" not in source
