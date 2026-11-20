"""Keep the backend test suite fast.

Creating/dropping the full schema on an on-disk SQLite file costs ~2.5s per
test on Windows (fsync + antivirus scans of the .db file) versus milliseconds
in memory. Use `create_engine("sqlite://", poolclass=StaticPool,
connect_args={"check_same_thread": False})` instead.
"""
from pathlib import Path
import re

TESTS_DIR = Path(__file__).resolve().parent

# Files that intentionally need a file-backed database (keep this list short).
ALLOWED_FILE_DATABASES = {
    # Asserts that live extraction refuses a file-backed session; no schema is created.
    "test_shopify_privacy_processing.py",
}

_FILE_SQLITE = re.compile(r"sqlite:///(?!:memory:)")


def test_tests_do_not_use_on_disk_sqlite_databases():
    offenders = sorted(
        path.relative_to(TESTS_DIR).as_posix()
        for path in TESTS_DIR.rglob("test*.py")
        if path.name not in ALLOWED_FILE_DATABASES
        and path.name != Path(__file__).name
        and _FILE_SQLITE.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == [], (
        "Use an in-memory SQLite engine (sqlite:// + StaticPool) in tests; "
        f"on-disk databases make the suite ~4x slower: {offenders}"
    )
