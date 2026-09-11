import pytest
from pydantic import ValidationError

from app.settings import Settings
from app.runtime.observability import initialize_observability


def test_sentry_is_skipped_without_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.runtime.observability.sentry_sdk.init",
        lambda **kwargs: calls.append(kwargs),
    )

    enabled = initialize_observability(Settings(sentry_dsn=None))

    assert enabled is False
    assert calls == []


def test_sentry_uses_privacy_safe_configuration(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.runtime.observability.sentry_sdk.init",
        lambda **kwargs: calls.append(kwargs),
    )

    settings = Settings(
        sentry_dsn="https://public@example.ingest.sentry.io/123",
        sentry_environment="production",
        sentry_release="diaglob@abc1234",
        sentry_traces_sample_rate=0.05,
    )

    enabled = initialize_observability(settings)

    assert enabled is True
    assert len(calls) == 1
    assert calls[0]["dsn"] == settings.sentry_dsn
    assert calls[0]["environment"] == "production"
    assert calls[0]["release"] == "diaglob@abc1234"
    assert calls[0]["traces_sample_rate"] == 0.05
    assert calls[0]["send_default_pii"] is False


def test_sentry_sample_rate_rejects_values_above_one():
    with pytest.raises(ValidationError):
        Settings(sentry_traces_sample_rate=1.1)
