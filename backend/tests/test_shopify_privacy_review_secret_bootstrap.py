"""No secrets in logs, no surprise rotations, no unsafe global enablement."""
import os
import importlib.util
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


def test_bootstrap_creates_secret_only_with_secure_permissions(tmp_path):
    file = tmp_path / "diaglob.env"
    file.write_text("DB_PASSWORD=do-not-leak\n", encoding="utf-8")
    os.chmod(file, 0o640)
    original = file.read_bytes()

    result = run(file)
    if not callable(getattr(os, "fchmod", None)):
        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr.strip() == "REVIEW_SECRET_BOOTSTRAP_FAILED"
        assert file.read_bytes() == original
        assert list(tmp_path.glob(".diaglob-review-secret-*")) == []
        return
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


def test_bootstrap_refuses_symlink_to_sensitive_file(tmp_path, monkeypatch):
    real = tmp_path / "real.env"
    real.write_text("DB_PASSWORD=separate-private\n")
    link = tmp_path / "link.env"
    try:
        link.symlink_to(real)
    except OSError as exc:
        if getattr(exc, "winerror", None) != 1314:
            raise
        # Windows may deny symlink creation without Developer Mode. Exercise
        # the same rejection branch in-process, not by skipping its assertions
        # or requiring elevated test privileges.
        spec = importlib.util.spec_from_file_location("review_secret", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original_is_symlink = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == link or original_is_symlink(path))
        with pytest.raises(ValueError, match="REVIEW_ENV_FILE_INVALID"):
            module.bootstrap_secret(link)
    else:
        result = run(link)
        assert result.returncode != 0
        assert "separate-private" not in result.stderr
    assert real.read_text() == "DB_PASSWORD=separate-private\n"


def test_no_secret_generated_when_secure_permissions_are_unavailable(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("review_secret", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    file = tmp_path / "diaglob.env"
    file.write_text("DB_PASSWORD=do-not-leak\n", encoding="utf-8")
    original = file.read_bytes()
    monkeypatch.setattr(module.os, "fchmod", None, raising=False)

    def forbidden_secret(*args, **kwargs):
        raise AssertionError("Secret generated without secure permissions")

    monkeypatch.setattr(module.secrets, "token_urlsafe", forbidden_secret)
    with pytest.raises(ValueError, match="REVIEW_SECURE_PERMISSIONS_UNAVAILABLE"):
        module.bootstrap_secret(file)
    assert file.read_bytes() == original
    assert list(tmp_path.glob(".diaglob-review-secret-*")) == []


def test_wrapper_never_prints_secret_and_preserves_manual_deletion_gate():
    source = WRAPPER.read_text(encoding="utf-8")
    assert 'exec 9< "$LOCK"' in source
    assert "flock -w 120 9" in source
    assert "REVIEW_SECRET_RUNTIME=verified" in source
    assert "PRIVACY_ERASURE_AUTHORIZED=false" in source
    assert "print(values[0])" not in source
    assert "echo ${DIAGLOB_INTERNAL_SECRET}" not in source
