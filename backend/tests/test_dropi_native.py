"""Contract tests for the partner-gated native Dropi read-only transport."""
import httpx
import pytest

from app.integrations.dropi_native import DropiNativeError, get_base_url, preview_products, read_product_details


def test_public_country_allowlist_only():
    assert get_base_url("CO") == "https://api.dropi.co/integrations/"
    with pytest.raises(DropiNativeError, match="DROPI_COUNTRY_UNSUPPORTED"):
        get_base_url("PRIVATE")


def test_provider_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DROPI_NATIVE_API_ENABLED", raising=False)
    with pytest.raises(DropiNativeError, match="DROPI_PARTNER_APPROVAL_REQUIRED"):
        preview_products("token-is-never-sent")


def test_authorized_read_only_catalog_preview(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "isSuccess": True,
                "objects": [{
                    "id": 123,
                    "name": "Sample",
                    "sku": "SAMPLE",
                    "type": "SIMPLE",
                    "stock": 4,
                    "supplier_email": "secret@example.com",
                }],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = preview_products("example-test-token", country_code="CO", limit=1, client=client)
    assert result == [{"id": 123, "name": "Sample", "sku": "SAMPLE", "type": "SIMPLE", "stock": 4}]
    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert str(seen[0].url) == "https://api.dropi.co/integrations/products/index"
    assert seen[0].headers["dropi-integration-key"] == "example-test-token"
    assert b'"pageSize":1' in seen[0].content
    assert "secret@example.com" not in str(result)


@pytest.mark.parametrize("status,expected", [
    (401, "DROPI_AUTH_FAILED"),
    (403, "DROPI_AUTH_FAILED"),
    (404, "DROPI_PROVIDER_UNAVAILABLE"),
])
def test_provider_http_errors(monkeypatch, status, expected):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status)))
    with pytest.raises(DropiNativeError, match=expected):
        preview_products("token", client=client)
    client.close()


def test_provider_rejection_without_secret_leak(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "true")
    client = httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"isSuccess": False, "message": "Invalid token details"}),
    ))
    with pytest.raises(DropiNativeError, match="DROPI_AUTH_OR_PROVIDER_ERROR") as info:
        preview_products("sensitive-token", client=client)
    assert "sensitive-token" not in str(info.value)
    client.close()


def test_invalid_catalog_type(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    client = httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"isSuccess": True, "objects": {"id": 1}}),
    ))
    with pytest.raises(DropiNativeError, match="DROPI_INVALID_RESPONSE"):
        preview_products("token", client=client)
    client.close()


def test_unsupported_limit(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    with pytest.raises(DropiNativeError, match="DROPI_INVALID_LIMIT"):
        preview_products("token", limit=100)


def test_read_product_disabled_without_authorization(monkeypatch):
    monkeypatch.delenv("DROPI_NATIVE_API_ENABLED", raising=False)
    with pytest.raises(DropiNativeError, match="DROPI_PARTNER_APPROVAL_REQUIRED"):
        read_product_details("unused", "12")


@pytest.mark.parametrize("invalid", ["", "-5", "1/2", "../orders", "1?send=1", "０１", "1" * 30])
def test_read_product_rejects_unsafe_ids(monkeypatch, invalid):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    with pytest.raises(DropiNativeError, match="DROPI_INVALID_PRODUCT_ID"):
        read_product_details("token", invalid)


def test_read_product_stock_and_variations_sanitized(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "true")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={
            "isSuccess": True,
            "objects": {
                "id": 12,
                "name": "Camisa",
                "sku": "ABC",
                "type": "VARIABLE",
                "stock": 50,
                "supplier_email": "private@example.com",
                "variations": [
                    {"id": 123, "sku": "ABC-S", "stock": 12, "supplier_phone": "secret"}
                ],
            },
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = read_product_details("test-dropi-token", "12", client=client)

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert str(requests[0].url) == "https://api.dropi.co/integrations/products/v2/12"
    assert requests[0].headers["dropi-integration-key"] == "test-dropi-token"
    assert result["stock"] == 50
    assert result["variations"] == [{"id": 123, "sku": "ABC-S", "stock": 12}]
    assert "private@example.com" not in repr(result)
    assert "secret" not in repr(result)


def test_read_product_fails_closed_for_invalid_provider_shape(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    with httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"isSuccess": True, "objects": ["unexpected"]})
    )) as client:
        with pytest.raises(DropiNativeError, match="DROPI_INVALID_RESPONSE"):
            read_product_details("test-token", "12", client=client)


def test_read_product_never_follows_redirects(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    with httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(302, headers={"location": "http://localhost/private"})
    ), follow_redirects=False) as client:
        with pytest.raises(DropiNativeError, match="DROPI_REDIRECT_DENIED"):
            read_product_details("test-token", "12", client=client)


def test_read_product_rejects_oversized_variations(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    with httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={
            "isSuccess": True, "objects": {"variations": [{"id": i} for i in range(101)]}
        })
    )) as client:
        with pytest.raises(DropiNativeError, match="DROPI_RESPONSE_TOO_LARGE"):
            read_product_details("test-token", "12", client=client)
