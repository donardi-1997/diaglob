"""Shopify-only short-lived ID token and explicit member-bound store reads."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import pytest

from app.api.shopify_embedded import embedded_store_data

AUTH = HTTPAuthorizationCredentials(scheme="Bearer", credentials="shopify-token")
IDENTITY = {"shop": "diaglob-poc.myshopify.com", "subject": "staff-123"}


@pytest.mark.parametrize("section", ["products", "orders"])
def test_data_rejects_missing_shopify_session(section):
    with pytest.raises(HTTPException) as exc:
        embedded_store_data(section, credentials=None, db=MagicMock())
    assert exc.value.status_code == 401


def test_data_rejects_unknown_module_before_query():
    with pytest.raises(HTTPException) as exc:
        embedded_store_data("customers", credentials=AUTH, db=MagicMock())
    assert exc.value.status_code == 404


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value=IDENTITY)
@patch("app.api.shopify_embedded.authorize_embedded_identity", return_value={"organization_id": 7, "store_id": 20})
def test_products_only_return_safe_fields(authz, token):
    row = SimpleNamespace(id=3, title="Zapato", vendor="Proveedor", active=True, shopify_product_id="123")
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [row]
    db.query.return_value.filter.return_value.count.return_value = 1
    result = embedded_store_data("products", credentials=AUTH, db=db)
    assert result["items"] == [{"id": 3, "title": "Zapato", "vendor": "Proveedor", "active": True, "shopify_product_id": "123"}]
    authz.assert_called_once_with(db, IDENTITY)


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value=IDENTITY)
@patch("app.api.shopify_embedded.authorize_embedded_identity", return_value={"organization_id": 7, "store_id": 20})
def test_orders_redact_personal_data(authz, token):
    row = SimpleNamespace(id=9, order_number="#1001", total_amount=25000, currency="COP",
                          financial_status="paid", fulfillment_status="unfulfilled", customer_email="private@test.com")
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [row]
    db.query.return_value.filter.return_value.count.return_value = 1
    result = embedded_store_data("orders", credentials=AUTH, db=db)
    assert result["items"][0]["order_number"] == "#1001"
    assert "customer_email" not in str(result)
    assert result["limit"] == 20


def test_embedded_home_uses_link_code_not_password(monkeypatch):
    from app.api.shopify_embedded import shopify_embedded_home
    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "c5fc9aed710462d41767477fa9e595c0")
    html = shopify_embedded_home().body.decode("utf-8")
    assert 'data-panel="home"' in html
    assert 'data-panel="products"' in html
    assert 'data-panel="orders"' in html
    assert 'data-panel="conversations"' not in html
    assert 'data-panel="automations"' not in html
    assert 'id="link-form"' in html
    assert 'id="login-form"' not in html
    assert "AWSCognitoIdentityProviderService.InitiateAuth" not in html
    assert "localStorage" not in html
    assert "X-Diaglob-Authorization" not in html


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value=IDENTITY)
@patch("app.api.shopify_embedded.authorize_embedded_identity", return_value={"organization_id": 7, "store_id": 20})
def test_embedded_metrics_count_saved_products_including_inactive_historical_rows(authz, token):
    # Sync fetched=5, created=3, updated=2 can leave 6 saved records if
    # three existed before the import. The summary counts saved rows, not
    # products fetched during the last sync run.
    from datetime import datetime
    from app.api.shopify_embedded import embedded_metrics

    db = MagicMock()
    db.query.return_value.filter_by.return_value.count.side_effect = [6, 1]
    db.query.return_value.filter_by.return_value.first.return_value = SimpleNamespace(
        last_sync_at=datetime(2026, 10, 20, 21, 16, 27)
    )
    result = embedded_metrics(credentials=AUTH, db=db)
    assert result["products"] == 6
    assert result["orders"] == 1
    assert result["last_product_sync"] == "2026-10-20T21:16:27"
    assert result["mode"] == "read_only"
    authz.assert_called_once_with(db, IDENTITY)


def test_shopify_embedded_summary_labels_saved_count_and_formats_utc_to_bogota(monkeypatch):
    from app.api.shopify_embedded import shopify_embedded_home

    monkeypatch.setenv("SHOPIFY_CLIENT_ID", "c5fc9aed710462d41767477fa9e595c0")
    html = shopify_embedded_home().body.decode("utf-8")
    assert "Productos guardados en DIAGLOB" in html
    assert "Productos sincronizados" not in html
    assert "function formatProductSyncTime(raw)" in html
    assert "timeZone: 'America/Bogota'" in html
    assert "new Date(normalized)" in html
    assert "raw + 'Z'" in html
    assert "formatProductSyncTime(data.last_product_sync)" in html
    assert "Fecha no disponible" in html
