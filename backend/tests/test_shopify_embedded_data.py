"""Dual-auth and shop-scoped read-only embedded catalog tests."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import pytest

from app.api.shopify_embedded import embedded_store_data

AUTH = HTTPAuthorizationCredentials(scheme="Bearer", credentials="shopify-token")


@pytest.mark.parametrize("section", ["products", "orders"])
def test_data_requires_both_tokens(section):
    with pytest.raises(HTTPException) as exc:
        embedded_store_data(section, credentials=AUTH, diaglob_authorization=None, db=MagicMock())
    assert exc.value.status_code == 401


def test_data_rejects_unknown_module_before_query():
    with pytest.raises(HTTPException) as exc:
        embedded_store_data("customers", credentials=AUTH, diaglob_authorization="Bearer cognito", db=MagicMock())
    assert exc.value.status_code == 404


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value={"shop": "diaglob-poc.myshopify.com"})
@patch("app.api.shopify_embedded.authorize_embedded_store", return_value={"organization_id": 7, "store_id": 20})
def test_products_only_return_safe_fields(authz, token):
    row = SimpleNamespace(id=3, title="Zapato", vendor="Proveedor", active=True, shopify_product_id="123")
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [row]
    db.query.return_value.filter.return_value.count.return_value = 1
    result = embedded_store_data("products", credentials=AUTH, diaglob_authorization="Bearer cognito", db=db)
    assert result["items"] == [{"id": 3, "title": "Zapato", "vendor": "Proveedor", "active": True, "shopify_product_id": "123"}]
    authz.assert_called_once_with(db, "diaglob-poc.myshopify.com", "cognito")


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value={"shop": "diaglob-poc.myshopify.com"})
@patch("app.api.shopify_embedded.authorize_embedded_store", return_value={"organization_id": 7, "store_id": 20})
def test_orders_redact_personal_data(authz, token):
    row = SimpleNamespace(id=9, order_number="#1001", total_amount=25000, currency="COP",
                          financial_status="paid", fulfillment_status="unfulfilled", customer_email="private@test.com")
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [row]
    db.query.return_value.filter.return_value.count.return_value = 1
    result = embedded_store_data("orders", credentials=AUTH, diaglob_authorization="Bearer cognito", db=db)
    assert result["items"][0]["order_number"] == "#1001"
    assert "customer_email" not in str(result)
    assert result["limit"] == 20
