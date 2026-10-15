"""Plan-store capacity contract for direct Diaglob accounts.

Shopify App Pricing remains shop-specific; these per-organization limits do
not authorize a second Shopify installation under one subscription.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.stores import ensure_active_store_capacity
from app.plan_limits import (
    get_limits_for_plan, get_organization_limits, organization_can_activate_store,
    organization_usage,
)
from app.plans import get_active_store_limit


@pytest.mark.parametrize(
    "plan,expected",
    [
        ("trial", 1),
        ("starter", 1),
        ("growth", 2),
        ("pro", 3),
        ("scale", 5),
    ],
)
def test_reconciled_plan_limits_match_legacy_store_catalog(plan, expected):
    org = SimpleNamespace(
        plan=plan, billing_provider="paddle", subscription_status="active",
    )
    assert get_organization_limits(org).active_stores == expected
    assert get_limits_for_plan(plan).active_stores == expected
    assert get_active_store_limit(plan) == expected
    assert organization_can_activate_store(org, expected - 1)
    assert not organization_can_activate_store(org, expected)


@pytest.mark.parametrize("plan,cap", [("pro", 3), ("scale", 5)])
def test_active_store_endpoint_rejects_new_activations_at_cap(plan, cap):
    org = SimpleNamespace(
        plan=plan, billing_provider="paddle", subscription_status="active",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = org

    with patch("app.api.stores.get_active_store_usage", return_value=cap - 1):
        assert ensure_active_store_capacity(db, organization_id=42) is None

    with patch("app.api.stores.get_active_store_usage", return_value=cap):
        with pytest.raises(HTTPException) as exc:
            ensure_active_store_capacity(db, organization_id=42)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "ACTIVE_STORE_LIMIT_REACHED"
    assert exc.value.detail["limit"] == cap
    assert exc.value.detail["used"] == cap
    assert exc.value.detail["remaining"] == 0
    assert db.add.call_count == 0
    assert db.delete.call_count == 0
    assert db.commit.call_count == 0


def test_existing_over_cap_stores_are_not_deleted_or_negative_reported():
    org = SimpleNamespace(
        plan="scale", billing_provider="paddle", subscription_status="active",
    )
    usage = organization_usage(org, active_stores=8, monthly_customers=50, members=2)
    assert usage["stores"] == {"used": 8, "limit": 5, "remaining": 0}
    assert not organization_can_activate_store(org, 8)


def test_shopify_inactive_entitlements_stay_suspended_after_cap_reduction():
    org = SimpleNamespace(
        plan="scale", billing_provider="shopify",
        subscription_status="inactive",
    )
    assert get_organization_limits(org).active_stores == 0
    assert not organization_can_activate_store(org, 0)
