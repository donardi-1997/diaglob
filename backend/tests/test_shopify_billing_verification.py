"""Read-only Shopify App Pricing checks with durable, non-entitling evidence."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.billing import (
    check_shopify_billing_reconciliation,
    get_shopify_billing_reconciliation_history,
)
from app.db import Base
from app.models import (
    CommerceConnection, Organization, ShopifyBillingVerification, Store,
)
from app.services.shopify_billing_verification import (
    ShopifyBillingEvidenceError,
    list_shopify_billing_verifications,
    record_shopify_billing_verification,
)


@pytest.fixture
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(
            name="Synthetic Partner Organization",
            slug="synthetic-billing-audit",
            billing_provider="shopify",
            plan="starter",
            billing_period_months=1,
            subscription_status="active",
        )
        db.add(org)
        db.flush()
        membership = SimpleNamespace(
            organization_id=org.id, organization=org, role="owner",
        )
        store = Store(
            organization_id=org.id,
            name="Synthetic Store",
            slug="synthetic-store",
            country_code="CO",
            currency="COP",
            timezone="America/Bogota",
            active=True,
        )
        db.add(store)
        db.flush()
        connection = CommerceConnection(
            organization_id=org.id,
            store_id=store.id,
            provider="shopify",
            external_store_url="synthetic-billing.myshopify.com",
            access_token_encrypted="SECRET_SYNTHETIC_TOKEN",
            status="connected",
            connected_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.add(connection)
        db.commit()
        yield db, org, store, connection, membership
    engine.dispose()


def _preview(org, *, target="growth", status="plan_transition_requires_review"):
    return {
        "organization_id": org.id,
        "current_plan": org.plan,
        "target_plan": target,
        "target_billing_period_months": 1 if target is not None else None,
        "status": status,
        "requires_review": True,
        "applied": False,
    }


def test_check_persists_one_restricted_audit_row_without_entitlements(sandbox):
    db, org, store, connection, member = sandbox
    with patch(
        "app.api.billing.preview_shopify_billing_reconciliation",
        return_value=_preview(org),
    ) as partner:
        result = check_shopify_billing_reconciliation(membership=member, db=db)
    partner.assert_called_once()
    assert result["target_plan"] == "growth"
    assert result["requires_review"] is True
    assert result["applied"] is False
    assert type(result["verification_id"]) is int
    db.expire_all()
    assert db.query(ShopifyBillingVerification).count() == 1
    receipt = db.query(ShopifyBillingVerification).one()
    assert receipt.organization_id == org.id
    assert receipt.store_id == store.id
    assert receipt.connection_id == connection.id
    assert receipt.installation_connected_at == connection.connected_at
    assert org.plan == "starter"
    assert org.billing_provider == "shopify"
    assert connection.access_token_encrypted == "SECRET_SYNTHETIC_TOKEN"
    assert "SECRET_SYNTHETIC_TOKEN" not in str(result)
    assert "synthetic-billing.myshopify.com" not in str(result)


def test_inactive_subscription_can_be_recorded_but_does_not_remove_plan(sandbox):
    db, org, _, _, member = sandbox
    inactive = _preview(
        org, target=None, status="subscription_inactive_requires_review",
    )
    with patch(
        "app.api.billing.preview_shopify_billing_reconciliation",
        return_value=inactive,
    ):
        result = check_shopify_billing_reconciliation(membership=member, db=db)
    assert result["target_plan"] is None
    assert result["applied"] is False
    assert org.plan == "starter"


def test_reinstall_during_partner_request_invalidates_original_epoch(sandbox):
    db, org, _, connection, member = sandbox
    original = connection.connected_at

    def simulate_reinstall(*, membership, db):
        connection.connected_at = datetime.utcnow()
        db.commit()
        return _preview(org)

    with patch(
        "app.api.billing.preview_shopify_billing_reconciliation",
        side_effect=simulate_reinstall,
    ):
        with pytest.raises(HTTPException) as exc:
            check_shopify_billing_reconciliation(membership=member, db=db)
    assert exc.value.status_code == 409
    assert exc.value.detail == {"code": "SHOPIFY_BILLING_STATE_CHANGED"}
    assert db.query(ShopifyBillingVerification).count() == 0
    assert connection.connected_at != original


def test_tenant_plan_change_during_partner_request_invalidates_check(sandbox):
    db, org, _, _, member = sandbox

    def simulate_plan_change(*, membership, db):
        org.plan = "pro"
        db.commit()
        return _preview(SimpleNamespace(id=org.id, plan="starter"))

    with patch(
        "app.api.billing.preview_shopify_billing_reconciliation",
        side_effect=simulate_plan_change,
    ):
        with pytest.raises(HTTPException) as exc:
            check_shopify_billing_reconciliation(membership=member, db=db)
    assert exc.value.status_code == 409
    assert db.query(ShopifyBillingVerification).count() == 0


def test_multiple_bindings_rejected_before_partner_request(sandbox):
    db, org, _, _, member = sandbox
    second = Store(
        organization_id=org.id, name="Second Shop", slug="second-shop",
        country_code="CO", currency="COP", timezone="UTC", active=False,
    )
    db.add(second)
    db.flush()
    db.add(CommerceConnection(
        organization_id=org.id, store_id=second.id,
        provider="shopify",
        external_store_url="second-synthetic-shop.myshopify.com",
        status="revoked",
    ))
    db.commit()
    with patch("app.api.billing.preview_shopify_billing_reconciliation") as provider:
        with pytest.raises(HTTPException) as exc:
            check_shopify_billing_reconciliation(membership=member, db=db)
    assert exc.value.status_code == 409
    provider.assert_not_called()
    assert db.query(ShopifyBillingVerification).count() == 0


@pytest.mark.parametrize("role", ["employee", "viewer", "analyst"])
def test_non_billing_roles_cannot_check_or_read_history(sandbox, role):
    db, _, _, _, membership = sandbox
    membership.role = role
    with patch("app.api.billing.preview_shopify_billing_reconciliation") as provider:
        with pytest.raises(HTTPException) as exc:
            check_shopify_billing_reconciliation(membership=membership, db=db)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            get_shopify_billing_reconciliation_history(
                membership=membership, db=db, limit=20,
            )
        assert exc.value.status_code == 403
    provider.assert_not_called()


def test_cross_tenant_history_isolation_and_no_token_exposure(sandbox):
    db, org, store, connection, membership = sandbox
    record_shopify_billing_verification(
        db, organization_id=org.id,
        store_id=store.id, connection_id=connection.id,
        installation_connected_at=connection.connected_at,
        preview=_preview(org),
    )
    other = Organization(
        name="Unrelated Merchant", slug="other-billing-history",
        billing_provider="shopify", plan="starter",
    )
    db.add(other)
    db.commit()
    first = get_shopify_billing_reconciliation_history(
        membership=membership, db=db, limit=20,
    )
    second = get_shopify_billing_reconciliation_history(
        membership=SimpleNamespace(
            organization_id=other.id, organization=other, role="manager",
        ),
        db=db, limit=20,
    )
    assert len(first["items"]) == 1
    assert second["items"] == []
    assert "SECRET_SYNTHETIC_TOKEN" not in str(first)
    assert "synthetic-billing.myshopify.com" not in str(first)
    assert "shop_gid" not in str(first)
    assert "handle" not in str(first)
    assert first["applied"] is False


def test_billing_provider_switch_invalidates_verification(sandbox):
    db, org, store, connection, _ = sandbox
    org.billing_provider = "paddle"
    db.commit()
    with pytest.raises(ShopifyBillingEvidenceError, match="STATE_CHANGED"):
        record_shopify_billing_verification(
            db, organization_id=org.id,
            store_id=store.id, connection_id=connection.id,
            installation_connected_at=connection.connected_at,
            preview=_preview(org),
        )
    assert db.query(ShopifyBillingVerification).count() == 0


def test_invalid_provider_evidence_never_produces_a_record(sandbox):
    db, org, store, connection, _ = sandbox
    invalid = {**_preview(org), "applied": True}
    with pytest.raises(ShopifyBillingEvidenceError, match="EVIDENCE_INVALID"):
        record_shopify_billing_verification(
            db, organization_id=org.id,
            store_id=store.id, connection_id=connection.id,
            installation_connected_at=connection.connected_at,
            preview=invalid,
        )
    assert db.query(ShopifyBillingVerification).count() == 0


def test_verification_history_limit_is_bounded(sandbox):
    db, org, _, _, _ = sandbox
    for invalid in (0, 51, -10, True):
        with pytest.raises(ShopifyBillingEvidenceError, match="HISTORY_INVALID"):
            list_shopify_billing_verifications(
                db, organization_id=org.id, limit=invalid,
            )
