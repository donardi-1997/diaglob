"""Mocked Dropi catalog paging contract; no requests leave the test process."""
import json

import httpx
import pytest

from app.integrations.dropi_catalog import normalize_product
from app.integrations.dropi_native import DropiNativeError, search_products
from app.services.dropi_catalog_service import attach_shopify_mappings


def test_catalog_normalization_redacts_nested_private_data():
    item = normalize_product({
        "id": 87,
        "name": "Zapatos",
        "sku": " SHOES ",
        "type": "VARIABLE",
        "stock": "8",
        "supplier_email": "private@example.com",
        "cost": 700,
        "variations": [
            {"id": 9, "sku": "SHOES-9", "stock": "3", "supplier_token": "sensitive"}
        ],
    })
    assert item["id"] == "87"
    assert item["stock"] == 8
    assert item["variants"][0] == {"id": "9", "sku": "SHOES-9", "stock": 3}
    assert "private@example.com" not in repr(item)
    assert "sensitive" not in repr(item)
    assert "cost" not in item


def test_unavailable_stock_is_unknown_not_zero():
    item = normalize_product({"id": 19, "name": "Unknown", "stock": "N/A"})
    assert item["stock"] is None
    assert item["variants_in_page"] is False
    assert item["variants"] == []


def test_catalog_pagination_and_filtered_search(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    pages = []
    def handler(request):
        body = json.loads(request.content)
        assert request.method == "POST"
        assert request.url.host == "api.dropi.co"
        assert request.url.path == "/integrations/products/index"
        assert request.headers["dropi-integration-key"] == "safe-test-token"
        assert body["keywords"] == "zapatos"
        assert body["pageSize"] == 2
        assert body["get_stock"] is False
        pages.append(body["startData"])
        objects = (
            [{"id": 101, "name": "A"}, {"id": 102, "name": "B"}]
            if body["startData"] == 1
            else [{"id": 103, "name": "C"}]
        )
        return httpx.Response(200, json={"isSuccess": True, "objects": objects})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = search_products(
            "safe-test-token", country_code="CO", page=1,
            limit=2, query=" zapatos ", client=client,
        )
        second = search_products(
            "safe-test-token", country_code="CO", page=2,
            limit=2, query=" zapatos ", client=client,
        )
    assert pages == [1, 2]
    assert first["has_more"] is True
    assert first["next_page"] == 2
    assert second["has_more"] is False
    assert second["next_page"] is None
    assert second["total"] is None
    assert second["items"][0]["id"] == "103"


@pytest.mark.parametrize("kw", ["a" * 101, "bad\nquery", "line\ttab"])
def test_search_rejects_invalid_search_strings(monkeypatch, kw):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    with pytest.raises(DropiNativeError, match="DROPI_INVALID_QUERY"):
        search_products("test", query=kw)


@pytest.mark.parametrize("page,limit", [(0, 20), (1001, 1), (1, 0), (1, 21), (True, 1)])
def test_search_rejects_out_of_bounds_paging(monkeypatch, page, limit):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    with pytest.raises(DropiNativeError, match="DROPI_INVALID_PAGE|DROPI_INVALID_LIMIT"):
        search_products("test", page=page, limit=limit)


def test_search_off_does_not_contact_provider(monkeypatch):
    monkeypatch.delenv("DROPI_NATIVE_API_ENABLED", raising=False)
    def fail(_):
        raise AssertionError("Network is disabled")
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(DropiNativeError, match="DROPI_PARTNER_APPROVAL_REQUIRED"):
            search_products("token", client=client)


def test_provider_over_limit_fails_closed(monkeypatch):
    monkeypatch.setenv("DROPI_NATIVE_API_ENABLED", "1")
    with httpx.Client(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"isSuccess": True, "objects": [{"id": i} for i in range(3)]})
    )) as client:
        with pytest.raises(DropiNativeError, match="DROPI_INVALID_RESPONSE"):
            search_products("token", limit=2, client=client)


def test_comparison_uses_explicit_mapping_not_sku_guess():
    product = normalize_product({"id": 44, "name": "Shirt", "sku": "SAME"})
    compared = attach_shopify_mappings([product], [])
    assert compared[0]["mapping_status"] == "unmapped"
    assert not compared[0]["shopify_mappings"]


def test_comparison_reports_sku_and_stock_differences():
    from types import SimpleNamespace
    product = normalize_product({
        "id": 44,
        "name": "Shirt",
        "variations": [{"id": 50, "sku": "DROP-50", "stock": 3}],
    })
    mapping = SimpleNamespace(active=True, external_product_id="44", external_variant_id="50")
    variant = SimpleNamespace(id=5, shopify_variant_id="shop-5", sku="SHOP-5", inventory_quantity=8)
    local_product = SimpleNamespace(shopify_product_id="shop-p", title="Shirt")
    result = attach_shopify_mappings([product], [(mapping, variant, local_product)])
    assert result[0]["mapping_status"] == "linked"
    assert result[0]["differences_detected"] is True
    assert result[0]["shopify_mappings"][0]["sku_check"] == "different"
    assert result[0]["shopify_mappings"][0]["stock_check"] == "different"


def test_comparison_does_not_invent_remote_variants():
    from types import SimpleNamespace
    product = normalize_product({"id": 44, "sku": "SAME"})
    mapping = SimpleNamespace(active=True, external_product_id="44", external_variant_id="unknown")
    variant = SimpleNamespace(id=7, shopify_variant_id="7", sku="SAME", inventory_quantity=5)
    local_product = SimpleNamespace(shopify_product_id="shop-7", title="Test")
    result = attach_shopify_mappings([product], [(mapping, variant, local_product)])
    assert result[0]["shopify_mappings"][0]["sku_check"] == "unknown"
    assert result[0]["shopify_mappings"][0]["stock_check"] == "unknown"
    assert result[0]["differences_detected"] is False
