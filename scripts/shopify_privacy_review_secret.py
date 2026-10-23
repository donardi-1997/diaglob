#!/usr/bin/env python3
"""Generate the DIAGLOB internal operator secret safely without printing it.

Operational bootstrap only. NEVER authorizes live privacy export/redaction.
Accepts a file argument for tests, but production wrapper pins the env path.
"""
from __future__ import annotations

import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path


KEY = "DIAGLOB_INTERNAL_SECRET"
ENTRY = re.compile(r"^\s*(?:export\s+)?" + KEY + r"\s*=\s*(.*)$", re.MULTILINE)


def bootstrap_secret(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("REVIEW_ENV_FILE_INVALID")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("REVIEW_ENV_FILE_INVALID")
    original = path.read_text(encoding="utf-8")
    matches = list(ENTRY.finditer(original))
    if len(matches) > 1:
        raise ValueError("REVIEW_SECRET_DUPLICATE")
    if matches:
        if not matches[0].group(1).strip():
            raise ValueError("REVIEW_SECRET_EMPTY")
        # Existing configured secrets must NOT be printed or rotated.
        return "present"

    new_secret = secrets.token_urlsafe(48)
    data = original.rstrip("\n") + "\n" + KEY + "=" + new_secret + "\n"
    fd, temp_path = tempfile.mkstemp(
        prefix=".diaglob-review-secret-", dir=str(path.parent)
    )
    try:
        os.fchmod(fd, 0o600)
        if hasattr(os, "fchown"):
            os.fchown(fd, info.st_uid, info.st_gid)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise
    return "created"


def main() -> int:
    if len(sys.argv) != 2:
        print("REVIEW_ENV_PATH_REQUIRED", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if str(path) == "/etc/diaglob/diaglob.env" and os.geteuid() != 0:
        print("REVIEW_ROOT_REQUIRED", file=sys.stderr)
        return 2
    try:
        status = bootstrap_secret(path)
    except (OSError, ValueError):
        # Never leak filesystem paths or existing secret values into logs.
        print("REVIEW_SECRET_BOOTSTRAP_FAILED", file=sys.stderr)
        return 2
    print("REVIEW_SECRET_STATUS=" + status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
