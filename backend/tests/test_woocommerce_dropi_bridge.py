"""Contract tests for the supported WooCommerce / Dropify bridge boundary."""
import base64

import httpx
import pytest

from app.integrations import woocommerce_bridge as woo


@pytest.mark.parametrize(
    "url",
    [
        "http://store.example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://10.0.0.1",
        "https://store.example.com:8080",
        "https://user:pass@store.example.com",
        "https://store.example.com/?key=secret",
        "https://store.example.com/#fragment",
        "https://store.local",
        "https://store.example.com/../admin",
    ],
)
def test_rejects_unsafe_merchant_urls(url):
    with pytest.raises(woo.WooCommerceError) as exc:
        woo.normalize_woocommerce_url(url)
    assert exc.value.code == "WOO_INVALID_URL"


def test_normalizes_public_subdirectory():
    assert (
        woo.normalize_woocommerce_url("https://SHOP.EXAMPLE.COM/wordpress/")
        == "https://shop.example.com/wordpress"
    )


def test_blocks_private_dns_response(monkeypatch):
    monkeypatch.setattr(
        woo.socket,
        "getaddrinfo",
        lambda *_a, **_kw: [(2, 1, 6, "", ("172.16.0.2", 443))],
    )
    with pytest.raises(woo.WooCommerceError) as exc:
        woo.assert_public_dns("https://example.com")
    assert exc.value.code == "WOO_UNSAFE_DESTINATION"


def test_products_read_is_basic_auth_and_read_only(monkeypatch):
    monkeypatch.setattr(woo, "assert_public_dns", lambda _url: None)

    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/wp-json/wc/v3/products"
        assert request.url.params["per_page"] == "2"
        assert request.headers["Authorization"] == "Basic " + base64.b64encode(b"ck_abc:cs_xyz").decode()
        return httpx.Response(200, json=[{"id": 11, "name": "Lamp", "sku": "D-1"}])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        raw = woo.list_woocommerce("https://store.example.com", "ck_abc", "cs_xyz", "products", limit=2, client=client)
    assert woo.preview_woocommerce_products(raw) == [{
        "id": 11, "name": "Lamp", "sku": "D-1", "type": None,
        "status": None, "stock_status": None, "stock_quantity": None,
    }]


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (302, "WOO_REDIRECT_DENIED"),
        (401, "WOO_AUTH_FAILED"),
        (403, "WOO_AUTH_FAILED"),
        (404, "WOO_API_NOT_FOUND"),
        (500, "WOO_PROVIDER_ERROR"),
    ],
)
def test_provider_errors_do_not_leak_bodies(monkeypatch, status, code):
    monkeypatch.setattr(woo, "assert_public_dns", lambda _url: None)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(status, headers={"Location": "http://localhost/"}, text="secret-private-body")
        )
    ) as client:
        with pytest.raises(woo.WooCommerceError) as exc:
            woo.list_woocommerce("https://store.example.com", "ck", "cs", "orders", client=client)
    assert exc.value.code == code
    assert "secret-private-body" not in str(exc.value)


def test_order_preview_redacts_personal_data():
    order = {
        "id": 99, "number": "99", "status": "processing", "currency": "COP",
        "total": "120000", "billing": {"email": "private@example.com"},
        "shipping": {"phone": "5551234"}, "line_items": [{"id": 1}],
    }
    result = woo.preview_woocommerce_orders([order])
    assert result == [{
        "id": 99, "number": "99", "status": "processing", "currency": "COP",
        "total": "120000", "line_items_count": 1,
    }]
    assert "private@example.com" not in repr(result)


def test_unsupported_resource_does_not_send_request():
    with pytest.raises(woo.WooCommerceError) as exc:
        woo.list_woocommerce("https://example.com", "ck", "cs", "../../internal")
    assert exc.value.code == "WOO_UNSUPPORTED_RESOURCE"


def test_invalid_response_is_not_accepted(monkeypatch):
    monkeypatch.setattr(woo, "assert_public_dns", lambda _url: None)
    with httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"error": True}))) as client:
        with pytest.raises(woo.WooCommerceError) as exc:
            woo.list_woocommerce("https://example.com", "ck", "cs", "products", client=client)
    assert exc.value.code == "WOO_INVALID_RESPONSE"
