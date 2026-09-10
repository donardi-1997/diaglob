"""Regression tests for path-scoped commerce order authorization."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.orders import _require_membership_store_access


def test_restricted_membership_cannot_cross_store_boundary():
    membership = SimpleNamespace(
        all_stores=False,
        stores=[SimpleNamespace(id=2, active=True)],
    )

    with pytest.raises(HTTPException) as exc_info:
        _require_membership_store_access(membership, 1)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Store access denied"


def test_restricted_membership_can_access_assigned_store():
    membership = SimpleNamespace(
        all_stores=False,
        stores=[SimpleNamespace(id=2, active=True)],
    )

    _require_membership_store_access(membership, 2)


def test_all_store_membership_is_not_restricted_by_path_store():
    membership = SimpleNamespace(
        all_stores=True,
        stores=[],
    )

    _require_membership_store_access(membership, 999)
