"""Contract tests for the partner-gated native Dropi read-only transport."""
import httpx
import pytest

from app.integrations.dropi_native import DropiNativeError, get_base_url, preview_products


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
