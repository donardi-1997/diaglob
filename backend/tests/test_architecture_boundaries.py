"""Architecture boundary tests for Knowledge domain services.

These tests prevent services from importing HTTP-layer modules,
which would break the service extraction pattern.
"""
import importlib
import pkgutil
from pathlib import Path

import pytest

SERVICES_DIR = Path(__file__).resolve().parent.parent / "app" / "services"
FORBIDDEN_PREFIXES = ("app.api", "app.main")


def _iter_service_modules():
    """Yield importable module names under app.services."""
    import app.services as svc_pkg

    for importer, modname, ispkg in pkgutil.walk_packages(
        svc_pkg.__path__, prefix="app.services."
    ):
        yield modname


def _import_module_safe(modname: str):
    """Try importing a module; skip if it has unresolvable deps."""
    try:
        return importlib.import_module(modname)
    except Exception:
        return None


@pytest.mark.parametrize("modname", list(_iter_service_modules()))
def test_services_do_not_import_api_layer(modname: str):
    """Services must not import from app.api or app.main."""
    mod = _import_module_safe(modname)
    if mod is None:
        pytest.skip(f"Could not import {modname}")

    source = str(getattr(mod, "__file__", "")) or ""
    if not source:
        pytest.skip("No source file")

    try:
        text = Path(source).read_text(encoding="utf-8")
    except Exception:
        pytest.skip("Could not read source")

    for prefix in FORBIDDEN_PREFIXES:
        forbidden_import = f"from {prefix}"
        forbidden_import2 = f"import {prefix}"
        assert forbidden_import not in text, (
            f"{modname} imports from {forbidden_import}"
        )
        assert forbidden_import2 not in text, (
            f"{modname} imports {forbidden_import2}"
        )
