"""Register all SQLAlchemy domain models before test fixtures create tables."""

import importlib
import sys
from pathlib import Path

import pytest

import app.models  # noqa: F401

_MODEL_DIR = Path(__file__).resolve().parents[1] / "app" / "model_domains"

for _module in sorted(_MODEL_DIR.glob("*.py")):
    if _module.stem != "__init__":
        importlib.import_module(f"app.model_domains.{_module.stem}")


@pytest.fixture(autouse=True)
def _isolate_global_app_dependency_overrides():
    """Never let one test's FastAPI overrides leak into another test.

    Tests override `app.main.app.dependency_overrides` (db, user, membership).
    A helper that forgets to restore them (e.g. a generator consumed with
    `next()` whose cleanup never runs) leaks objects bound to a closed
    session into whatever module runs next in the same process. Under
    pytest-xdist that order changes, which surfaced as a DetachedInstanceError
    in an unrelated module. app.main is imported lazily by tests that need
    it, so only guard it once it is loaded.
    """
    main = sys.modules.get("app.main")
    snapshot = dict(main.app.dependency_overrides) if main else None
    yield
    main = main or sys.modules.get("app.main")
    if main is None:
        return
    main.app.dependency_overrides.clear()
    if snapshot:
        main.app.dependency_overrides.update(snapshot)
