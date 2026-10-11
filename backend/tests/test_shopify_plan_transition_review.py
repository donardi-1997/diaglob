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
    get_shopify_plan_transition_assessment,
    get_shopify_plan_transition_proposals,
    propose_shopify_plan_transition,
)
from app.services.shopify_transition_assessment import (
    assess_shopify_transition_review,
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


def _assess(sandbox):
    db, org, _, _, _, _ = sandbox
    proposal = _prepare(sandbox)
    return assess_shopify_transition_review(
        db, organization_id=org.id, review_id=proposal["id"],
    )


def test_fresh_review_is_preflight_only_never_an_access_grant(sandbox):
    db, org, _, connection, _, _ = sandbox
    result = _assess(sandbox)
    assert result["status"] == "ready_for_manual_review"
    assert result["ready_for_manual_review"] is True
    assert result["blockers"] == []
    assert result["requires_new_shopify_verification_before_activation"] is True
    assert result["shopify_reverified_now"] is False
    assert result["activation_allowed"] is False
    assert result["applied"] is False
    assert db.query(ShopifyPlanTransitionReview).one().status == "pending_review"
    db.expire_all()
    assert org.plan == "starter"
    assert connection.access_token_encrypted == "PRIVATE_SYNTHETIC_TOKEN"
    assert "PRIVATE_SYNTHETIC_TOKEN" not in str(result)
    assert "myshopify.com" not in str(result)


def test_preflight_rejects_expired_proposal_even_if_db_status_pending(sandbox):
    db, org, _, _, _, _ = sandbox
    proposal = _prepare(sandbox)
    item = db.get(ShopifyPlanTransitionReview, proposal["id"])
    item.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assessment = assess_shopify_transition_review(
        db, organization_id=org.id, review_id=item.id,
    )
    assert assessment["status"] == "blocked"
    assert "REVIEW_EXPIRED" in assessment["blockers"]
    assert assessment["activation_allowed"] is False
    db.expire_all()
    assert db.get(ShopifyPlanTransitionReview, item.id).status == "pending_review"


def test_preflight_rejects_disconnected_or_reinstalled_shop(sandbox):
    db, org, _, conn, _, _ = sandbox
    proposal = _prepare(sandbox)
    conn.connected_at = datetime.utcnow()
    db.commit()
    assessment = assess_shopify_transition_review(
        db, organization_id=org.id, review_id=proposal["id"],
    )
    assert "SHOPIFY_INSTALLATION_CHANGED" in assessment["blockers"]
    conn.status = "revoked"
    conn.access_token_encrypted = None
    db.commit()
    assessment = assess_shopify_transition_review(
        db, organization_id=org.id, review_id=proposal["id"],
    )
    assert "SHOPIFY_INSTALLATION_CHANGED" in assessment["blockers"]
    assert assessment["ready_for_manual_review"] is False


def test_preflight_rejects_newer_verified_subscription_even_if_proposal_unexpired(sandbox):
    db, org, store, conn, _, _ = sandbox
    proposal = _prepare(sandbox)
    db.add(ShopifyBillingVerification(
        organization_id=org.id, store_id=store.id,
        connection_id=conn.id,
        status="subscription_inactive_requires_review",
        current_plan="starter", target_plan=None,
        target_period_months=None,
        installation_connected_at=conn.connected_at,
        observed_at=datetime.utcnow() + timedelta(milliseconds=5),
    ))
    db.commit()
    result = assess_shopify_transition_review(
        db, organization_id=org.id, review_id=proposal["id"],
    )
    assert "NEWER_VERIFICATION_EXISTS" in result["blockers"]
    assert result["activation_allowed"] is False


def test_preflight_rejects_changed_plan_and_billing_provider(sandbox):
    db, org, _, _, _, _ = sandbox
    proposal = _prepare(sandbox)
    org.plan = "pro"
    org.billing_provider = "paddle"
    db.commit()
    result = assess_shopify_transition_review(
        db, organization_id=org.id, review_id=proposal["id"],
    )
    assert "BILLING_CHANNEL_CHANGED" in result["blockers"]
    assert "BASELINE_PLAN_CHANGED" in result["blockers"]


def test_preflight_rejects_paddle_references(sandbox):
    db, org, _, _, _, _ = sandbox
    proposal = _prepare(sandbox)
    org.billing_subscription_id = "legacy-synthetic"
    db.commit()
    result = assess_shopify_transition_review(
        db, organization_id=org.id, review_id=proposal["id"],
    )
    assert "LEGACY_BILLING_REFERENCES" in result["blockers"]
    assert "legacy-synthetic" not in str(result)


def test_preflight_rejects_paused_deleted_store(sandbox):
    db, org, store, _, _, _ = sandbox
    proposal = _prepare(sandbox)
    store.active = False
    store.deleted = True
    db.commit()
    result = assess_shopify_transition_review(
        db, organization_id=org.id, review_id=proposal["id"],
    )
    assert "STORE_UNAVAILABLE" in result["blockers"]


def test_preflight_rejects_second_shop_even_when_revoked(sandbox):
    db, org, _, _, _, _ = sandbox
    proposal = _prepare(sandbox)
    second = Store(
        organization_id=org.id, name="Second", slug="assessment-second",
        country_code="CO", currency="COP", timezone="UTC", active=False,
    )
    db.add(second)
    db.flush()
    db.add(CommerceConnection(
        organization_id=org.id, store_id=second.id, provider="shopify",
        external_store_url="assessment-second.myshopify.com", status="revoked",
    ))
    db.commit()
    result = assess_shopify_transition_review(
        db, organization_id=org.id, review_id=proposal["id"],
    )
    assert "SHOPIFY_BINDINGS_CHANGED" in result["blockers"]
    assert result["activation_allowed"] is False


def test_preflight_rejects_foreign_tenant_even_with_known_review_id(sandbox):
    db, _, _, _, _, _ = sandbox
    proposal = _prepare(sandbox)
    foreign = Organization(
        name="Foreign assessment", slug="foreign-assessment-tenant",
        billing_provider="shopify", plan="starter",
    )
    db.add(foreign)
    db.commit()
    with pytest.raises(ShopifyTransitionReviewError, match="NOT_FOUND"):
        assess_shopify_transition_review(
            db, organization_id=foreign.id, review_id=proposal["id"],
        )


def test_assessment_route_requires_billing_role_and_is_read_only(sandbox):
    db, org, _, _, _, member = sandbox
    proposal = _prepare(sandbox)
    member.role = "viewer"
    with pytest.raises(HTTPException) as error:
        get_shopify_plan_transition_assessment(
            review_id=proposal["id"], membership=member, db=db,
        )
    assert error.value.status_code == 403
    member.role = "manager"
    result = get_shopify_plan_transition_assessment(
        review_id=proposal["id"], membership=member, db=db,
    )
    assert result["ready_for_manual_review"] is True
    assert result["activation_allowed"] is False
    assert org.plan == "starter"
    assert db.query(ShopifyPlanTransitionReview).count() == 1


def test_missing_review_returns_consistent_non_disclosing_code(sandbox):
    db, org, _, _, _, _ = sandbox
    with pytest.raises(ShopifyTransitionReviewError, match="NOT_FOUND"):
        assess_shopify_transition_review(
            db, organization_id=org.id, review_id=99999,
        )


def test_invalid_assessment_ids_fail_closed(sandbox):
    db, org, _, _, _, _ = sandbox
    proposal = _prepare(sandbox)
    for invalid in (0, -1, True, "1", None):
        with pytest.raises(ShopifyTransitionReviewError, match="INVALID_ID"):
            assess_shopify_transition_review(
                db, organization_id=org.id, review_id=invalid,
            )
    assert db.query(ShopifyPlanTransitionReview).count() == 1
    assert proposal["applied"] is False


# Actual Shopify App Pricing is owned by Shopify. All tests use mock snapshots,
# not merchant calls, charge creation, or changes to a real account.

def _approved_monthly_growth(monkeypatch):
    import json
    from app.services.shopify_app_pricing import ShopifySubscriptionSnapshot
    monkeypatch.setenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_APP_PRICING_HANDLES_JSON", json.dumps({
        "growth-approved": {
            "plan": "growth", "interval": "EVERY_30_DAYS",
            "amount_usd": "49.00",
        },
    }))
    return ShopifySubscriptionSnapshot(
        active=True, billing_period="EVERY_30_DAYS",
        item_handles=("growth-approved",),
        eligible_handles=("growth-approved",),
        eligible_amounts=("49.00",),
    )


def test_hosted_shopify_app_pricing_requires_auth_and_operator_handle(
    sandbox, monkeypatch,
):
    from app.services.shopify_hosted_plan_selection import get_hosted_plan_selection
    from app.services.shopify_app_pricing import ShopifyAppPricingError
    db, org, _, conn, _, member = sandbox
    with patch(
        "app.services.shopify_hosted_plan_selection.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/777",
    ) as shop:
        with pytest.raises(ShopifyAppPricingError, match="NOT_CONFIGURED"):
            get_hosted_plan_selection(db, organization_id=org.id)
        monkeypatch.setenv("SHOPIFY_APP_STORE_HANDLE", "diaglob-app")
        result = get_hosted_plan_selection(db, organization_id=org.id)
    shop.assert_called_once_with(conn)
    assert result == {
        "provider": "shopify",
        "hosted_by_shopify": True,
        "url": "https://admin.shopify.com/store/synthetic-review/charges/diaglob-app/pricing_plans",
        "entitlements_applied": False,
    }
    assert "PRIVATE_SYNTHETIC_TOKEN" not in str(result)
    assert "gid://shopify" not in str(result)
    org.billing_provider = "paddle"
    db.commit()
    with pytest.raises(ShopifyAppPricingError, match="PROVENANCE_REQUIRED"):
        get_hosted_plan_selection(db, organization_id=org.id)


def test_hosted_plan_selection_rejects_untrusted_app_handle_and_multishop(
    sandbox, monkeypatch,
):
    from app.services.shopify_hosted_plan_selection import get_hosted_plan_selection
    from app.services.shopify_app_pricing import ShopifyAppPricingError
    db, org, _, _, _, _ = sandbox
    monkeypatch.setenv("SHOPIFY_APP_STORE_HANDLE", "evil/path?next=https://other.example")
    with patch("app.services.shopify_hosted_plan_selection.resolve_trusted_shop_gid") as verifier:
        with pytest.raises(ShopifyAppPricingError, match="NOT_CONFIGURED"):
            get_hosted_plan_selection(db, organization_id=org.id)
        verifier.assert_not_called()


def test_verified_shopify_transition_default_disabled_and_owner_only(
    sandbox, monkeypatch,
):
    from app.services.shopify_verified_entitlement_apply import (
        apply_verified_shopify_transition,
    )
    from app.api.billing import apply_shopify_plan_transition
    db, org, _, _, _, member = sandbox
    review = _prepare(sandbox)
    monkeypatch.delenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", raising=False)
    with pytest.raises(ShopifyTransitionReviewError, match="ACTIVATION_DISABLED"):
        apply_verified_shopify_transition(
            db, organization_id=org.id, review_id=review["id"],
        )
    member.role = "manager"
    with pytest.raises(HTTPException) as response:
        apply_shopify_plan_transition(
            review_id=review["id"], membership=member, db=db,
        )
    assert response.value.status_code == 403
    assert org.plan == "starter"


def test_shopify_transition_applies_fresh_approved_partner_plan_once(
    sandbox, monkeypatch,
):
    from app.services.shopify_verified_entitlement_apply import (
        apply_verified_shopify_transition,
    )
    db, org, _, conn, _, _ = sandbox
    review = _prepare(sandbox)
    verified = _approved_monthly_growth(monkeypatch)
    with patch(
        "app.services.shopify_verified_entitlement_apply.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/777",
    ) as identity, patch(
        "app.services.shopify_verified_entitlement_apply.get_active_shopify_subscription",
        return_value=verified,
    ) as partner:
        response = apply_verified_shopify_transition(
            db, organization_id=org.id, review_id=review["id"],
        )
        replay = apply_verified_shopify_transition(
            db, organization_id=org.id, review_id=review["id"],
        )
    assert response["applied"] is True
    assert response["plan"] == "growth"
    assert replay["applied"] is False and replay["already_applied"] is True
    partner.assert_called_once_with("gid://shopify/Shop/777")
    identity.assert_called_once()
    db.refresh(org)
    assert org.billing_provider == "shopify"
    assert org.plan == "growth"
    assert org.subscription_status == "active"
    assert org.billing_period_months == 1
    assert not org.billing_customer_id and not org.billing_subscription_id
    from app.models import ShopifyPlanTransitionReview
    assert db.get(ShopifyPlanTransitionReview, review["id"]).status == "applied"
    assert conn.access_token_encrypted == "PRIVATE_SYNTHETIC_TOKEN"


@pytest.mark.parametrize("condition", ["inactive", "cancelled", "wrong_price", "wrong_plan"])
def test_shopify_transition_never_applies_unapproved_provider_state(
    sandbox, monkeypatch, condition,
):
    from app.services.shopify_verified_entitlement_apply import (
        apply_verified_shopify_transition,
    )
    from app.services.shopify_app_pricing import ShopifySubscriptionSnapshot
    db, org, _, _, _, _ = sandbox
    review = _prepare(sandbox)
    verified = _approved_monthly_growth(monkeypatch)
    if condition == "inactive":
        verified = ShopifySubscriptionSnapshot(active=False)
    elif condition == "cancelled":
        verified = ShopifySubscriptionSnapshot(
            **{**vars(verified), "cancel_at_end_of_cycle": True}
        )
    elif condition == "wrong_price":
        verified = ShopifySubscriptionSnapshot(
            **{**vars(verified), "eligible_amounts": ("1.00",)}
        )
    else:
        verified = ShopifySubscriptionSnapshot(
            **{**vars(verified), "eligible_handles": ("unknown",), "item_handles": ("unknown",)}
        )
    with patch(
        "app.services.shopify_verified_entitlement_apply.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/777",
    ), patch(
        "app.services.shopify_verified_entitlement_apply.get_active_shopify_subscription",
        return_value=verified,
    ):
        with pytest.raises(ShopifyTransitionReviewError):
            apply_verified_shopify_transition(
                db, organization_id=org.id, review_id=review["id"],
            )
    db.refresh(org)
    assert org.plan == "starter"
    assert org.subscription_status != "active"


def test_shopify_transition_rechecks_installation_after_partner_response(
    sandbox, monkeypatch,
):
    from app.services.shopify_verified_entitlement_apply import (
        apply_verified_shopify_transition,
    )
    db, org, _, conn, _, _ = sandbox
    review = _prepare(sandbox)
    verified = _approved_monthly_growth(monkeypatch)

    def reinstalled(*args):
        conn.connected_at = datetime.utcnow()
        db.commit()
        return verified

    with patch(
        "app.services.shopify_verified_entitlement_apply.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/777",
    ), patch(
        "app.services.shopify_verified_entitlement_apply.get_active_shopify_subscription",
        side_effect=reinstalled,
    ):
        with pytest.raises(ShopifyTransitionReviewError, match="STATE_CHANGED"):
            apply_verified_shopify_transition(
                db, organization_id=org.id, review_id=review["id"],
            )
    db.refresh(org)
    assert org.plan == "starter"


def test_shopify_transition_cross_tenant_replay_is_denied(sandbox, monkeypatch):
    from app.services.shopify_verified_entitlement_apply import (
        apply_verified_shopify_transition,
    )
    db, org, _, _, _, _ = sandbox
    review = _prepare(sandbox)
    _approved_monthly_growth(monkeypatch)
    other = Organization(
        name="Other Account", slug="other-customer-isolation",
        billing_provider="shopify", plan="starter",
    )
    db.add(other)
    db.commit()
    with patch(
        "app.services.shopify_verified_entitlement_apply.get_active_shopify_subscription"
    ) as partner:
        with pytest.raises(ShopifyTransitionReviewError, match="NOT_FOUND"):
            apply_verified_shopify_transition(
                db, organization_id=other.id, review_id=review["id"],
            )
        partner.assert_not_called()


@pytest.mark.parametrize(
    "remote_status,expected_local",
    [
        ("plan_verified_no_change", "active"),
        ("plan_transition_requires_review", "review_required"),
        ("subscription_inactive_requires_review", "inactive"),
    ],
)
def test_shopify_billing_lifecycle_refresh_enforces_current_partner_state(
    sandbox, monkeypatch, remote_status, expected_local,
):
    from app.services.shopify_billing_lifecycle import refresh_shopify_billing_status
    from app.plan_limits import get_organization_limits, organization_has_plan
    db, org, _, _, _, _ = sandbox
    org.subscription_status = "active"
    db.commit()
    monkeypatch.setenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "true")

    preview = SimpleNamespace(
        organization_id=org.id, current_plan="starter",
        status=remote_status,
        target_plan=(
            None if remote_status == "subscription_inactive_requires_review"
            else "starter" if remote_status == "plan_verified_no_change"
            else "growth"
        ),
        target_billing_period_months=(
            None if remote_status == "subscription_inactive_requires_review" else 1
        ),
    )
    with patch(
        "app.services.shopify_billing_lifecycle.preview_shopify_entitlement_reconciliation",
        return_value=preview,
    ) as provider:
        result = refresh_shopify_billing_status(db, organization_id=org.id)
    provider.assert_called_once()
    db.refresh(org)
    assert result["subscription_status"] == expected_local
    assert org.subscription_status == expected_local
    assert org.plan == "starter"
    assert org.billing_provider == "shopify"
    assert db.query(ShopifyBillingVerification).count() == 2
    if expected_local != "active":
        assert get_organization_limits(org).active_stores == 0
        assert organization_has_plan(org) is False
    else:
        assert get_organization_limits(org).active_stores > 0
        assert organization_has_plan(org) is True


def test_shopify_lifecycle_no_partner_claim_or_paddle_changes(sandbox, monkeypatch):
    from app.services.shopify_billing_lifecycle import refresh_shopify_billing_status
    db, org, _, _, _, _ = sandbox
    monkeypatch.setenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "true")
    org.billing_provider = "paddle"
    db.commit()
    with patch(
        "app.services.shopify_billing_lifecycle.preview_shopify_entitlement_reconciliation"
    ) as provider:
        with pytest.raises(ShopifyTransitionReviewError, match="PROVENANCE_REQUIRED"):
            refresh_shopify_billing_status(db, organization_id=org.id)
        provider.assert_not_called()


def test_shopify_lifecycle_does_not_suspend_on_partner_outage(sandbox, monkeypatch):
    from app.services.shopify_billing_lifecycle import refresh_shopify_billing_status
    from app.services.shopify_app_pricing import ShopifyAppPricingError
    db, org, _, _, _, _ = sandbox
    org.subscription_status = "active"
    db.commit()
    monkeypatch.setenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "true")
    with patch(
        "app.services.shopify_billing_lifecycle.preview_shopify_entitlement_reconciliation",
        side_effect=ShopifyAppPricingError("SHOPIFY_PARTNER_API_UNAVAILABLE"),
    ):
        with pytest.raises(ShopifyTransitionReviewError, match="PARTNER_API_UNAVAILABLE"):
            refresh_shopify_billing_status(db, organization_id=org.id)
    db.refresh(org)
    assert org.subscription_status == "active"
    assert db.query(ShopifyBillingVerification).count() == 1


def test_shopify_lifecycle_reinstall_during_partner_check_fails_closed(
    sandbox, monkeypatch,
):
    from app.services.shopify_billing_lifecycle import refresh_shopify_billing_status
    db, org, _, conn, _, _ = sandbox
    monkeypatch.setenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "true")

    def reconnect(*args, **kwargs):
        conn.connected_at = datetime.utcnow()
        db.commit()
        return SimpleNamespace(
            organization_id=org.id, current_plan="starter",
            status="subscription_inactive_requires_review",
            target_plan=None, target_billing_period_months=None,
        )

    with patch(
        "app.services.shopify_billing_lifecycle.preview_shopify_entitlement_reconciliation",
        side_effect=reconnect,
    ):
        with pytest.raises(ShopifyTransitionReviewError, match="STATE_CHANGED"):
            refresh_shopify_billing_status(db, organization_id=org.id)
    assert db.query(ShopifyBillingVerification).count() == 1



@pytest.mark.parametrize("provider,expected", [
    ("shopify", "inactive"), ("paddle", "active"),
])
def test_shopify_disconnect_only_suspends_shopify_billed_access(
    sandbox, provider, expected,
):
    from app.services.shopify_service import disconnect
    db, org, store, _, _, _ = sandbox
    org.billing_provider = provider
    org.subscription_status = "active"
    db.commit()
    result = disconnect(db, org.id, store.id)
    db.refresh(org)
    assert result["connected"] is False
    assert org.subscription_status == expected


@pytest.mark.parametrize("provider,expected", [
    ("shopify", "inactive"), ("paddle", "active"),
])
def test_verified_shopify_uninstall_suspends_only_shopify_billing(
    sandbox, provider, expected,
):
    from datetime import timezone
    from app.services.shopify_uninstall import process_shopify_uninstall
    db, org, _, _, _, _ = sandbox
    org.billing_provider = provider
    org.subscription_status = "active"
    db.commit()
    result = process_shopify_uninstall(
        db,
        topic="app/uninstalled",
        header_shop_domain="synthetic-review.myshopify.com",
        triggered_at=datetime.now(timezone.utc).isoformat(),
        payload={"id": 717, "myshopify_domain": "synthetic-review.myshopify.com"},
    )
    db.refresh(org)
    assert result["action"] == "revoked"
    assert org.subscription_status == expected



def test_shopify_same_plan_annual_change_requires_partner_period_confirmation(
    sandbox, monkeypatch,
):
    import json
    from app.services.shopify_verified_entitlement_apply import (
        apply_verified_shopify_transition,
    )
    from app.services.shopify_app_pricing import ShopifySubscriptionSnapshot
    db, org, _, _, receipt, _ = sandbox
    receipt.target_plan = "starter"
    receipt.target_period_months = 12
    db.commit()
    review = _prepare(sandbox)
    monkeypatch.setenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_APP_PRICING_HANDLES_JSON", json.dumps({
        "starter-annual": {
            "plan": "starter", "interval": "ANNUAL", "amount_usd": "190.00",
        },
    }))
    snapshot = ShopifySubscriptionSnapshot(
        active=True, billing_period="ANNUAL",
        item_handles=("starter-annual",),
        eligible_handles=("starter-annual",),
        eligible_amounts=("190.00",),
    )
    with patch(
        "app.services.shopify_verified_entitlement_apply.resolve_trusted_shop_gid",
        return_value="gid://shopify/Shop/777",
    ), patch(
        "app.services.shopify_verified_entitlement_apply.get_active_shopify_subscription",
        return_value=snapshot,
    ):
        applied = apply_verified_shopify_transition(
            db, organization_id=org.id, review_id=review["id"],
        )
    assert applied["applied"] is True
    db.refresh(org)
    assert org.plan == "starter"
    assert org.billing_period_months == 12
    assert org.subscription_status == "active"
