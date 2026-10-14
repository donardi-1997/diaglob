"""Embedded access requires Cognito identity and an active store membership."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.shopify_embedded_authorization import authorize_embedded_store


def _fake_db(rows, scoped=True):
    db = MagicMock()
    db.query.return_value.join.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.limit.return_value.all.return_value = rows
    db.query.return_value.filter.return_value.first.return_value = object() if scoped else None
    return db


def _row(*, all_stores=True):
    return (
        SimpleNamespace(id=8),
        SimpleNamespace(id=20),
        SimpleNamespace(id=9, organization_id=7, all_stores=all_stores, role="admin"),
    )


@patch("app.services.shopify_embedded_authorization.verify_cognito_access_token", return_value={"sub": "member-123"})
def test_authorized_existing_membership(token_verifier):
    result = authorize_embedded_store(_fake_db([_row()]), "diaglob-poc.myshopify.com", "verified-token")
    assert result == {
        "authorized": True, "shop": "diaglob-poc.myshopify.com",
        "store_id": 20, "organization_id": 7, "role": "admin",
    }
    token_verifier.assert_called_once_with("verified-token")


@patch("app.services.shopify_embedded_authorization.verify_cognito_access_token", return_value={"sub": "member-123"})
@pytest.mark.parametrize("rows", [[], [_row(), _row()]])
def test_missing_or_ambiguous_membership_denied(token_verifier, rows):
    with pytest.raises(HTTPException) as exc:
        authorize_embedded_store(_fake_db(rows), "diaglob-poc.myshopify.com", "token")
    assert exc.value.status_code == 403


@patch("app.services.shopify_embedded_authorization.verify_cognito_access_token", return_value={"sub": "member-123"})
def test_scoped_membership_requires_store_assignment(token_verifier):
    with pytest.raises(HTTPException) as exc:
        authorize_embedded_store(_fake_db([_row(all_stores=False)], scoped=False), "diaglob-poc.myshopify.com", "token")
    assert exc.value.status_code == 403
