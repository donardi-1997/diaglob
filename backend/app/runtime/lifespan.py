"""Application lifecycle orchestration.

External reconciliation is launched after the event loop starts and is not awaited
before the API begins serving traffic. Failures are logged and isolated from process
startup so a transient Bedrock/DB reconciliation problem cannot make the HTTP service
unavailable.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from ..settings import Settings

logger = logging.getLogger(__name__)


async def run_knowledge_reconciliation() -> None:
    """Run the synchronous reconciliation outside the event loop and isolate errors."""
    try:
        from ..services.knowledge_provisioning import (
            reconcile_knowledge_base_provisioning,
        )

        await asyncio.to_thread(reconcile_knowledge_base_provisioning)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("knowledge.startup_reconciliation_failed")


def build_lifespan(settings: Settings):
    """Build a FastAPI lifespan function from validated runtime settings."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task: asyncio.Task[None] | None = None

        if settings.knowledge_reconcile_on_startup:
            task = asyncio.create_task(
                run_knowledge_reconciliation(),
                name="knowledge-startup-reconciliation",
            )
            app.state.knowledge_reconciliation_task = task

        try:
            yield
        finally:
            if task is not None and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    return lifespan
