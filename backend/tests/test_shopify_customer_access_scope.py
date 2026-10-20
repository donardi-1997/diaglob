"""Regression tests for Shopify/commerce customer PCD read authorization.

All customer fixtures are synthetic; no real customer data or credentials.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from app.api.customers import (
    _authorized_customer_store_id,
    _validate_store,
    get_customers_summary,
    list_customer_classifications,
    list_customer_audience,
    list_customers,
    get_customer_detail,
)


def _member(*, stores=(), all_stores=False, organization_id=41):
    return SimpleNamespace(
        organization_id=organization_id,
        user_id=51,
        role="operator",
        all_stores=all_stores,
        stores=list(stores),
    )


def _store(store_id, *, organization_id=41, active=True, deleted=False):
    return SimpleNamespace(
        id=store_id, organization_id=organization_id,
        active=active, deleted=deleted,
    )


def test_store_restricted_staff_cannot_read_unscoped_org_customer_data():
    member = _member(stores=[_store(100), _store(101)])
    with pytest.raises(HTTPException) as exc:
        _authorized_customer_store_id(Mock(), member, None)
    assert exc.value.status_code == 403


def test_store_restricted_staff_with_no_active_grants_denied():
    member = _member(stores=[_store(100, active=False), _store(101, deleted=True)])
    with pytest.raises(HTTPException) as exc:
        _authorized_customer_store_id(Mock(), member, None)
    assert exc.value.status_code == 403


def test_single_active_assigned_store_is_used_automatically():
    member = _member(stores=[
        _store(100, active=False),
        _store(101),
        _store(102, organization_id=99),
    ])
    assert _authorized_customer_store_id(Mock(), member, None) == 101


def test_org_wide_owner_can_keep_unscoped_aggregate_view():
    assert _authorized_customer_store_id(Mock(), _member(all_stores=True), None) is None


def test_store_access_check_cannot_be_bypassed_with_foreign_store_id():
    member = _member(stores=[_store(100)])
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = _store(101)
    with pytest.raises(HTTPException) as exc:
        _validate_store(db, member, 101)
    assert exc.value.status_code == 403


def test_nonexistent_store_fails_closed():
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc:
        _validate_store(db, _member(all_stores=True), 100)
    assert exc.value.status_code == 404


@patch("app.api.customers._validate_store")
@patch("app.services.customer_classification_service.get_customer_classifications")
def test_store_classifications_route_requires_assigned_store(classifications, validate):
    # The endpoint's local import is not used here, unlike general customer endpoints.
    with patch("app.api.customers.get_customer_classifications", return_value={"items": []}):
        db = Mock()
        member = _member(stores=[_store(100)])
        def enforce(_db, membership, store_id):
            if store_id != 100:
                raise HTTPException(status_code=403, detail="Store access denied")
        validate.side_effect = enforce
        with pytest.raises(HTTPException) as exc:
            list_customer_classifications(store_id=101, membership=member, db=db)
        assert exc.value.status_code == 403


@patch("app.api.customers._validate_store")
@patch("app.api.customers.list_classified_audience_customers")
def test_audience_route_cannot_read_unassigned_store(service, validate):
    validate.side_effect = HTTPException(status_code=403, detail="Store access denied")
    with pytest.raises(HTTPException) as exc:
        list_customer_audience(store_id=102, membership=_member(), db=Mock())
    assert exc.value.status_code == 403
    service.assert_not_called()


@patch("app.customers.intelligence.get_customer_list")
def test_list_route_filters_to_single_allowed_store(service):
    service.return_value = {"items": [], "total": 0}
    member = _member(stores=[_store(100)])
    list_customers(membership=member, db=Mock())
    assert service.call_args.kwargs["store_id"] == 100


@patch("app.customers.intelligence.get_summary")
def test_summary_cannot_read_unscoped_org_with_multi_store_grant(service):
    with pytest.raises(HTTPException) as exc:
        get_customers_summary(
            membership=_member(stores=[_store(100), _store(101)]),
            db=Mock(),
        )
    assert exc.value.status_code == 403
    service.assert_not_called()


@patch("app.customers.intelligence.get_customer_detail")
def test_detail_cannot_probe_customers_without_scoped_store(service):
    with pytest.raises(HTTPException) as exc:
        get_customer_detail(
            customer_id=909,
            membership=_member(stores=[_store(100), _store(101)]),
            db=Mock(),
        )
    assert exc.value.status_code == 403
    service.assert_not_called()


def test_audit_event_has_no_customer_contact_or_query_params(caplog):
    from app.api.customers import _audit_customer_read
    import logging
    with caplog.at_level(logging.INFO, logger="app.api.customers"):
        _audit_customer_read(_member(stores=[_store(100)]), "list", 100)
    assert "CUSTOMER_PCD_READ" in caplog.text
    assert "organization_id=41" in caplog.text
    for forbidden in ("email=", "phone=", "address=", "customer_id=", "token="):
        assert forbidden not in caplog.text
