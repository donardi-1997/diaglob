"""
Tests for Dropi integration abstraction.

Covers:
- Placeholder raises correct errors
- Provider interface
- Factory function
"""

import os

import pytest

from app.integrations.dropi import (
    DropiNotConfiguredError,
    DropiPlaceholder,
    DropiProviderError,
    get_dropi_provider,
)


class TestDropiPlaceholder:
    """Test placeholder provider raises clear errors."""

    def test_get_products_raises(self):
        provider = DropiPlaceholder()

        with pytest.raises(DropiNotConfiguredError):
            provider.get_products(store_id=1)

    def test_create_order_raises(self):
        provider = DropiPlaceholder()

        with pytest.raises(DropiNotConfiguredError):
            provider.create_order(store_id=1, items=[])

    def test_get_order_raises(self):
        provider = DropiPlaceholder()

        with pytest.raises(DropiNotConfiguredError):
            provider.get_order(store_id=1, order_id="123")

    def test_get_shipping_quote_raises(self):
        provider = DropiPlaceholder()

        with pytest.raises(DropiNotConfiguredError):
            provider.get_shipping_quote(
                store_id=1,
                items=[],
                destination={},
            )


class TestDropiProviderError:
    """Test provider error class."""

    def test_error_message(self):
        err = DropiProviderError("API error", 502)
        assert str(err) == "API error"
        assert err.status_code == 502

    def test_error_default_status(self):
        err = DropiProviderError("Error")
        assert err.status_code == 502


class TestDropiFactory:
    """Test provider factory function."""

    def test_returns_placeholder_when_not_configured(self):
        provider = get_dropi_provider()
        assert isinstance(provider, DropiPlaceholder)

    def test_returns_placeholder_without_api_key(self):
        original = os.environ.pop("DROPI_API_KEY", None)
        os.environ.pop("DROPI_API_BASE_URL", None)

        try:
            provider = get_dropi_provider()
            assert isinstance(provider, DropiPlaceholder)
        finally:
            if original:
                os.environ["DROPI_API_KEY"] = original


class TestDropiNotConfiguredError:
    """Test error message content."""

    def test_message_mentions_api_access(self):
        err = DropiNotConfiguredError()
        assert "API access" in str(err) or "api access" in str(err).lower()
