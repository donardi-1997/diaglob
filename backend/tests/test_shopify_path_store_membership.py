"""Shopify paths must enforce tenant AND assigned-store access.

Synthetic data only: no merchant access, orders, or remote Shopify calls.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.shopify import router
from app.api.store_access import require_authorized_path_store
from app.models import Store


def _db_with_store(store):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = store
    return db


def _membership(*, all_stores=False, allowed=(7,)):
    return SimpleNamespace(
        organization_id=31,
        all_stores=all_stores,
        stores=[SimpleNamespace(id=store_id) for store_id in allowed],
    )


def test_restricted_member_cannot_access_unassigned_store():
    db = _db_with_store(SimpleNamespace(id=8, organization_id=31))
    with pytest.raises(HTTPException) as exc:
        require_authorized_path_store(8, _membership(), db)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Store access denied"
    db.query.assert_called_once_with(Store)


def test_restricted_member_can_access_assigned_store():
    store = SimpleNamespace(id=7, organization_id=31)
    assert require_authorized_path_store(
        7, _membership(), _db_with_store(store)
    ) is store


def test_unrestricted_member_can_access_organization_store():
    store = SimpleNamespace(id=8, organization_id=31)
    assert require_authorized_path_store(
        8, _membership(all_stores=True, allowed=()), _db_with_store(store)
    ) is store


@pytest.mark.parametrize("all_stores", [False, True])
def test_missing_or_foreign_tenant_store_fails_closed(all_stores):
    # SQL query applies organization_id AND deleted=false; no matching row.
    db = _db_with_store(None)
    with pytest.raises(HTTPException) as exc:
        require_authorized_path_store(
            99, _membership(all_stores=all_stores), db
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Store not found"
    assert len(db.query.return_value.filter.call_args.args) == 3


def test_every_shopify_store_path_requires_store_membership_guard():
    paths = []
    for route in router.routes:
        if "{store_id}" not in route.path:
            continue
        paths.append(route.path)
        assert any(
            dependency.dependency is require_authorized_path_store
            for dependency in route.dependencies
        ), f"Missing path authorization: {route.path}"
    assert len(paths) == 12
    assert "/api/stores/{store_id}/shopify/orders/{order_id}" in paths
    assert "/api/stores/{store_id}/shopify/connect" in paths
    assert "/api/stores/{store_id}/shopify/install/claim" in paths
    assert "/api/stores/{store_id}/shopify/install/claim-code" in paths
