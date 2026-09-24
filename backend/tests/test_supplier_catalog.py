"""CJ catalog service tests."""

from app.services import supplier_catalog as catalog


def test_list_products_flattens_v2_search_groups(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "token",
    )
    monkeypatch.setattr(
        catalog.cj_client,
        "list_products",
        lambda *_args, **_kwargs: {
            "content": [
                {
                    "productList": [
                        {
                            "id": "pid-1",
                            "nameEn": "Test Hoodie",
                            "sku": "SPU-1",
                            "bigImage": "https://example.test/p.jpg",
                            "sellPrice": "8.40",
                            "listedNum": 12,
                        }
                    ]
                }
            ],
            "totalRecords": 1,
            "totalPages": 1,
        },
    )

    result = catalog.list_cj_products(
        object(),
        1,
        2,
        query="hoodie",
        limit=20,
        page=1,
    )

    assert result["total"] == 1
    assert result["items"][0] == {
        "provider": "cj",
        "external_product_id": "pid-1",
        "title": "Test Hoodie",
        "sku": "SPU-1",
        "image_url": "https://example.test/p.jpg",
        "supplier_cost_usd": "8.40",
        "suggested_sell_price": None,
        "category_id": None,
        "category_name": None,
        "listed_count": 12,
    }


def test_stock_keeps_warehouse_provenance(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "token",
    )
    monkeypatch.setattr(
        catalog.cj_client,
        "get_stock",
        lambda *_args, **_kwargs: [
            {
                "areaId": "1",
                "areaEn": "China Warehouse",
                "countryCode": "CN",
                "totalInventoryNum": 10,
                "cjInventoryNum": 4,
                "factoryInventoryNum": 6,
            },
            {
                "areaId": "2",
                "areaEn": "US Warehouse",
                "countryCode": "US",
                "totalInventoryNum": 3,
                "cjInventoryNum": 3,
                "factoryInventoryNum": 0,
            },
        ],
    )

    result = catalog.get_cj_stock(object(), 1, 2, "vid-1")

    assert result["total_inventory"] == 13
    assert result["warehouses"][1]["country_code"] == "US"
    assert result["warehouses"][1]["total_inventory"] == 3


def test_freight_quote_normalizes_cost_and_eta(monkeypatch):
    monkeypatch.setattr(
        catalog,
        "get_valid_cj_access_token",
        lambda *_args, **_kwargs: "token",
    )
    monkeypatch.setattr(
        catalog.cj_client,
        "calculate_freight",
        lambda *_args, **_kwargs: [
            {
                "logisticName": "USPS+",
                "logisticAging": "2-5",
                "logisticPrice": 4.71,
                "totalPostageFee": 5.10,
                "taxesFee": 0.25,
                "clearanceOperationFee": 0.14,
            }
        ],
    )

    result = catalog.quote_cj_freight(
        object(),
        1,
        2,
        start_country_code="CN",
        end_country_code="US",
        zip_code="10001",
        items=[{"variant_id": "vid-1", "quantity": 1}],
    )

    option = result["options"][0]
    assert option["logistics_name"] == "USPS+"
    assert option["transit_time"] == "2-5"
    assert option["price_usd"] == 5.10
    assert option["base_price_usd"] == 4.71
