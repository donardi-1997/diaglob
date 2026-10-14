"""Embedded overview never returns store metadata before dual authentication."""
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from app.api.shopify_embedded import embedded_overview


def test_overview_requires_shopify_identity():
    with pytest.raises(HTTPException) as exc:
        embedded_overview(credentials=None, diaglob_authorization="Bearer token", db=MagicMock())
    assert exc.value.status_code == 401


def test_overview_requires_cognito():
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="shopify")
    with pytest.raises(HTTPException) as exc:
        embedded_overview(credentials=credentials, diaglob_authorization=None, db=MagicMock())
    assert exc.value.status_code == 401


@patch("app.api.shopify_embedded.verify_shopify_id_token", return_value={"shop": "diaglob-poc.myshopify.com"})
@patch("app.api.shopify_embedded.authorize_embedded_store", return_value={"store_id": 2, "organization_id": 5})
def test_overview_returns_only_scoped_store_metadata(authorization, shopify):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        name="Diaglob POC", country_code="CO", currency="COP"
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="shopify-token")
    result = embedded_overview(credentials=credentials, diaglob_authorization="Bearer cognito-token", db=db)
    assert result["store_name"] == "Diaglob POC"
    assert result["shop"] == "diaglob-poc.myshopify.com"
    assert "organization_id" not in result
    assert "access_token" not in result
    authorization.assert_called_once_with(db, "diaglob-poc.myshopify.com", "cognito-token")
