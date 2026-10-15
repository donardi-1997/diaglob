"""Embedded overview requires the Shopify session and a saved authorized user link."""
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from app.api.shopify_embedded import embedded_overview

AUTH = HTTPAuthorizationCredentials(scheme="Bearer", credentials="shopify-token")
IDENTITY = {"shop": "diaglob-poc.myshopify.com", "subject": "staff-123"}


def test_overview_requires_shopify_identity():
    with pytest.raises(HTTPException) as exc:
        embedded_overview(credentials=None, db=MagicMock())
    assert exc.value.status_code == 401


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value=IDENTITY)
@patch("app.api.shopify_embedded.authorize_embedded_identity", side_effect=HTTPException(403, "Link required"))
def test_overview_refuses_shopify_token_without_explicit_binding(authorization, shopify):
    with pytest.raises(HTTPException) as exc:
        embedded_overview(credentials=AUTH, db=MagicMock())
    assert exc.value.status_code == 403


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value=IDENTITY)
@patch("app.api.shopify_embedded.authorize_embedded_identity", return_value={"store_id": 2, "organization_id": 5})
def test_overview_returns_only_scoped_store_metadata(authorization, shopify):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        name="Diaglob POC", country_code="CO", currency="COP"
    )
    result = embedded_overview(credentials=AUTH, db=db)
    assert result["store_name"] == "Diaglob POC"
    assert result["shop"] == "diaglob-poc.myshopify.com"
    assert "organization_id" not in result
    assert "access_token" not in result
    authorization.assert_called_once_with(db, IDENTITY)
