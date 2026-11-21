"""The production audit runs as `python -m` without importing the full app.

pytest's conftest loads app.main, which hides missing model registrations, so
this check runs in a clean interpreter exactly like production does.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

SCRIPT = """
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import app.shopify_privacy_operational_audit as audit
from app.models import Store

engine = create_engine("sqlite://")
# Only the queried table; nothing else is registered by the test itself.
Store.__table__.create(engine)
with Session(engine) as db:
    active_with_tables = audit._active_processor_controls(db)
print(json.dumps({"active": sorted(active_with_tables)}))
"""


def test_processor_detection_works_without_full_app_import():
    env = {
        **os.environ,
        "DATABASE_URL": "sqlite:///:memory:",
        "KNOWLEDGE_RECONCILE_ON_STARTUP": "false",
        "PYTHONPATH": str(BACKEND),
    }
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=BACKEND, env=env,
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    # No stores exist: detection must succeed and find nothing active. A
    # mapper failure would fail closed and report every processor active.
    assert json.loads(result.stdout.strip().splitlines()[-1]) == {"active": []}
