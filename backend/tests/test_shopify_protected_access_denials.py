"""Shopify protected-customer-data denial must fail closed without leaking PII."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.shopify_client import (
    ShopifyGraphQLClient,
    ShopifyGraphQLError,
    ShopifyProtectedCustomerDataError,
    ShopifyScopeDeniedError,
)


@pytest.mark.parametrize(
    "error,expected_error,expected_code",
    [
        (
            {
                "message": "This app is not approved to access the Customer object.",
                "path": ["customer", "phone"],
            },
            ShopifyProtectedCustomerDataError,
            "SHOPIFY_PROTECTED_CUSTOMER_DATA_NOT_APPROVED",
        ),
        (
            {
                "message": "This app is not approved to use the phoneNumber field.",
                "path": ["customer", "phoneNumber"],
            },
            ShopifyProtectedCustomerDataError,
            "SHOPIFY_PROTECTED_CUSTOMER_DATA_NOT_APPROVED",
        ),
        (
            {"message": "Access denied for orders.", "extensions": {"code": "ACCESS_DENIED"}},
            ShopifyScopeDeniedError,
            "SHOPIFY_SCOPE_DENIED",
        ),
        (
            {"message": "Sensitive supplier payload: private@example.com"},
            ShopifyGraphQLError,
            "SHOPIFY_GRAPHQL_QUERY_FAILED",
        ),
    ],
)
def test_graphql_http_200_errors_never_return_partial_data_or_raw_messages(
    error, expected_error, expected_code
):
    response = Mock(status_code=200)
    response.json.return_value = {
        "data": {"customer": {"email": "private@example.com", "phone": None}},
        "errors": [error],
    }
    client = ShopifyGraphQLClient("dev.myshopify.com", "fake-token")

    with patch("app.shopify_client.httpx.post", return_value=response):
        with pytest.raises(expected_error) as captured:
            client.query("query { customer { email phone } }")

    assert str(captured.value) == expected_code
    assert "private@example.com" not in str(captured.value)
    assert "Sensitive supplier payload" not in str(captured.value)


def test_graphql_success_without_errors_preserves_data():
    response = Mock(status_code=200)
    response.json.return_value = {"data": {"shop": {"name": "Development"}}}
    client = ShopifyGraphQLClient("dev.myshopify.com", "fake-token")

    with patch("app.shopify_client.httpx.post", return_value=response):
        assert client.query("query { shop { name } }") == {
            "shop": {"name": "Development"}
        }


@pytest.mark.parametrize(
    "denial",
    [
        ShopifyProtectedCustomerDataError(
            "SHOPIFY_PROTECTED_CUSTOMER_DATA_NOT_APPROVED"
        ),
        ShopifyScopeDeniedError("SHOPIFY_SCOPE_DENIED"),
    ],
)
def test_shopify_test_endpoint_reports_actionable_safe_denial(denial):
    from app.api.shopify import shopify_test_connection

    membership = SimpleNamespace(organization_id=1)
    with patch("app.api.shopify.svc_test_connection", side_effect=denial):
        with pytest.raises(HTTPException) as captured:
            shopify_test_connection(store_id=2, membership=membership, db=object())

    assert captured.value.status_code == 403
    assert captured.value.detail["code"] == str(denial)
    assert "permission or protected data approval" in (
        captured.value.detail["message"].lower()
    )
