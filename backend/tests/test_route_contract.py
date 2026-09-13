"""Route contract guard test.

Verifies the runtime route set matches the committed snapshot.
Fails on any unexpected route addition, removal, or method change.

To update the snapshot intentionally:
1. Change code
2. Run: python -m pytest tests/test_route_contract.py --update-snapshot
3. Review the diff to tests/contracts/api_routes.json
4. Commit both code and snapshot changes
"""
import json
from pathlib import Path

import pytest

CONTRACT_PATH = (
    Path(__file__).resolve().parent / "contracts" / "api_routes.json"
)


def _collect_routes_from_container(container) -> list[tuple[str, str]]:
    """Recursively collect (method, path) from a route container.

    Handles both classic Route objects and FastAPI's _IncludedRouter
    wrappers that nest an APIRouter under ``original_router``.
    """
    routes: list[tuple[str, str]] = []
    for route in container.routes:
        if hasattr(route, "original_router"):
            routes.extend(
                _collect_routes_from_container(route.original_router)
            )
        elif hasattr(route, "path") and hasattr(route, "methods"):
            for method in sorted(route.methods or {"GET"}):
                routes.append((method, route.path))
        elif hasattr(route, "routes"):
            routes.extend(_collect_routes_from_container(route))
    return routes


def _get_runtime_routes() -> list[tuple[str, str]]:
    """Extract sorted unique (method, path) from the running app."""
    from app.main import app

    return sorted(set(_collect_routes_from_container(app)))


def _load_snapshot() -> list[tuple[str, str]]:
    """Load the committed route contract snapshot."""
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return [tuple(item) for item in data]


def _save_snapshot(routes: list[tuple[str, str]]):
    """Save routes to the contract snapshot file."""
    CONTRACT_PATH.write_text(
        json.dumps(routes, indent=2) + "\n",
        encoding="utf-8",
    )


class TestRouteContract:
    def test_route_set_matches_snapshot(self):
        """Runtime routes must exactly match the committed snapshot."""
        actual = _get_runtime_routes()
        expected = _load_snapshot()

        actual_set = set(actual)
        expected_set = set(expected)

        missing = expected_set - actual_set
        unexpected = actual_set - expected_set

        if missing or unexpected:
            msg_parts = []
            if missing:
                msg_parts.append(f"MISSING routes ({len(missing)}):")
                for method, path in sorted(missing):
                    msg_parts.append(f"  - {method} {path}")
            if unexpected:
                msg_parts.append(f"UNEXPECTED routes ({len(unexpected)}):")
                for method, path in sorted(unexpected):
                    msg_parts.append(f"  + {method} {path}")
            pytest.fail("\n".join(msg_parts))

    def test_route_count(self):
        """Sanity check on route count."""
        actual = _get_runtime_routes()
        assert len(actual) >= 100, f"Expected 100+ routes, got {len(actual)}"


# Support --update-snapshot flag
def pytest_addoption(parser):
    parser.addoption(
        "--update-snapshot",
        action="store_true",
        default=False,
        help="Update the route contract snapshot",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--update-snapshot"):
        routes = _get_runtime_routes()
        _save_snapshot(routes)
        print(f"\nUpdated route contract snapshot: {len(routes)} routes")
