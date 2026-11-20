"""Safe runtime dependency checks used by load balancers and operators."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import text


def database_readiness(
    connect: Callable[[], AbstractContextManager[Any]],
) -> dict[str, str]:
    """Check database availability without returning driver or connection detail."""
    try:
        with connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return {"status": "degraded", "database": "error"}
    return {"status": "ok", "database": "connected"}


def readiness_payload(
    connect: Callable[[], AbstractContextManager[Any]],
) -> dict[str, str | bool]:
    """Return a stable, non-sensitive readiness contract."""
    result = database_readiness(connect)
    return {
        "status": result["status"],
        "service": "diaglob-api",
        "database": result["database"],
        "multitenant": True,
        "multistore": True,
    }
