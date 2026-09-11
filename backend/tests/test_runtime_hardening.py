"""Regression coverage for process-level runtime hardening."""
from __future__ import annotations

import asyncio
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.runtime import lifespan as lifespan_module
from app.runtime.rate_limit import (
    InMemoryRateLimitBackend,
    RateLimitMiddleware,
    RateLimitRule,
)
from app.runtime.security import SecurityHeadersMiddleware
from app.services import knowledge_provisioning
from app.settings import Settings


def test_settings_normalize_environment_and_origins():
    settings = Settings(
        environment=" PROD ",
        cors_allowed_origins=(
            "https://app.diaglob.tech/, https://diaglob.tech, "
            "https://app.diaglob.tech"
        ),
        _env_file=None,
    )

    assert settings.environment == "production"
    assert settings.is_production is True
    assert settings.allowed_origins == [
        "https://app.diaglob.tech",
        "https://diaglob.tech",
    ]


def test_in_memory_rate_limit_backend_enforces_rule_per_key():
    backend = InMemoryRateLimitBackend()
    rule = RateLimitRule(max_requests=2, window_seconds=60)

    async def scenario():
        assert await backend.allow("login:1.1.1.1", rule) is True
        assert await backend.allow("login:1.1.1.1", rule) is True
        assert await backend.allow("login:1.1.1.1", rule) is False
        assert await backend.allow("login:2.2.2.2", rule) is True
        assert backend.bucket_count == 2
        backend.clear()
        assert backend.bucket_count == 0

    asyncio.run(scenario())


def test_rate_limit_response_keeps_cors_and_security_headers():
    origin = "https://app.diaglob.tech"
    backend = InMemoryRateLimitBackend()
    app = FastAPI()

    @app.get("/limited")
    def limited():
        return {"ok": True}

    app.add_middleware(
        RateLimitMiddleware,
        backend=backend,
        rules={"/limited": RateLimitRule(1, 60)},
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    client = TestClient(app)
    headers = {"Origin": origin}

    assert client.get("/limited", headers=headers).status_code == 200
    response = client.get("/limited", headers=headers)

    assert response.status_code == 429
    assert response.json() == {"detail": "Rate limit exceeded"}
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_start_knowledge_reconciliation_uses_daemon_worker(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_reconciliation():
        started.set()
        release.wait(timeout=1)

    monkeypatch.setattr(
        lifespan_module,
        "run_knowledge_reconciliation",
        slow_reconciliation,
    )
    monkeypatch.setattr(lifespan_module, "_reconciliation_thread", None)

    worker = lifespan_module.start_knowledge_reconciliation()

    assert started.wait(timeout=0.5) is True
    assert worker.daemon is True
    assert worker.is_alive() is True

    # A second startup while the first reconciliation is active reuses the worker.
    assert lifespan_module.start_knowledge_reconciliation() is worker

    release.set()
    worker.join(timeout=0.5)
    assert worker.is_alive() is False


def test_lifespan_schedules_knowledge_reconciliation_without_joining(monkeypatch):
    sentinel = object()
    calls: list[str] = []

    def fake_start():
        calls.append("started")
        return sentinel

    monkeypatch.setattr(
        lifespan_module,
        "start_knowledge_reconciliation",
        fake_start,
    )

    settings = Settings(
        knowledge_reconcile_on_startup=True,
        _env_file=None,
    )
    app = FastAPI()

    async def scenario():
        lifespan = lifespan_module.build_lifespan(settings)
        async with lifespan(app):
            assert calls == ["started"]
            assert app.state.knowledge_reconciliation_thread is sentinel

    asyncio.run(scenario())


def test_lifespan_can_disable_startup_reconciliation():
    settings = Settings(
        knowledge_reconcile_on_startup=False,
        _env_file=None,
    )
    app = FastAPI()

    async def scenario():
        lifespan = lifespan_module.build_lifespan(settings)
        async with lifespan(app):
            assert not hasattr(app.state, "knowledge_reconciliation_thread")

    asyncio.run(scenario())


def test_reconciliation_failure_isolated_from_runtime(monkeypatch):
    def failing_reconciliation():
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        knowledge_provisioning,
        "reconcile_knowledge_base_provisioning",
        failing_reconciliation,
    )

    # The startup reconciliation is best effort: provider failures are logged but
    # must not escape and fail FastAPI startup.
    lifespan_module.run_knowledge_reconciliation()
