"""Register all SQLAlchemy domain models before test fixtures create tables."""

import importlib
from pathlib import Path

import app.models  # noqa: F401

_MODEL_DIR = Path(__file__).resolve().parents[1] / "app" / "model_domains"

for _module in sorted(_MODEL_DIR.glob("*.py")):
    if _module.stem != "__init__":
        importlib.import_module(f"app.model_domains.{_module.stem}")
