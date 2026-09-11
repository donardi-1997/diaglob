"""Application lifecycle orchestration.

External reconciliation is launched in a daemon worker and is not awaited before the
API begins serving traffic. Failures are logged and isolated from process startup or
shutdown so a transient Bedrock/DB reconciliation problem cannot make the HTTP
service unavailable.
"""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..settings import Settings

logger = logging.getLogger(__name__)

_reconciliation_lock = threading.Lock()
_reconciliation_thread: threading.Thread | None = None


def run_knowledge_reconciliation() -> None:
    """Run one reconciliation attempt and isolate provider/infrastructure errors."""
    try:
        from ..services.knowledge_provisioning import (
            reconcile_knowledge_base_provisioning,
        )

        reconcile_knowledge_base_provisioning()
    except Exception:
        logger.exception("knowledge.startup_reconciliation_failed")


def start_knowledge_reconciliation() -> threading.Thread:
    """Start reconciliation without blocking startup or duplicating active workers."""
    global _reconciliation_thread

    with _reconciliation_lock:
        if _reconciliation_thread is not None and _reconciliation_thread.is_alive():
            return _reconciliation_thread

        _reconciliation_thread = threading.Thread(
            target=run_knowledge_reconciliation,
            name="knowledge-startup-reconciliation",
            daemon=True,
        )
        _reconciliation_thread.start()
        return _reconciliation_thread


def build_lifespan(settings: Settings):
    """Build a FastAPI lifespan function from validated runtime settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.knowledge_reconcile_on_startup:
            app.state.knowledge_reconciliation_thread = (
                start_knowledge_reconciliation()
            )

        # Intentionally do not join the daemon worker on shutdown. API lifecycle
        # availability must not depend on an external reconciliation attempt.
        yield

    return lifespan
