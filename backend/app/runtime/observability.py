"""Optional production observability initialization for Diaglob."""
from __future__ import annotations

import sentry_sdk

from ..settings import Settings


def initialize_observability(settings: Settings) -> bool:
    """Initialize Sentry when configured, with privacy-safe defaults."""
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment,
        release=settings.sentry_release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
    return True
