from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.admin import _require_platform_admin


def test_bootstrap_platform_admin_is_always_authorized(monkeypatch):
    monkeypatch.delenv("PLATFORM_ADMIN_EMAILS", raising=False)
    user = SimpleNamespace(email="ADMIN@DIAGLOB.TECH")

    assert _require_platform_admin(user) is user


def test_configured_platform_admin_is_authorized(monkeypatch):
    monkeypatch.setenv(
        "PLATFORM_ADMIN_EMAILS",
        "owner@example.com, second@example.com",
    )
    user = SimpleNamespace(email="second@example.com")

    assert _require_platform_admin(user) is user


def test_non_platform_admin_is_rejected(monkeypatch):
    monkeypatch.delenv("PLATFORM_ADMIN_EMAILS", raising=False)
    user = SimpleNamespace(email="merchant@example.com")

    with pytest.raises(HTTPException) as exc_info:
        _require_platform_admin(user)

    assert exc_info.value.status_code == 403
