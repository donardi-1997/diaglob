"""Billing preview must not ignore paused or revoked Shopify merchant bindings.

All tests are local SQLite; no Shopify API, Partner API, charges or writes
to a production database.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.billing import preview_shopify_billing_reconciliation
from app.db import Base
from app.models import CommerceConnection, Organization, Store


@pytest.fixture
def billing_sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(
            name="Shopify Billing Org",
            slug="shopify-billing-tenant-guard",
            billing_provider="shopify",
            plan="starter",
            subscription_status="active",
        )
        db.add(org)
        db.flush()
        member = SimpleNamespace(
            role="owner", organization=org, organization_id=org.id
        )
        yield db, org, member
    engine.dispose()


def add_shop(db, org, name, *, active=True, deleted=False, status="connected"):
    store = Store(
        organization_id=org.id,
        name=name,
        slug=name.lower(),
        country_code="CO",
        currency="COP",
        timezone="America/Bogota",
        active=active,
        deleted=deleted,
    )
    db.add(store)
    db.flush()
    connection = CommerceConnection(
        organization_id=org.id,
        store_id=store.id,
        provider="shopify",
        external_store_url=f"{name.lower()}.myshopify.com",
        access_token_encrypted="only-a-synthetic-token",
        status=status,
    )
    db.add(connection)
    db.commit()
    return store, connection


@pytest.mark.parametrize(
    "second_store_flags",
    [
        {"active": False, "status": "connected"},
        {"deleted": True, "status": "connected"},
        {"status": "revoked"},
        {"status": "error"},
        {},
    ],
)
def test_multiple_shopify_bindings_cannot_be_hidden_from_billing_review(
    billing_sandbox, second_store_flags
):
    db, org, membership = billing_sandbox
    add_shop(db, org, "primary")
    add_shop(db, org, "secondary", **second_store_flags)
    with patch("app.api.billing.preview_shopify_entitlement_reconciliation") as partner:
        with pytest.raises(HTTPException) as error:
            preview_shopify_billing_reconciliation(membership=membership, db=db)
    assert error.value.status_code == 409
    assert error.value.detail == {
        "code": "SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED"
    }
    partner.assert_not_called()


@pytest.mark.parametrize(
    "flags", [
        {"active": False}, {"deleted": True}, {"status": "revoked"},
        {"status": "error"},
    ]
)
def test_single_ineligible_shop_connection_cannot_be_previewed(
    billing_sandbox, flags
):
    db, org, membership = billing_sandbox
    add_shop(db, org, "primary", **flags)
    with patch("app.api.billing.preview_shopify_entitlement_reconciliation") as partner:
        with pytest.raises(HTTPException) as error:
            preview_shopify_billing_reconciliation(membership=membership, db=db)
    assert error.value.status_code == 409
    assert error.value.detail == {
        "code": "SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED"
    }
    partner.assert_not_called()


def test_exactly_one_active_shop_may_preview_without_applying_plan(
    billing_sandbox,
):
    db, org, membership = billing_sandbox
    _, connection = add_shop(db, org, "primary")
    preview = SimpleNamespace(
        status="plan_transition_requires_review",
        requires_review=True,
        current_plan="starter",
        target_plan="growth",
        target_billing_period_months=1,
        organization_id=org.id,
    )
    with patch(
        "app.api.billing.preview_shopify_entitlement_reconciliation",
        return_value=preview,
    ) as partner:
        result = preview_shopify_billing_reconciliation(
            membership=membership, db=db,
        )
    partner.assert_called_once_with(
        org, connection, connected_shopify_store_count=1
    )
    assert result["applied"] is False
    assert result["requires_review"] is True
    assert result["target_plan"] == "growth"
    assert org.plan == "starter"
    assert "only-a-synthetic-token" not in str(result)


def test_cross_tenant_connection_is_not_eligible_for_other_org(
    billing_sandbox,
):
    db, org, membership = billing_sandbox
    another = Organization(
        name="Second",
        slug="second-shopify-tenant",
        billing_provider="shopify",
    )
    db.add(another)
    db.commit()
    add_shop(db, another, "other-tenant")
    with patch("app.api.billing.preview_shopify_entitlement_reconciliation") as partner:
        with pytest.raises(HTTPException) as error:
            preview_shopify_billing_reconciliation(membership=membership, db=db)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED"
    partner.assert_not_called()


def test_billing_preview_requires_owner_or_manager(billing_sandbox):
    db, org, member = billing_sandbox
    add_shop(db, org, "primary")
    member.role = "employee"
    with patch("app.api.billing.preview_shopify_entitlement_reconciliation") as partner:
        with pytest.raises(HTTPException) as error:
            preview_shopify_billing_reconciliation(membership=member, db=db)
    assert error.value.status_code == 403
    partner.assert_not_called()
