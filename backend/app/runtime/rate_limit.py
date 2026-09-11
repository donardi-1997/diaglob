"""Rate-limit middleware with a replaceable storage backend.

The middleware is intentionally independent from FastAPI application bootstrap.
The in-memory backend preserves today's single-process behavior while providing a
clean boundary for a Redis-backed implementation without changing routing code.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


@dataclass(frozen=True)
class RateLimitRule:
    max_requests: int
    window_seconds: int


DEFAULT_RATE_LIMIT_RULES: dict[str, RateLimitRule] = {
    "/api/auth/login": RateLimitRule(10, 60),
    "/api/auth/register": RateLimitRule(5, 60),
    "/api/billing/checkout": RateLimitRule(10, 60),
    "/api/billing/ai-packages/checkout": RateLimitRule(10, 60),
    "/api/billing/upgrade": RateLimitRule(10, 60),
    "/api/billing/upgrade/preview": RateLimitRule(20, 60),
    "/api/billing/downgrade": RateLimitRule(10, 60),
    "/webhooks/whatsapp": RateLimitRule(100, 60),
}


class RateLimitBackend(Protocol):
    async def allow(self, key: str, rule: RateLimitRule) -> bool:
        """Return True when the request may proceed and record the hit."""


@dataclass
class _Bucket:
    timestamps: deque[float]
    window_seconds: int


class InMemoryRateLimitBackend:
    """Process-local sliding-window limiter with periodic stale-key cleanup."""

    def __init__(self, prune_interval_seconds: int = 60) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()
        self._last_prune = time.monotonic()
        self._prune_interval_seconds = max(int(prune_interval_seconds), 1)

    async def allow(self, key: str, rule: RateLimitRule) -> bool:
        now = time.monotonic()
        async with self._lock:
            self._prune_if_needed(now)
            bucket = self._buckets.setdefault(
                key,
                _Bucket(deque(), rule.window_seconds),
            )
            bucket.window_seconds = rule.window_seconds
            cutoff = now - rule.window_seconds
            while bucket.timestamps and bucket.timestamps[0] <= cutoff:
                bucket.timestamps.popleft()

            if len(bucket.timestamps) >= rule.max_requests:
                return False

            bucket.timestamps.append(now)
            return True

    def _prune_if_needed(self, now: float) -> None:
        if now - self._last_prune < self._prune_interval_seconds:
            return

        stale_keys: list[str] = []
        for key, bucket in self._buckets.items():
            cutoff = now - bucket.window_seconds
            while bucket.timestamps and bucket.timestamps[0] <= cutoff:
                bucket.timestamps.popleft()
            if not bucket.timestamps:
                stale_keys.append(key)

        for key in stale_keys:
            self._buckets.pop(key, None)
        self._last_prune = now

    @property
    def bucket_count(self) -> int:
        """Expose current bucket count for diagnostics/tests."""
        return len(self._buckets)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply configured rules without owning persistence concerns."""

    def __init__(
        self,
        app,
        *,
        backend: RateLimitBackend,
        rules: dict[str, RateLimitRule] | None = None,
        enabled: bool = True,
    ) -> None:
        super().__init__(app)
        self.backend = backend
        self.rules = rules or DEFAULT_RATE_LIMIT_RULES
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled:
            return await call_next(request)

        rule = self.rules.get(request.url.path)
        if rule is None:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{client_ip}"

        if not await self.backend.allow(key, rule):
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
            )

        return await call_next(request)
