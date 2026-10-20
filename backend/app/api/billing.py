"""Billing HTTP router with a backwards-compatible Paddle webhook endpoint."""

import json
import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..billing_providers import (
    BillingProviderConfigurationError,
    BillingProviderError,
    get_billing_provider,
)
from ..billing import get_subscription_price_id
from ..db import get_db
from ..models import CommerceConnection, Organization, OrganizationMembership, Store
from .deps import get_current_membership
from ..services.ai_usage_packages import fulfill_ai_usage_package_transaction
from ..services.shopify_app_pricing import (
    SHOPIFY_APP_STORE_PLANS,
    SHOPIFY_APP_STORE_TRIAL_DAYS,
    SHOPIFY_APP_PRICING_INTERVAL_TO_MONTHS,
    ShopifyAppPricingError,
)
from ..services.shopify_app_pricing_reconciliation import (
    preview_shopify_entitlement_reconciliation,
    verify_shopify_trial_contract,
)
from ..services.shopify_billing_verification import (
    ShopifyBillingEvidenceError,
    list_shopify_billing_verifications,
    record_shopify_billing_verification,
)
from ..services.shopify_plan_transition_review import (
    ShopifyTransitionReviewError,
    list_shopify_plan_transition_reviews,
    prepare_shopify_plan_transition,
)
from ..services.shopify_transition_assessment import (
    assess_shopify_transition_review,
)
from ..services.shopify_hosted_plan_selection import (
    get_hosted_plan_selection,
)
from ..services.shopify_verified_entitlement_apply import (
    apply_verified_shopify_transition,
)
from ..services.shopify_billing_lifecycle import (
    refresh_shopify_billing_status,
)
from ..services.shopify_development_billing_probe import (
    probe_shopify_development_subscription,
)
from ..services.billing_service import (
    AutoRenewConflictError,
    DowngradeBlockedError,
    DowngradeNoopError,
    DowngradePeriodChangeError,
    InvalidBillingPlanError,
    NoActiveSubscriptionError,
    StoreSelectionError,
    UpgradeNotAllowedError,
    apply_downgrade,
    cancel_downgrade,
    create_checkout,
    execute_upgrade,
    get_billing_price_id,
    get_downgrade_preview_data,
    preview_upgrade_local,
    preview_upgrade_provider,
    process_pending_downgrades,
    toggle_auto_renew_disable,
    toggle_auto_renew_enable,
    validate_plan_downgrade,
    validate_plan_upgrade,
)
from ..services.paddle_webhooks import (
    SUPPORTED_EVENTS,
    SUBSCRIPTION_EVENTS,
    TRANSACTION_EVENTS,
    is_canonical_subscription,
    is_duplicate_event,
    is_out_of_order_event,
    process_subscription_event,
    process_transaction_event,
    resolve_organization,
    update_billing_fields,
)
from ..services.paddle_checkout import (
    create_signed_checkout_custom_data,
    paddle_country_code,
    verify_signed_checkout_custom_data,
)
from ..services.trial_service import TRIAL_DAYS
from ..services.paddle_fulfillment import (
    verify_notification,
    dispatch_verified_notification,
    create_portal_session_url,
    get_paddle_billing_capabilities,
)
from ..model_domains.paddle_billing import PaddleWebhookEvent
from sqlalchemy.exc import IntegrityError

router = APIRouter()
logger = logging.getLogger(__name__)


def _reject_shopify_managed_billing(organization: Organization) -> None:
    """Never route Shopify App Store subscriptions through Paddle operations.

    The billing-provider flag must be set server-side using verified install
    provenance. Legacy unassigned organizations keep the Paddle channel.
    """
    if (organization.billing_provider or "").strip().lower() == "shopify":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SHOPIFY_MANAGED_BILLING",
                "message": "Manage this subscription through Shopify App Pricing.",
            },
        )

    # Shopify install provenance must block external checkout even if an
    # inconsistent/migrated record says billing_provider="paddle". The origin
    # is an independent guard; otherwise stale provider data would bypass
    # App Store billing enforcement. Direct signup + Shopify store connector
    # still legitimately uses Paddle (origin="direct").
    if getattr(organization, "billing_onboarding_channel", None) == "shopify_install":
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_INSTALL_BILLING_PENDING"},
        )




_SHOPIFY_BILLING_TEMPORARY_ERRORS = frozenset({
    "SHOPIFY_PARTNER_API_NOT_CONFIGURED",
    "SHOPIFY_PARTNER_API_UNAVAILABLE",
    "SHOPIFY_PARTNER_API_GRAPHQL_ERROR",
    "SHOPIFY_PARTNER_API_INVALID_RESPONSE",
    "SHOPIFY_IDENTITY_UNAVAILABLE",
    "SHOPIFY_IDENTITY_INVALID",
    "SHOPIFY_IDENTITY_MISMATCH",
    "SHOPIFY_PLAN_CATALOG_NOT_CONFIGURED",
    "SHOPIFY_PLAN_CATALOG_INVALID",
})


@router.post("/api/billing/shopify/subscription-refresh")
def refresh_shopify_billing_subscription(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Refresh paid Shopify access from Partner API; no subscription mutations."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    try:
        return refresh_shopify_billing_status(
            db, organization_id=membership.organization_id,
        )
    except ShopifyTransitionReviewError as exc:
        db.rollback()
        code = str(exc)
        if not code.startswith("SHOPIFY_") or not code.replace("_", "").isalnum():
            code = "SHOPIFY_BILLING_UNAVAILABLE"
        raise HTTPException(
            status_code=503 if code in _SHOPIFY_BILLING_TEMPORARY_ERRORS
            or code == "SHOPIFY_BILLING_UNAVAILABLE" else 409,
            detail={"code": code},
        ) from exc


def _require_synchronized_paddle_subscription(db: Session, organization: Organization) -> None:
    """Reject plan mutations on legacy IDs or non-active local subscriptions."""
    if not get_paddle_billing_capabilities(db, organization)["plan_changes_available"]:
        raise HTTPException(
            status_code=409,
            detail="No existe una suscripción Paddle activa y sincronizada para esta organización.",
        )


@router.get("/api/billing/shopify/capabilities")
def shopify_billing_capabilities(
    membership: OrganizationMembership = Depends(get_current_membership),
):
    """Expose operational flags only; no provider secrets or customer data."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    return {
        "organization_id": membership.organization_id,
        "shopify_hosted_pricing_configured": bool(
            (os.getenv("SHOPIFY_APP_STORE_HANDLE") or "").strip()
        ),
        "verified_entitlement_apply_enabled": (
            os.getenv("SHOPIFY_BILLING_ENTITLEMENTS_ENABLED", "").lower() == "true"
        ),
        "paddle_checkout_available": False,
        "public_plans": list(SHOPIFY_APP_STORE_PLANS),
        "trial_days": SHOPIFY_APP_STORE_TRIAL_DAYS,
        "billing_period_months": list(SHOPIFY_APP_PRICING_INTERVAL_TO_MONTHS.values()),
    }


@router.get("/api/billing/shopify/hosted-plan-selection")
def shopify_hosted_plan_selection(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Return a trusted Shopify-owned pricing URL, without redirecting or billing."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    try:
        return get_hosted_plan_selection(
            db, organization_id=membership.organization_id,
        )
    except ShopifyAppPricingError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=503 if code in _SHOPIFY_BILLING_TEMPORARY_ERRORS
            or code == "SHOPIFY_HOSTED_PRICING_NOT_CONFIGURED" else 409,
            detail={"code": code},
        ) from exc


@router.post("/api/billing/shopify/transition-proposals/{review_id}/apply")
def apply_shopify_plan_transition(
    review_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Explicit owner action; always rechecks Partner before entitlements change."""
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    try:
        return apply_verified_shopify_transition(
            db, organization_id=membership.organization_id, review_id=review_id,
        )
    except ShopifyTransitionReviewError as exc:
        db.rollback()
        code = str(exc)
        safe_code = (
            code if code.startswith("SHOPIFY_") and
            code.replace("_", "").isalnum()
            else "SHOPIFY_TRANSITION_UNAVAILABLE"
        )
        raise HTTPException(
            status_code=503 if safe_code in _SHOPIFY_BILLING_TEMPORARY_ERRORS else 409,
            detail={"code": safe_code},
        ) from exc


@router.get("/api/billing/shopify/development-probe")
def shopify_development_subscription_probe(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Read-only test-store contract observation; no commercial plan grants.

    This route is disabled by default. It is not proof of development-store
    eligibility: the Partner owner must separately verify the storefront type
    and that it belongs to the proper Shopify Partner organization.
    """
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    if os.getenv("SHOPIFY_BILLING_TEST_PROBE_ENABLED", "") != "true":
        raise HTTPException(status_code=404, detail={"code": "SHOPIFY_TEST_PROBE_DISABLED"})
    organization = membership.organization
    if (
        not organization.active
        or (organization.billing_provider or "").strip().lower() != "shopify"
    ):
        raise HTTPException(
            status_code=409, detail={"code": "SHOPIFY_BILLING_PROVENANCE_REQUIRED"},
        )
    bindings = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == membership.organization_id,
            CommerceConnection.provider == "shopify",
        )
        .limit(2)
        .all()
    )
    if len(bindings) != 1:
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED"},
        )
    connection = bindings[0]
    store = (
        db.query(Store)
        .filter(
            Store.id == connection.store_id,
            Store.organization_id == membership.organization_id,
            Store.active.is_(True),
            Store.deleted.is_(False),
        ).first()
    )
    if connection.status != "connected" or store is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED"},
        )
    try:
        return probe_shopify_development_subscription(
            organization,
            connection,
            connected_shopify_store_count=1,
        )
    except ShopifyAppPricingError as exc:
        # No Partner API exceptions, GIDs, handles or credentials cross HTTP.
        code = str(exc)
        safe_errors = {
            "SHOPIFY_TEST_PROBE_DISABLED",
            "SHOPIFY_TEST_SHOP_NOT_CONFIGURED",
            "SHOPIFY_TEST_SHOP_NOT_ALLOWLISTED",
            "SHOPIFY_TEST_PROBE_TENANT_REVIEW_REQUIRED",
            "SHOPIFY_PARTNER_API_NOT_CONFIGURED",
            "SHOPIFY_PARTNER_API_UNAVAILABLE",
            "SHOPIFY_PARTNER_API_GRAPHQL_ERROR",
            "SHOPIFY_PARTNER_API_INVALID_RESPONSE",
            "SHOPIFY_IDENTITY_UNAVAILABLE",
            "SHOPIFY_IDENTITY_INVALID",
            "SHOPIFY_IDENTITY_MISMATCH",
            "SHOPIFY_SUBSCRIPTION_SHOP_MISMATCH",
        }
        if code not in safe_errors:
            code = "SHOPIFY_TEST_PROBE_UNAVAILABLE"
        transient = {
            "SHOPIFY_PARTNER_API_NOT_CONFIGURED",
            "SHOPIFY_PARTNER_API_UNAVAILABLE",
            "SHOPIFY_PARTNER_API_GRAPHQL_ERROR",
            "SHOPIFY_PARTNER_API_INVALID_RESPONSE",
            "SHOPIFY_IDENTITY_UNAVAILABLE",
            "SHOPIFY_TEST_SHOP_NOT_CONFIGURED",
            "SHOPIFY_TEST_PROBE_UNAVAILABLE",
        }
        raise HTTPException(
            status_code=503 if code in transient else 409,
            detail={"code": code},
        ) from exc


@router.get("/api/billing/shopify/reconciliation-preview")
def preview_shopify_billing_reconciliation(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Read-only, tenant-bound preview of a verified Shopify subscription.

    Never infer billing authority from a client-supplied shop/domain, redirect,
    or plan handle. This endpoint does not create charges, update plans, or
    mutate existing Paddle subscriptions.
    """
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = membership.organization
    if (organization.billing_provider or "").strip().lower() != "shopify":
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_BILLING_PROVENANCE_REQUIRED"},
        )

    # Count ALL Shopify bindings in the tenant, including paused/deleted
    # stores and revoked/error connections. Filtering inactive stores first
    # can disguise a multi-shop organization as a single-shop subscription,
    # silently applying one merchant's plan to the whole organization.
    bindings = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == membership.organization_id,
            CommerceConnection.provider == "shopify",
        )
        .limit(2)
        .all()
    )
    if len(bindings) != 1:
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_MULTISTORE_BILLING_REVIEW_REQUIRED"},
        )

    connection = bindings[0]
    eligible_store = (
        db.query(Store)
        .filter(
            Store.id == connection.store_id,
            Store.organization_id == membership.organization_id,
            Store.active.is_(True),
            Store.deleted.is_(False),
        )
        .first()
    )
    if eligible_store is None or connection.status != "connected":
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED"},
        )

    try:
        preview = preview_shopify_entitlement_reconciliation(
            organization,
            connection,
            connected_shopify_store_count=len(bindings),
        )
    except ShopifyAppPricingError as exc:
        code = str(exc)
        if not code.startswith("SHOPIFY_") or not code.replace("_", "").isalnum():
            code = "SHOPIFY_RECONCILIATION_UNAVAILABLE"
        raise HTTPException(
            status_code=(
                503 if code in _SHOPIFY_BILLING_TEMPORARY_ERRORS
                or code == "SHOPIFY_RECONCILIATION_UNAVAILABLE"
                else 409
            ),
            detail={"code": code},
        ) from exc

    # Do not expose access tokens, app credentials, raw subscription payloads,
    # plan handles, or unreviewed Shop GIDs in an HTTP response.
    return {
        "status": preview.status,
        "requires_review": preview.requires_review,
        "current_plan": preview.current_plan,
        "target_plan": preview.target_plan,
        "target_billing_period_months": preview.target_billing_period_months,
        "has_pending_update": bool(getattr(preview, "has_pending_update", False)),
        "organization_id": preview.organization_id,
        "applied": False,
    }

@router.get("/api/billing/shopify/trial-verification")
def verify_shopify_billing_trial(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Verify the active plan's configured trial days against Partner events."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    organization = membership.organization
    if (organization.billing_provider or "").strip().lower() != "shopify":
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_BILLING_PROVENANCE_REQUIRED"},
        )

    bindings = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == membership.organization_id,
            CommerceConnection.provider == "shopify",
        )
        .limit(2)
        .all()
    )
    if len(bindings) != 1 or bindings[0].status != "connected":
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED"},
        )
    connection = bindings[0]
    store = (
        db.query(Store)
        .filter(
            Store.id == connection.store_id,
            Store.organization_id == membership.organization_id,
            Store.active.is_(True),
            Store.deleted.is_(False),
        )
        .first()
    )
    if store is None:
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED"},
        )

    try:
        return verify_shopify_trial_contract(
            organization,
            connection,
            connected_shopify_store_count=len(bindings),
        )
    except ShopifyAppPricingError as exc:
        code = str(exc)
        if not code.startswith("SHOPIFY_") or not code.replace("_", "").isalnum():
            code = "SHOPIFY_TRIAL_VERIFICATION_UNAVAILABLE"
        raise HTTPException(
            status_code=(
                503 if code in _SHOPIFY_BILLING_TEMPORARY_ERRORS
                or code in {
                    "SHOPIFY_TRIAL_EVIDENCE_NOT_FOUND",
                    "SHOPIFY_TRIAL_VERIFICATION_UNAVAILABLE",
                }
                else 409
            ),
            detail={"code": code},
        ) from exc


@router.post("/api/billing/shopify/reconciliation-check")
def check_shopify_billing_reconciliation(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Query Shopify live and persist only non-authorizing verification evidence.

    No untrusted shop or plan parameters. The issuer must already manage this
    organization and its billing channel. Recording a check cannot grant a plan.
    """
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    if (membership.organization.billing_provider or "").strip().lower() != "shopify":
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_BILLING_PROVENANCE_REQUIRED"},
        )

    installed = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == membership.organization_id,
            CommerceConnection.provider == "shopify",
        )
        .limit(2)
        .all()
    )
    if len(installed) != 1 or installed[0].status != "connected":
        raise HTTPException(
            status_code=409,
            detail={"code": "SHOPIFY_BILLING_CONNECTION_REVIEW_REQUIRED"},
        )
    connection = installed[0]
    connection_id = connection.id
    store_id = connection.store_id
    installed_at = connection.connected_at

    # Reuses the existing live Admin+Partner verification and plan price guard.
    # No writes or locks are held while waiting for the remote provider.
    preview = preview_shopify_billing_reconciliation(membership=membership, db=db)

    try:
        verification = record_shopify_billing_verification(
            db,
            organization_id=membership.organization_id,
            connection_id=connection_id,
            store_id=store_id,
            installation_connected_at=installed_at,
            preview=preview,
        )
    except ShopifyBillingEvidenceError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail={"code": str(exc)}
        ) from exc
    return {
        **preview,
        "verification_id": verification.id,
        "verified_at": verification.observed_at.isoformat(),
        "requires_review": True,
        "applied": False,
    }


@router.get("/api/billing/shopify/reconciliation-history")
def get_shopify_billing_reconciliation_history(
    limit: int = Query(20, ge=1, le=50),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Tenant-scoped audit metadata only; never a billing authorization."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    return {
        "organization_id": membership.organization_id,
        "items": list_shopify_billing_verifications(
            db, organization_id=membership.organization_id, limit=limit,
        ),
        "applied": False,
    }


class ShopifyTransitionReviewRequest(BaseModel):
    verification_id: int


@router.post("/api/billing/shopify/transition-proposals")
def propose_shopify_plan_transition(
    payload: ShopifyTransitionReviewRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Stage a non-granting review after a recent provider-backed verification."""
    if membership.role != "owner":
        raise HTTPException(status_code=403, detail="Owner access required")
    try:
        return prepare_shopify_plan_transition(
            db,
            organization_id=membership.organization_id,
            verification_id=payload.verification_id,
        )
    except ShopifyTransitionReviewError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail={"code": str(exc)}
        ) from exc


@router.get("/api/billing/shopify/transition-proposals")
def get_shopify_plan_transition_proposals(
    limit: int = Query(20, ge=1, le=50),
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Inspect non-entitling proposals, never approve or apply them."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    return {
        "organization_id": membership.organization_id,
        "items": list_shopify_plan_transition_reviews(
            db, organization_id=membership.organization_id, limit=limit,
        ),
        "applied": False,
    }


@router.get("/api/billing/shopify/transition-proposals/{review_id}/assessment")
def get_shopify_plan_transition_assessment(
    review_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Non-authorizing freshness assessment for the current tenant only."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    try:
        return assess_shopify_transition_review(
            db,
            organization_id=membership.organization_id,
            review_id=review_id,
        )
    except ShopifyTransitionReviewError as exc:
        raise HTTPException(
            status_code=409, detail={"code": str(exc)}
        ) from exc


class BillingAutoRenewRequest(BaseModel):
    enabled: bool


class BillingCheckoutRequest(BaseModel):
    plan: str
    billing_period_months: int = 1


class PaddleCheckoutIntentRequest(BaseModel):
    plan: str
    billing_period_months: int = 1


class BillingUpgradeRequest(BaseModel):
    plan: str


class BillingDowngradeRequest(BaseModel):
    plan: str
    billing_period_months: int | None = None
    store_ids: list[int] | None = None


@router.post("/api/billing/webhook")
async def paddle_billing_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Backward-compatible destination, now on the SDK-verified event ledger."""
    raw_body = await request.body()
    secret = (os.getenv("PADDLE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Paddle webhook is not configured")
    try:
        event = verify_notification(raw_body, request.headers.get("Paddle-Signature", ""), secret)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid Paddle signature") from exc
    try:
        return dispatch_verified_notification(event, db)
    except IntegrityError as exc:
        db.rollback()
        event_id = str(event.get("event_id") or "")
        if event_id and db.get(PaddleWebhookEvent, event_id):
            return {"ok": True, "duplicate": True, "event_type": event.get("event_type")}
        raise HTTPException(status_code=503, detail="Paddle event processing failed") from exc
    except Exception:
        db.rollback()
        logger.exception("Paddle legacy event processing failed")
        raise


@router.patch("/api/billing/auto-renew")
def update_billing_auto_renew(
    payload: BillingAutoRenewRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    _reject_shopify_managed_billing(membership.organization)

    organization = membership.organization
    _require_synchronized_paddle_subscription(db, organization)
    if not organization.billing_subscription_id:
        raise HTTPException(
            status_code=409,
            detail="La organización no tiene una suscripción de facturación asociada.",
        )

    status = (organization.subscription_status or "").strip().lower()
    if status not in {"active", "trialing"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "La renovación automática solo puede modificarse mientras "
                "la suscripción está activa."
            ),
        )

    try:
        if payload.enabled:
            return toggle_auto_renew_enable(organization, db)
        return toggle_auto_renew_disable(organization, db)
    except AutoRenewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BillingProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BillingProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.post("/api/billing/upgrade/preview")
def preview_billing_upgrade(
    payload: BillingUpgradeRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    _reject_shopify_managed_billing(membership.organization)

    organization = db.query(Organization).filter(
        Organization.id == membership.organization_id
    ).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    _require_synchronized_paddle_subscription(db, organization)

    try:
        current_plan, target_plan = validate_plan_upgrade(organization, payload.plan)
    except InvalidBillingPlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoActiveSubscriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UpgradeNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    logger.info(
        "billing.preview org=%s current=%s target=%s provider=%s",
        organization.id,
        current_plan,
        target_plan,
        organization.billing_provider or "paddle",
    )

    provider_result = preview_upgrade_provider(organization, target_plan)
    if provider_result is not None:
        provider_result["current_plan"] = current_plan
        provider_result["target_plan"] = target_plan
        return provider_result

    return preview_upgrade_local(organization, current_plan, target_plan)


@router.post("/api/billing/upgrade")
def apply_billing_upgrade(
    payload: BillingUpgradeRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    _reject_shopify_managed_billing(membership.organization)

    organization = db.query(Organization).filter(
        Organization.id == membership.organization_id
    ).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    _require_synchronized_paddle_subscription(db, organization)

    try:
        _current_plan, target_plan = validate_plan_upgrade(organization, payload.plan)
        return execute_upgrade(organization, target_plan, db)
    except InvalidBillingPlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoActiveSubscriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UpgradeNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BillingProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BillingProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/billing/downgrade/preview")
def preview_billing_downgrade(
    payload: BillingDowngradeRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    _reject_shopify_managed_billing(membership.organization)

    organization = membership.organization
    _require_synchronized_paddle_subscription(db, organization)
    try:
        current_plan, target_plan, current_period, target_period = (
            validate_plan_downgrade(
                organization,
                payload.plan,
                db,
                payload.billing_period_months,
            )
        )
    except InvalidBillingPlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoActiveSubscriptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DowngradePeriodChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DowngradeNoopError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpgradeNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DowngradeBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        return get_downgrade_preview_data(
            organization,
            current_plan,
            target_plan,
            target_period,
            current_period,
            db,
        )
    except BillingProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BillingProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except DowngradeBlockedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/api/billing/downgrade")
def apply_billing_downgrade(
    payload: BillingDowngradeRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    _reject_shopify_managed_billing(membership.organization)

    organization = membership.organization
    _require_synchronized_paddle_subscription(db, organization)
    try:
        current_plan, target_plan, current_period, target_period = (
            validate_plan_downgrade(
                organization,
                payload.plan,
                db,
                payload.billing_period_months,
            )
        )
    except InvalidBillingPlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoActiveSubscriptionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DowngradePeriodChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DowngradeNoopError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpgradeNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DowngradeBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        return apply_downgrade(
            organization,
            target_plan,
            target_period,
            current_plan,
            current_period,
            payload.store_ids,
            db,
        )
    except BillingProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BillingProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except StoreSelectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DowngradeBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/api/billing/downgrade")
def cancel_billing_downgrade(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    _reject_shopify_managed_billing(membership.organization)
    return cancel_downgrade(membership.organization, db)


@router.post("/api/internal/billing/process-downgrades")
def process_downgrades_internal(
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
    db: Session = Depends(get_db),
):
    expected_secret = os.getenv("DIAGLOB_INTERNAL_SECRET")
    if (
        not expected_secret
        or not x_internal_secret
        or not secrets.compare_digest(x_internal_secret, expected_secret)
    ):
        raise HTTPException(status_code=401, detail="Unauthorized internal request")

    results = process_pending_downgrades(db)
    return {"ok": True, "processed": len(results), "results": results}


@router.get("/api/billing/paddle/status")
def get_paddle_synchronization_status(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Read-only, scoped billing capabilities; never expose Paddle IDs."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    organization = membership.organization
    _reject_shopify_managed_billing(organization)
    return get_paddle_billing_capabilities(db, organization)


@router.get("/api/billing/paddle/catalog")
def get_paddle_checkout_catalog(
    request: Request,
    membership: OrganizationMembership = Depends(get_current_membership),
):
    """Expose public Paddle price IDs and edge-detected location to its UI."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = membership.organization
    _reject_shopify_managed_billing(organization)
    provider_name = (organization.billing_provider or "paddle").strip().lower()
    if provider_name != "paddle":
        raise HTTPException(status_code=409, detail="Paddle checkout is unavailable")

    try:
        price_ids = {
            plan: {
                "month": get_billing_price_id(plan, 1, "paddle"),
                "year": get_billing_price_id(plan, 12, "paddle"),
            }
            for plan in ("starter", "growth", "pro", "scale")
        }
    except (InvalidBillingPlanError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Paddle price catalog is not configured for this environment",
        ) from exc

    return {
        "price_ids": price_ids,
        "country_code": paddle_country_code(
            request.headers,
            trusted_header=os.getenv("PADDLE_TRUSTED_COUNTRY_HEADER"),
        ),
        "trial_days": TRIAL_DAYS,
    }


@router.post("/api/billing/paddle/checkout-intent")
def create_paddle_checkout_intent(
    payload: PaddleCheckoutIntentRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
):
    """Sign tenant and plan metadata before a Paddle.js price-ID checkout."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = membership.organization
    _reject_shopify_managed_billing(organization)
    provider_name = (organization.billing_provider or "paddle").strip().lower()
    if provider_name != "paddle":
        raise HTTPException(status_code=409, detail="Paddle checkout is unavailable")
    if (
        organization.billing_subscription_id
        and organization.subscription_status in {"active", "trialing", "past_due"}
    ):
        raise HTTPException(
            status_code=409,
            detail="Usa las opciones de cambio de plan para tu suscripción actual.",
        )

    plan_key = payload.plan.strip().lower()
    if plan_key not in {"starter", "growth", "pro", "scale"}:
        raise HTTPException(status_code=400, detail="Plan inválido")
    if payload.billing_period_months not in (1, 12):
        raise HTTPException(
            status_code=400,
            detail="Solo se ofrecen suscripciones mensuales y anuales",
        )

    try:
        price_id = get_billing_price_id(
            plan_key, payload.billing_period_months, "paddle",
        )
    except InvalidBillingPlanError as exc:
        raise HTTPException(
            status_code=503,
            detail="Paddle price catalog is not configured for this environment",
        ) from exc

    signing_secret = (os.getenv("PADDLE_WEBHOOK_SECRET") or "").strip()
    if not signing_secret:
        raise HTTPException(
            status_code=503,
            detail="Paddle checkout is not configured",
        )

    custom_data = create_signed_checkout_custom_data(
        organization_id=organization.id,
        plan=plan_key,
        billing_period_months=payload.billing_period_months,
        price_id=price_id,
        secret=signing_secret,
    )
    return {"price_id": price_id, "custom_data": custom_data}


@router.post("/api/billing/checkout")
def create_billing_checkout(
    payload: BillingCheckoutRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    _reject_shopify_managed_billing(membership.organization)

    organization = membership.organization
    if (
        organization.billing_subscription_id
        and organization.subscription_status in {"active", "trialing", "past_due"}
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "La organización ya tiene una suscripción activa. "
                "Usa upgrade o downgrade en lugar de crear un checkout nuevo."
            ),
        )

    plan_key = payload.plan.strip().lower()
    if plan_key not in {"starter", "growth", "pro", "scale"}:
        raise HTTPException(status_code=400, detail="Plan inválido")
    if payload.billing_period_months not in (1, 12):
        raise HTTPException(
            status_code=400,
            detail="Solo se ofrecen suscripciones mensuales y anuales",
        )

    try:
        get_billing_price_id(
            plan_key,
            payload.billing_period_months,
            organization.billing_provider,
        )
        return create_checkout(
            organization,
            plan_key,
            payload.billing_period_months,
        )
    except InvalidBillingPlanError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BillingProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BillingProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/billing/paddle/notifications")
async def paddle_verified_notifications(
    request: Request,
    db: Session = Depends(get_db),
):
    """SDK-verified raw Paddle deliveries. Acknowledged only after commit."""
    raw_body = await request.body()
    signature = request.headers.get("Paddle-Signature", "")
    secret = (os.getenv("PADDLE_FULFILLMENT_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Paddle fulfillment webhook is not configured")
    try:
        event = verify_notification(raw_body, signature, secret)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid Paddle signature or body") from exc
    try:
        return dispatch_verified_notification(event, db)
    except IntegrityError as exc:
        # Parallel deliveries may race to insert the same event ID.
        db.rollback()
        event_id = str(event.get("event_id") or "")
        if event_id and db.get(PaddleWebhookEvent, event_id):
            return {"ok": True, "duplicate": True, "event_type": event.get("event_type")}
        raise HTTPException(status_code=503, detail="Paddle event processing failed") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="Invalid Paddle event data") from exc
    except Exception:
        db.rollback()
        logger.exception("Paddle verified event processing failed")
        raise


@router.post("/api/billing/paddle/portal-session")
def mint_paddle_customer_portal_session(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    """Authenticated tenant context only; client never supplies a customer ID."""
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")
    organization = membership.organization
    _reject_shopify_managed_billing(organization)
    try:
        url = create_portal_session_url(db, organization)
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    from fastapi.responses import JSONResponse
    return JSONResponse({"url": url}, headers={"Cache-Control": "no-store"})
