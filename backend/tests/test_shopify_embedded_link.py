"""Shopify session must not become an implicit DIAGLOB tenant credential."""
from unittest.mock import MagicMock, patch

import pytest

from app.services.shopify_embedded_link import installed_shop_status


@pytest.mark.parametrize("connections,expected", [
    ([], "needs_link"),
    ([object()], "connected"),
    ([object(), object()], "needs_link"),
])
def test_shopify_installation_lookup_fails_closed(connections, expected):
    db = MagicMock()
    db.query.return_value.join.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = connections
    db.query.return_value.filter.return_value.first.return_value = None
    assert installed_shop_status(db, "diaglob-poc.myshopify.com") == expected
    assert db.query.call_count == (2 if not connections else 1)


def test_embedded_response_never_grants_tenant_access():
    from app.api.shopify_embedded import verify_embedded_session
    from fastapi.security import HTTPAuthorizationCredentials
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="shopify-test-jwt")
    with patch("app.api.shopify_embedded.verify_shopify_id_token", return_value={
        "shop": "diaglob-poc.myshopify.com",
        "subject": "123",
    }), patch("app.api.shopify_embedded.installed_shop_status", return_value="connected"):
        result = verify_embedded_session(credentials=credentials, db=MagicMock())
    assert result["authenticated"] is True
    assert result["installation_status"] == "connected"
    assert result["tenant_authorized"] is False
    assert "organization_id" not in result
    assert "store_id" not in result


def test_pending_public_oauth_install_is_routed_to_account_onboarding():
    from app.services.shopify_embedded_link import installed_shop_status

    connected_lookup = MagicMock()
    connected_lookup.join.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = []
    pending_lookup = MagicMock()
    pending_lookup.filter.return_value.first.return_value = object()
    db = MagicMock()
    db.query.side_effect = [connected_lookup, pending_lookup]

    assert installed_shop_status(db, "fresh.myshopify.com") == "oauth_pending"


def test_embedded_home_offers_first_party_public_oauth_continuation():
    import os

    from app.api.shopify_embedded import shopify_embedded_home
    from app.shopify_app_config_audit import DIAGLOB_SHOPIFY_CLIENT_ID

    with patch.dict(os.environ, {"SHOPIFY_CLIENT_ID": DIAGLOB_SHOPIFY_CLIENT_ID}):
        response = shopify_embedded_home()

    assert response.status_code == 200
    assert "info.installation_status === 'oauth_pending'" in response.body.decode()
    assert 'href="https://diaglob.tech/shopify/install?authorized=1"' in response.body.decode()
