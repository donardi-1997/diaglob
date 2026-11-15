"""Shopify Admin GraphQL transport and response contracts with mocked HTTP.

Covers permission denials, retryable conditions and unexpected provider payloads.
No HTTP calls escape this test module and no customer data are used.
"""
import httpx
import pytest

from app.shopify_client import (
    ShopifyAPIError, ShopifyAuthError, ShopifyGraphQLClient,
    ShopifyGraphQLError, ShopifyPlanError, ShopifyProtectedCustomerDataError,
    ShopifyRateLimitError, ShopifyScopeDeniedError, ShopifyTimeoutError,
)


def _response(url, status=200, json_body=None, raw=None):
    kwargs = {"content": raw} if raw is not None else {"json": json_body}
    return httpx.Response(
        status, request=httpx.Request("POST", url), **kwargs,
    )


def _client():
    return ShopifyGraphQLClient("  DEMO.MYSHOPIFY.COM ", "fixture-token-not-real")


def _stub(monkeypatch, *, status=200, payload=None, raw=None):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _response(url, status=status, json_body=payload, raw=raw)

    monkeypatch.setattr("app.shopify_client.httpx.post", fake_post)
    return calls


def test_graphql_uses_shop_scoped_https_endpoint_with_auth_header_and_variables(monkeypatch):
    calls = _stub(monkeypatch, payload={"data": {"shop": {"id": "gid://shopify/Shop/123"}}})
    result = _client().query(
        "query($id: ID!) { shop { id } }",
        {"id": "gid://shopify/Shop/123"},
    )
    assert result == {"shop": {"id": "gid://shopify/Shop/123"}}
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url.startswith("https://demo.myshopify.com/admin/api/")
    assert url.endswith("/graphql.json")
    assert kwargs["headers"]["X-Shopify-Access-Token"] == "fixture-token-not-real"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["json"]["variables"] == {"id": "gid://shopify/Shop/123"}
    assert kwargs["timeout"] > 0


def test_query_without_variables_does_not_send_empty_variables(monkeypatch):
    calls = _stub(monkeypatch, payload={"data": {"shop": {"name": "Synthetic"}}})
    assert _client().query("query { shop { name } }") == {"shop": {"name": "Synthetic"}}
    assert "variables" not in calls[0][1]["json"]


@pytest.mark.parametrize("status,kind,public_text", [
    (401, ShopifyAuthError, "Invalid or expired Shopify"),
    (402, ShopifyPlanError, "Shopify plan does not support"),
    (429, ShopifyRateLimitError, "Shopify rate limit exceeded"),
    (400, ShopifyAPIError, "Shopify HTTP error 400"),
    (403, ShopifyAPIError, "Shopify HTTP error 403"),
    (404, ShopifyAPIError, "Shopify HTTP error 404"),
    (500, ShopifyAPIError, "Shopify HTTP error 500"),
    (502, ShopifyAPIError, "Shopify HTTP error 502"),
    (503, ShopifyAPIError, "Shopify HTTP error 503"),
])
def test_transport_failure_statuses_have_deterministic_safe_exception(
    monkeypatch, status, kind, public_text,
):
    _stub(monkeypatch, status=status, payload={
        "error": "sensitive-value private@example.invalid",
    })
    with pytest.raises(kind) as failure:
        _client().query("query { shop { id } }")
    assert public_text in str(failure.value)
    assert "private@example.invalid" not in str(failure.value)


@pytest.mark.parametrize("problem,expected", [
    (httpx.ReadTimeout("provider timed out"), ShopifyTimeoutError),
    (httpx.ConnectTimeout("provider timed out"), ShopifyTimeoutError),
    (httpx.ConnectError("provider network error"), ShopifyAPIError),
    (httpx.RemoteProtocolError("provider failure"), ShopifyAPIError),
])
def test_network_exceptions_do_not_leak_provider_details(monkeypatch, problem, expected):
    def fake_post(*args, **kwargs):
        raise problem

    monkeypatch.setattr("app.shopify_client.httpx.post", fake_post)
    with pytest.raises(expected) as failure:
        _client().query("query { shop { id } }")
    assert "provider" not in str(failure.value)


@pytest.mark.parametrize("body", [
    b"not json",
    b"<html>Sensitive provider response</html>",
    b"",
])
def test_malformed_json_is_rejected_without_echo(monkeypatch, body):
    _stub(monkeypatch, raw=body)
    with pytest.raises(ShopifyAPIError, match="Invalid JSON from Shopify") as failure:
        _client().query("query { shop { id } }")
    assert "Sensitive" not in str(failure.value)


@pytest.mark.parametrize("payload", [
    None, [], True, 42, "not-an-object",
])
def test_non_object_json_is_rejected(monkeypatch, payload):
    _stub(monkeypatch, payload=payload)
    with pytest.raises(ShopifyAPIError, match="Invalid JSON from Shopify"):
        _client().query("query { shop { id } }")


@pytest.mark.parametrize("error,expected,code", [
    (
        {"message": "Not approved to access CUSTOMER email private@example.invalid"},
        ShopifyProtectedCustomerDataError,
        "SHOPIFY_PROTECTED_CUSTOMER_DATA_NOT_APPROVED",
    ),
    (
        {"message": "Not approved to use protected customer data"},
        ShopifyProtectedCustomerDataError,
        "SHOPIFY_PROTECTED_CUSTOMER_DATA_NOT_APPROVED",
    ),
    (
        {"message": "Forbidden", "extensions": {"code": "forbidden"}},
        ShopifyScopeDeniedError,
        "SHOPIFY_SCOPE_DENIED",
    ),
    (
        {"message": "Required access: read_orders"},
        ShopifyScopeDeniedError,
        "SHOPIFY_SCOPE_DENIED",
    ),
    (
        {"message": "Unknown provider exception private@example.invalid"},
        ShopifyGraphQLError,
        "SHOPIFY_GRAPHQL_QUERY_FAILED",
    ),
])
def test_http_200_with_graphql_errors_fails_closed_without_partial_data(
    monkeypatch, error, expected, code,
):
    _stub(monkeypatch, payload={
        "data": {"customer": {"email": "private@example.invalid"}},
        "errors": [error],
    })
    with pytest.raises(expected) as failure:
        _client().query("query { customer { email } }")
    assert str(failure.value) == code
    assert "private@example.invalid" not in str(failure.value)


@pytest.mark.parametrize("errors", [
    [{"message": "unknown error"}],
    {"message": "unknown error"},
    ["unstructured error"],
])
def test_graphql_error_variants_never_return_partial_data(monkeypatch, errors):
    _stub(monkeypatch, payload={"data": {"orders": [1]}, "errors": errors})
    with pytest.raises(ShopifyGraphQLError, match="SHOPIFY_GRAPHQL_QUERY_FAILED"):
        _client().query("query { orders { id } }")


@pytest.mark.parametrize("invalid_data", [None, False, [], "bad", 7])
def test_http_200_without_valid_graphql_data_cannot_look_like_success(
    monkeypatch, invalid_data,
):
    _stub(monkeypatch, payload={"data": invalid_data})
    with pytest.raises(ShopifyGraphQLError, match="SHOPIFY_GRAPHQL_QUERY_FAILED"):
        _client().query("query { shop { id } }")


@pytest.mark.parametrize("shop,token", [
    ("", "token"), ("demo.myshopify.com", ""),
])
def test_client_requires_shop_and_token(shop, token):
    with pytest.raises(ValueError):
        ShopifyGraphQLClient(shop, token)
