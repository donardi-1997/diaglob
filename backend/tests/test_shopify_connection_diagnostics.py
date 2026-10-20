"""Synthetic Shopify test/sync diagnostics. No network, tokens or shop data."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.shopify_client import ShopifyAPIError, ShopifyAuthError
from app.shopify_token_lifecycle import ShopifyTokenRefreshError
from app.services import shopify_service


def _connection():
    return SimpleNamespace(
        status="connected",
        last_error=None,
        organization_id=11,
        store_id=22,
    )


@pytest.mark.parametrize("error,expected_code,expected_status", [
    (ShopifyTokenRefreshError("SHOPIFY_REFRESH_TOKEN_EXPIRED"),
     "SHOPIFY_REAUTH_REQUIRED", "error"),
    (ShopifyTokenRefreshError("SHOPIFY_TOKEN_REFRESH_FAILED"),
     "SHOPIFY_REFRESH_UNAVAILABLE", "connected"),
    (ShopifyTokenRefreshError("SHOPIFY_REFRESH_NOT_CONFIGURED"),
     "SHOPIFY_REFRESH_UNAVAILABLE", "connected"),
])
def test_token_refresh_is_mapped_to_safe_diagnostic(error, expected_code, expected_status):
    db = Mock()
    connection = _connection()
    with patch.object(shopify_service, "_require_store"), patch.object(
        shopify_service, "_require_connection", return_value=connection,
    ), patch.object(shopify_service, "test_shopify_connection", side_effect=error):
        with pytest.raises((ShopifyAuthError, ShopifyAPIError), match=expected_code):
            shopify_service.test_connection(db, 11, 22)
    assert connection.status == expected_status
    assert connection.last_error == expected_code
    db.rollback.assert_called_once()
    db.commit.assert_called_once()


def test_shopify_auth_error_marks_reauthorization_required_without_echoing_source():
    db = Mock()
    connection = _connection()
    with patch.object(shopify_service, "_require_store"), patch.object(
        shopify_service, "_require_connection", return_value=connection,
    ), patch.object(
        shopify_service, "test_shopify_connection",
        side_effect=ShopifyAuthError("sensitive provider response"),
    ):
        with pytest.raises(ShopifyAuthError):
            shopify_service.test_connection(db, 11, 22)
    assert connection.status == "error"
    assert connection.last_error == "SHOPIFY_REAUTH_REQUIRED"
    assert "sensitive" not in connection.last_error


def test_transient_shopify_failure_does_not_revoke_connection():
    db = Mock()
    connection = _connection()
    with patch.object(shopify_service, "_require_store"), patch.object(
        shopify_service, "_require_connection", return_value=connection,
    ), patch.object(
        shopify_service, "test_shopify_connection",
        side_effect=ShopifyAPIError("synthetic network issue"),
    ):
        with pytest.raises(ShopifyAPIError):
            shopify_service.test_connection(db, 11, 22)
    assert connection.status == "connected"
    assert connection.last_error == "SHOPIFY_CONNECTION_CHECK_FAILED"
    db.commit.assert_called_once()


@pytest.mark.parametrize("error,status,last_error", [
    (ShopifyTokenRefreshError("SHOPIFY_REFRESH_TOKEN_EXPIRED"), "error", "SHOPIFY_REAUTH_REQUIRED"),
    (ShopifyTokenRefreshError("SHOPIFY_TOKEN_REFRESH_FAILED"), "connected", "SHOPIFY_REFRESH_UNAVAILABLE"),
])
def test_product_sync_does_not_leak_token_refresh_error(error, status, last_error):
    db = Mock()
    connection = _connection()
    with patch.object(shopify_service, "_require_store"), patch.object(
        shopify_service, "_require_connection", return_value=connection,
    ), patch.object(shopify_service, "sync_shopify_products", side_effect=error):
        with pytest.raises((ShopifyAPIError, ShopifyAuthError)):
            shopify_service.sync_products(db, 11, 22)
    assert connection.status == status
    assert connection.last_error == last_error


def test_failed_connection_not_mistaken_for_missing_installation():
    from app.services.shopify_service import ShopifyNotFoundError

    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = (1,)
    with patch.object(shopify_service, "_require_store"), patch.object(
        shopify_service, "_require_connection", side_effect=ShopifyNotFoundError(),
    ):
        with pytest.raises(ShopifyAuthError, match="SHOPIFY_REAUTH_REQUIRED"):
            shopify_service.test_connection(db, 11, 22)
    db.query.assert_called_once()


def test_no_saved_auth_error_still_reports_missing_connection():
    from app.services.shopify_service import ShopifyNotFoundError

    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = None
    with patch.object(shopify_service, "_require_store"), patch.object(
        shopify_service, "_require_connection", side_effect=ShopifyNotFoundError(),
    ):
        with pytest.raises(ShopifyNotFoundError):
            shopify_service.test_connection(db, 11, 22)
