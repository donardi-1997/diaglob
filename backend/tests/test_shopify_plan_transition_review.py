"""Staged Shopify plan reviews: no actual entitlement or payment operations."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.billing import (
    ShopifyTransitionReviewRequest,
    get_shopify_plan_transition_proposals,
    propose_shopify_plan_transition,
)
from app.db import Base
from app.models import (
    CommerceConnection, Organization, ShopifyBillingVerification,
    ShopifyPlanTransitionReview, Store,
)
from app.services.shopify_plan_transition_review import (
    ShopifyTransitionReviewError,
    activate_shopify_plan_transition,
    prepare_shopify_plan_transition,
)


@pytest.fixture
def sandbox():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        org = Organization(
            name="Shopify Staging", slug="shopify-review-only",
            billing_provider="shopify", plan="starter",
            billing_period_months=1, active=True,
        )
        db.add(org)
        db.flush()
        store = Store(
            organization_id=org.id,
            name="Synthetic Shopify",
            slug="synthetic-shopify-review",
            country_code="CO", currency="COP",
            timezone="America/Bogota", active=True,
        )
        db.add(store)
        db.flush()
        connection = CommerceConnection(
            organization_id=org.id, store_id=store.id,
            provider="shopify",
            external_store_url="synthetic-review.myshopify.com",
            status="connected",
            access_token_encrypted="PRIVATE_SYNTHETIC_TOKEN",
            connected_at=datetime.utcnow() - timedelta(hours=1),
        )
        db.add(connection)
        db.flush()
        verified = ShopifyBillingVerification(
            organization_id=org.id, store_id=store.id,
            connection_id=connection.id,
            status="plan_transition_requires_review",
            current_plan="starter", target_plan="growth",
            target_period_months=1,
            installation_connected_at=connection.connected_at,
            observed_at=datetime.utcnow(),
        )
        db.add(verified)
        db.commit()
        member = SimpleNamespace(
            role="owner", organization_id=org.id, organization=org,
        )
        yield db, org, store, connection, verified, member
    engine.dispose()


def _prepare(sandbox):
    db, org, _, _, verification, _ = sandbox
    return prepare_shopify_plan_transition(
        db, organization_id=org.id, verification_id=verification.id,
    )


def test_review_stage_is_idempotent_and_never_applies_billing(sandbox):
    db, org, _, connection, verification, _ = sandbox
    first = _prepare(sandbox)
    second = _prepare(sandbox)
    assert second == first
    assert first["status"] == "pending_review"
    assert first["requires_review"] is True
    assert first["applied"] is False
    assert db.query(ShopifyPlanTransitionReview).count() == 1
    db.expire_all()
    assert org.plan == "starter"
    assert org.billing_period_months == 1
    assert org.billing_provider == "shopify"
    assert connection.access_token_encrypted == "PRIVATE_SYNTHETIC_TOKEN"
    assert "PRIVATE_SYNTHETIC_TOKEN" not in str(first)
    assert "myshopify.com" not in str(first)
    assert "shop_gid" not in str(first)
    assert first["verification_id"] == verification.id


@pytest.mark.parametrize("minutes", [10, 11, 90])
def test_expired_verification_never_becomes_new_pending_review(sandbox, minutes):
    db, _, _, _, verified, _ = sandbox
    verified.observed_at = datetime.utcnow() - timedelta(minutes=minutes)
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="STALE_VERIFICATION"):
        _prepare(sandbox)
    assert db.query(ShopifyPlanTransitionReview).count() == 0


def test_reinstall_or_revocation_invalidates_preparation(sandbox):
    db, org, _, connection, verification, _ = sandbox
    connection.connected_at = datetime.utcnow()
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="INSTALLATION_OR_PLAN_CHANGED"):
        _prepare(sandbox)
    assert db.query(ShopifyPlanTransitionReview).count() == 0
    connection.connected_at = verification.installation_connected_at
    connection.status = "revoked"
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="INSTALLATION_OR_PLAN_CHANGED"):
        _prepare(sandbox)


def test_plan_switch_and_paddle_migration_fail_closed(sandbox):
    db, org, _, _, _, _ = sandbox
    org.plan = "pro"
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="INSTALLATION_OR_PLAN_CHANGED"):
        _prepare(sandbox)
    org.plan = "starter"
    org.billing_provider = "paddle"
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="INSTALLATION_OR_PLAN_CHANGED"):
        _prepare(sandbox)


def test_changed_current_shop_count_prevents_staging(sandbox):
    db, org, _, _, _, _ = sandbox
    store2 = Store(
        organization_id=org.id, name="Paused",
        slug="paused-shopify", country_code="CO", currency="COP",
        timezone="UTC", active=False,
    )
    db.add(store2)
    db.flush()
    db.add(CommerceConnection(
        organization_id=org.id, store_id=store2.id, provider="shopify",
        external_store_url="paused-myshop.myshopify.com", status="revoked",
    ))
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="INSTALLATION_OR_PLAN_CHANGED"):
        _prepare(sandbox)
    assert db.query(ShopifyPlanTransitionReview).count() == 0


def test_newer_verification_invalidates_older_evidence(sandbox):
    db, org, store, conn, verification, _ = sandbox
    db.add(ShopifyBillingVerification(
        organization_id=org.id, store_id=store.id,
        connection_id=conn.id, status="plan_transition_requires_review",
        current_plan="starter", target_plan="pro",
        target_period_months=1,
        installation_connected_at=conn.connected_at,
        observed_at=datetime.utcnow() + timedelta(seconds=1),
    ))
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="STALE_VERIFICATION"):
        _prepare(sandbox)


def test_other_tenant_cannot_replay_known_verification_id(sandbox):
    db, org, _, _, verification, _ = sandbox
    foreign = Organization(
        name="Other Tenant", slug="other-tenant-shopify-review",
        billing_provider="shopify", plan="starter",
    )
    db.add(foreign)
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="NOT_FOUND"):
        prepare_shopify_plan_transition(
            db, organization_id=foreign.id, verification_id=verification.id,
        )


def test_only_one_live_review_per_tenant_even_with_different_verification(sandbox):
    db, org, store, conn, _, _ = sandbox
    first = _prepare(sandbox)
    new = ShopifyBillingVerification(
        organization_id=org.id, store_id=store.id,
        connection_id=conn.id, status="plan_transition_requires_review",
        current_plan="starter", target_plan="pro", target_period_months=1,
        installation_connected_at=conn.connected_at, observed_at=datetime.utcnow(),
    )
    db.add(new)
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="ALREADY_PENDING"):
        prepare_shopify_plan_transition(
            db, organization_id=org.id, verification_id=new.id,
        )
    assert db.query(ShopifyPlanTransitionReview).count() == 1
    assert first["applied"] is False


def test_stale_pending_slot_is_released_transactionally(sandbox):
    db, org, store, conn, _, _ = sandbox
    first = _prepare(sandbox)
    old = db.query(ShopifyPlanTransitionReview).one()
    old.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.add(ShopifyBillingVerification(
        organization_id=org.id, store_id=store.id,
        connection_id=conn.id, status="plan_transition_requires_review",
        current_plan="starter", target_plan="pro", target_period_months=1,
        installation_connected_at=conn.connected_at, observed_at=datetime.utcnow(),
    ))
    db.commit()
    last = db.query(ShopifyBillingVerification).order_by(
        ShopifyBillingVerification.id.desc()
    ).first()
    second = prepare_shopify_plan_transition(
        db, organization_id=org.id, verification_id=last.id,
    )
    db.expire_all()
    assert db.query(ShopifyPlanTransitionReview).count() == 2
    assert db.get(ShopifyPlanTransitionReview, first["id"]).status == "stale"
    assert second["status"] == "pending_review"


def test_non_owner_cannot_propose_and_history_is_tenant_scoped(sandbox):
    db, org, _, _, verified, member = sandbox
    member.role = "manager"
    with pytest.raises(HTTPException) as exc:
        propose_shopify_plan_transition(
            payload=ShopifyTransitionReviewRequest(verification_id=verified.id),
            membership=member, db=db,
        )
    assert exc.value.status_code == 403
    member.role = "owner"
    result = propose_shopify_plan_transition(
        payload=ShopifyTransitionReviewRequest(verification_id=verified.id),
        membership=member, db=db,
    )
    assert result["applied"] is False
    items = get_shopify_plan_transition_proposals(
        membership=member, db=db, limit=20,
    )
    assert len(items["items"]) == 1
    assert items["applied"] is False
    foreign = Organization(
        name="Other Org", slug="another-shopify-review-history",
        billing_provider="shopify",
    )
    db.add(foreign)
    db.commit()
    foreign_member = SimpleNamespace(
        role="manager", organization_id=foreign.id, organization=foreign,
    )
    assert get_shopify_plan_transition_proposals(
        membership=foreign_member, db=db, limit=20,
    )["items"] == []


def test_production_activation_has_hard_stop_even_when_review_exists(sandbox):
    first = _prepare(sandbox)
    with patch.dict("os.environ", {
        "DIAGLOB_ENABLE_SHOPIFY_BILLING": "true",
        "SHOPIFY_APP_PRICING_ENABLED": "true",
    }):
        with pytest.raises(ShopifyTransitionReviewError, match="ACTIVATION_DISABLED"):
            activate_shopify_plan_transition(review_id=first["id"])
