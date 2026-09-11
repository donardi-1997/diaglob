"""Architecture and adapter tests for provider-neutral subscription billing."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.billing_providers import (
    BillingProviderError,
    UnsupportedBillingProviderError,
    get_billing_provider,
    get_billing_provider_for_organization,
    registered_billing_providers,
)
from app.billing_providers.paddle import PaddleBillingProvider
from app.paddle_client import PaddleProviderError


def test_legacy_organization_defaults_to_paddle():
    organization = SimpleNamespace(billing_provider=None)

    provider = get_billing_provider_for_organization(organization)

    assert provider.name == "paddle"
    assert "paddle" in registered_billing_providers()


def test_explicit_paddle_provider_resolves():
    assert get_billing_provider(" PADDLE ").name == "paddle"


def test_unknown_provider_is_rejected_explicitly():
    with pytest.raises(UnsupportedBillingProviderError):
        get_billing_provider("future-provider")


def test_paddle_adapter_translates_provider_errors():
    provider = PaddleBillingProvider()
    native_error = PaddleProviderError(
        status_code=502,
        detail={"message": "provider down"},
    )

    with patch(
        "app.paddle_client.get_subscription",
        side_effect=native_error,
    ):
        with pytest.raises(BillingProviderError) as exc_info:
            provider.get_subscription("sub_123")

    error = exc_info.value
    assert error.provider == "paddle"
    assert error.status_code == 502
    assert error.detail == {"message": "provider down"}


def test_billing_service_does_not_import_paddle_transport():
    service_path = (
        Path(__file__).resolve().parent.parent
        / "app"
        / "services"
        / "billing_service.py"
    )
    text = service_path.read_text(encoding="utf-8")

    assert "paddle_client" not in text
    assert "from ..paddle_client" not in text
    assert "os.getenv(\"PADDLE_" not in text


def test_billing_router_does_not_import_paddle_transport():
    router_path = (
        Path(__file__).resolve().parent.parent
        / "app"
        / "api"
        / "billing.py"
    )
    text = router_path.read_text(encoding="utf-8")

    assert "from ..paddle_client" not in text
    assert "PaddleProviderError" not in text
