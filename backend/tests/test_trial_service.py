from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.model_domains.trials import TrialEntitlement, TrialIdentity
from app.models import Organization
from app.plan_limits import get_organization_limits
from app.services import ai_usage_service
from app.services.trial_service import (
    TRIAL_AI_RESPONSES,
    TRIAL_DAYS,
    TrialIdentityAlreadyUsed,
    activate_trial_for_verified_store,
    create_pending_trial,
    hash_trial_identity,
    refresh_trial_state,
    serialize_trial_status,
)


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_org(db, suffix: str, *, plan: str = "none", status: str | None = None):
    organization = Organization(
        name=f"Trial Org {suffix}",
        slug=f"trial-org-{suffix}",
        plan=plan,
        subscription_status=status,
        active=True,
    )
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def make_pending_trial(db, suffix: str, now: datetime):
    organization = make_org(db, suffix)
    entitlement = create_pending_trial(db, organization, now=now)
    db.commit()
    db.refresh(organization)
    db.refresh(entitlement)
    return organization, entitlement


def test_pending_trial_does_not_start_clock_until_verified_store(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    organization, entitlement = make_pending_trial(db, "pending", now)

    assert organization.plan == "trial"
    assert organization.subscription_status == "trial_pending"
    assert entitlement.status == "pending"
    assert entitlement.started_at is None
    assert entitlement.ends_at is None


def test_verified_shopify_store_activates_exactly_seven_day_trial(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    organization, entitlement = make_pending_trial(db, "activate", now)

    result = activate_trial_for_verified_store(
        db,
        organization_id=organization.id,
        store_id=101,
        provider="shopify",
        external_identity="HTTPS://Example-Shop.MyShopify.com/",
        now=now,
    )
    db.commit()
    db.refresh(organization)
    db.refresh(entitlement)

    assert result["trial_activated"] is True
    assert entitlement.status == "active"
    assert entitlement.started_at == now
    assert entitlement.ends_at == now + timedelta(days=TRIAL_DAYS)
    assert organization.plan == "trial"
    assert organization.subscription_status == "trialing"

    identity = db.query(TrialIdentity).one()
    assert identity.provider == "shopify"
    assert identity.identity_hash == hash_trial_identity(
        "shopify", "example-shop.myshopify.com"
    )
    assert "example-shop" not in identity.identity_hash


def test_same_verified_store_is_idempotent_inside_same_organization(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    organization, _ = make_pending_trial(db, "same-org", now)

    first = activate_trial_for_verified_store(
        db,
        organization_id=organization.id,
        store_id=10,
        provider="shopify",
        external_identity="same.myshopify.com",
        now=now,
    )
    second = activate_trial_for_verified_store(
        db,
        organization_id=organization.id,
        store_id=10,
        provider="shopify",
        external_identity="https://SAME.myshopify.com/",
        now=now + timedelta(hours=1),
    )
    db.commit()

    assert first["trial_activated"] is True
    assert second["trial_activated"] is False
    assert second["reason"] == "already_active"
    assert db.query(TrialIdentity).count() == 1


def test_same_store_cannot_mint_second_trial_in_another_organization(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    first_org, _ = make_pending_trial(db, "owner-a", now)
    second_org, second_entitlement = make_pending_trial(db, "owner-b", now)

    activate_trial_for_verified_store(
        db,
        organization_id=first_org.id,
        store_id=1,
        provider="shopify",
        external_identity="claimed.myshopify.com",
        now=now,
    )
    db.commit()

    with pytest.raises(TrialIdentityAlreadyUsed) as exc:
        activate_trial_for_verified_store(
            db,
            organization_id=second_org.id,
            store_id=2,
            provider="shopify",
            external_identity="claimed.myshopify.com",
            now=now + timedelta(minutes=5),
        )

    # Provider callbacks intentionally commit this anti-abuse decision before
    # returning the conflict to the browser.
    db.commit()
    db.refresh(second_org)
    db.refresh(second_entitlement)

    assert str(exc.value) == "TRIAL_STORE_ALREADY_USED"
    assert second_entitlement.status == "blocked"
    assert second_org.plan == "none"
    assert second_org.subscription_status == "trial_blocked"
    assert db.query(TrialIdentity).count() == 1


def test_paid_organization_can_reuse_prior_trial_identity_without_new_trial(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    trial_org, _ = make_pending_trial(db, "original", now)
    activate_trial_for_verified_store(
        db,
        organization_id=trial_org.id,
        store_id=1,
        provider="nuvemshop",
        external_identity="987654",
        now=now,
    )
    db.commit()

    paid_org = make_org(db, "paid", plan="starter", status="active")
    result = activate_trial_for_verified_store(
        db,
        organization_id=paid_org.id,
        store_id=99,
        provider="nuvemshop",
        external_identity="987654",
        now=now + timedelta(days=1),
    )
    db.commit()

    assert result == {
        "allowed": True,
        "trial_activated": False,
        "reason": "paid_organization",
    }
    assert db.query(TrialIdentity).count() == 1
    assert paid_org.plan == "starter"
    assert paid_org.subscription_status == "active"


def test_trial_expires_and_write_entitlement_is_removed(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    organization, entitlement = make_pending_trial(db, "expiry", now)
    activate_trial_for_verified_store(
        db,
        organization_id=organization.id,
        store_id=1,
        provider="shopify",
        external_identity="expires.myshopify.com",
        now=now,
    )
    db.commit()

    refresh_trial_state(
        db,
        organization,
        now=now + timedelta(days=TRIAL_DAYS, seconds=1),
    )
    db.refresh(organization)
    db.refresh(entitlement)

    assert entitlement.status == "expired"
    assert organization.plan == "none"
    assert organization.subscription_status == "trial_expired"


def test_trial_status_reports_remaining_days(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    organization, _ = make_pending_trial(db, "status", now)
    activate_trial_for_verified_store(
        db,
        organization_id=organization.id,
        store_id=1,
        provider="shopify",
        external_identity="status.myshopify.com",
        now=now,
    )
    db.commit()

    status = serialize_trial_status(
        db,
        organization,
        now=now + timedelta(days=2, hours=1),
    )

    assert status["status"] == "active"
    assert status["days_remaining"] == 5
    assert status["ai_response_limit"] == TRIAL_AI_RESPONSES


def test_trial_plan_is_limited_to_one_store_and_1000_ai_responses(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    organization, _ = make_pending_trial(db, "limits", now)

    limits = get_organization_limits(organization)

    assert limits.active_stores == 1
    assert limits.included_ai_responses == TRIAL_AI_RESPONSES


def test_ai_is_unavailable_before_trial_activation(db):
    now = datetime(2026, 9, 10, 12, 0, 0)
    organization, _ = make_pending_trial(db, "ai-pending", now)

    reservation = ai_usage_service.acquire_ai_capacity(
        db,
        organization.id,
        now=now,
    )

    assert reservation["available"] is False
    assert reservation["reason"] == "trial_pending"


def test_trial_ai_limit_is_hard_cap_even_if_extra_credit_exists(db, monkeypatch):
    now = datetime(2026, 9, 10, 12, 0, 0)
    organization, _ = make_pending_trial(db, "ai-cap", now)
    activate_trial_for_verified_store(
        db,
        organization_id=organization.id,
        store_id=1,
        provider="shopify",
        external_identity="ai-cap.myshopify.com",
        now=now,
    )
    db.commit()

    monkeypatch.setattr(
        ai_usage_service,
        "_count_ai_responses",
        lambda *_args, **_kwargs: TRIAL_AI_RESPONSES,
    )
    monkeypatch.setattr(
        ai_usage_service,
        "_extra_credit_totals",
        lambda *_args, **_kwargs: (5000, 5000),
    )

    usage = ai_usage_service.get_ai_usage(db, organization.id)
    reservation = ai_usage_service.acquire_ai_capacity(
        db,
        organization.id,
        now=now + timedelta(days=1),
    )

    assert usage["remaining_ai_responses"] == 0
    assert usage["extra_ai_responses_remaining"] == 0
    assert reservation["available"] is False
    assert reservation["reason"] == "trial_ai_limit_reached"
