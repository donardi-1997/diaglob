"""Billing and Paddle HTTP router."""

import json
import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..billing import (
    verify_paddle_signature,
    get_subscription_price_id,
    get_plan_from_price_id,
    get_billing_period_from_price_id,
)
from ..plans import get_plan
from ..plan_limits import get_organization_limits, get_limits_for_plan
from ..db import get_db
from ..models import Organization, OrganizationMembership, Store
from .deps import get_current_membership
from ..paddle_client import PaddleConfigError, PaddleProviderError
from ..services.billing_service import (
    InvalidBillingPlanError,
    NoActiveSubscriptionError,
    UpgradeNotAllowedError,
    DowngradeBlockedError,
    DowngradePeriodChangeError,
    DowngradeNoopError,
    StoreSelectionError,
    AutoRenewConflictError,
    BILLING_PLAN_ORDER,
    apply_downgrade,
    cancel_downgrade,
    configure_pending_downgrade_stores,
    create_checkout,
    execute_upgrade,
    get_billing_price_id,
    get_downgrade_active_stores,
    get_downgrade_preview_data,
    preview_upgrade_local,
    preview_upgrade_paddle,
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

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================
# DTOs
# ============================================================


class BillingAutoRenewRequest(BaseModel):
    enabled: bool


class BillingCheckoutRequest(BaseModel):
    plan: str
    billing_period_months: int = 1


class BillingUpgradeRequest(BaseModel):
    plan: str


class BillingDowngradeRequest(BaseModel):
    plan: str
    billing_period_months: int | None = None
    store_ids: list[int] | None = None


# ============================================================
# ROUTES
# ============================================================


@router.post("/api/billing/webhook")
async def paddle_billing_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    signature = request.headers.get("Paddle-Signature", "")

    webhook_secret = os.getenv("PADDLE_WEBHOOK_SECRET")

    if not webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Paddle webhook secret not configured",
        )

    try:
        verify_paddle_signature(raw_body, signature, webhook_secret)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc

    event_id = event.get("event_id")
    event_type = event.get("event_type")
    occurred_at_raw = event.get("occurred_at")
    data = event.get("data") or {}

    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Invalid Paddle event")

    if event_type not in SUPPORTED_EVENTS:
        return {"ok": True, "ignored": True, "event_type": event_type}

    is_subscription_event = event_type in SUBSCRIPTION_EVENTS
    is_transaction_event = event_type in TRANSACTION_EVENTS

    if is_subscription_event:
        subscription_id = data.get("id")
    else:
        subscription_id = data.get("subscription_id")

    transaction_id = None
    if is_transaction_event:
        transaction_id = data.get("id")

    customer_id = data.get("customer_id")
    custom_data = data.get("custom_data") or {}
    organization_id_raw = custom_data.get("organization_id")

    organization = resolve_organization(
        db, event_type, subscription_id, customer_id, organization_id_raw
    )

    if organization is None:
        return {
            "ok": True,
            "ignored": True,
            "reason": "organization_not_found",
            "event_type": event_type,
        }

    if not is_canonical_subscription(organization, subscription_id):
        return {
            "ok": True,
            "ignored": True,
            "reason": "non_canonical_subscription",
            "event_type": event_type,
            "organization_id": organization.id,
            "subscription_id": subscription_id,
            "canonical_subscription_id": organization.billing_subscription_id,
        }

    if is_duplicate_event(organization, event_id):
        return {"ok": True, "duplicate": True, "event_type": event_type}

    occurred_at = None
    if occurred_at_raw:
        try:
            occurred_at = (
                datetime.fromisoformat(
                    occurred_at_raw.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            )
        except ValueError:
            occurred_at = None

    if is_out_of_order_event(organization, occurred_at):
        return {"ok": True, "ignored": True, "reason": "out_of_order_event", "event_type": event_type}

    price_id = get_subscription_price_id(data)
    plan_key = None
    billing_period_months = None

    if price_id:
        plan_key = get_plan_from_price_id(price_id)
        billing_period_months = get_billing_period_from_price_id(price_id)

    update_billing_fields(organization, customer_id, subscription_id, price_id, billing_period_months)

    status = data.get("status")

    if is_transaction_event:
        result = process_transaction_event(
            organization, event_id, occurred_at, plan_key, data, db
        )
        result["event_type"] = event_type
        result["transaction_id"] = transaction_id
        return result

    result = process_subscription_event(
        organization, event_id, occurred_at, event_type, plan_key,
        price_id, billing_period_months, status, data, db
    )
    return result


@router.patch("/api/billing/auto-renew")
def update_billing_auto_renew(
    payload: BillingAutoRenewRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = membership.organization

    subscription_id = organization.billing_subscription_id

    if not subscription_id:
        raise HTTPException(
            status_code=409,
            detail="La organización no tiene una suscripción Paddle asociada.",
        )

    status = (organization.subscription_status or "").strip().lower()

    if status not in {"active", "trialing"}:
        raise HTTPException(
            status_code=409,
            detail="La renovación automática solo puede modificarse mientras la suscripción está activa.",
        )

    try:
        if payload.enabled:
            result = toggle_auto_renew_enable(organization, db)
        else:
            result = toggle_auto_renew_disable(organization, db)
    except AutoRenewConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PaddleProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return result


@router.post("/api/billing/upgrade/preview")
def preview_billing_upgrade(
    payload: BillingUpgradeRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = db.query(Organization).filter(
        Organization.id == membership.organization_id
    ).first()

    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    try:
        current_plan, target_plan = validate_plan_upgrade(organization, payload.plan)
    except InvalidBillingPlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoActiveSubscriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UpgradeNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    logger.info(
        "billing.preview org=%s current=%s target=%s",
        organization.id,
        current_plan,
        target_plan,
    )

    paddle_result = preview_upgrade_paddle(organization, target_plan)

    if paddle_result is not None:
        paddle_result["current_plan"] = current_plan
        paddle_result["target_plan"] = target_plan
        return paddle_result

    local_result = preview_upgrade_local(organization, current_plan, target_plan)
    return local_result


@router.post("/api/billing/upgrade")
def apply_billing_upgrade(
    payload: BillingUpgradeRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = db.query(Organization).filter(
        Organization.id == membership.organization_id
    ).first()

    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    try:
        current_plan, target_plan = validate_plan_upgrade(organization, payload.plan)
    except InvalidBillingPlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NoActiveSubscriptionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UpgradeNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        result = execute_upgrade(organization, target_plan, db)
    except PaddleProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return result


@router.post("/api/billing/downgrade/preview")
def preview_billing_downgrade(
    payload: BillingDowngradeRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = membership.organization

    print(
        "[DOWNGRADE APPLY START]",
        "organization=",
        organization.id,
        "current_plan=",
        organization.plan,
        "target=",
        payload.plan,
        "store_ids=",
        payload.store_ids,
    )

    try:
        current_plan, target_plan, current_period, target_period = validate_plan_downgrade(
            organization, payload.plan, db, payload.billing_period_months
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
        result = get_downgrade_preview_data(
            organization, current_plan, target_plan, target_period, current_period, db
        )
    except PaddleProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except DowngradeBlockedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return result


@router.post("/api/billing/downgrade")
def apply_billing_downgrade(
    payload: BillingDowngradeRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = membership.organization

    try:
        current_plan, target_plan, current_period, target_period = validate_plan_downgrade(
            organization, payload.plan, db, payload.billing_period_months
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
        result = apply_downgrade(
            organization, target_plan, target_period, current_plan, current_period,
            payload.store_ids, db,
        )
    except PaddleProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except StoreSelectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DowngradeBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    print(
        "[DOWNGRADE APPLY COMMIT]",
        "organization=",
        organization.id,
        "plan=",
        organization.plan,
        "pending=",
        organization.pending_plan,
        "effective=",
        organization.pending_plan_effective_at,
        "prepared=",
        organization.pending_plan_prepared_at,
    )

    return result


@router.delete("/api/billing/downgrade")
def cancel_billing_downgrade(
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = membership.organization

    return cancel_downgrade(organization, db)


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


@router.post("/api/billing/checkout")
def create_billing_checkout(
    payload: BillingCheckoutRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

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

    try:
        get_billing_price_id(plan_key, payload.billing_period_months)
    except InvalidBillingPlanError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    api_key = os.getenv("PADDLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Paddle no está configurado")

    try:
        result = create_checkout(organization, plan_key, payload.billing_period_months)
    except PaddleProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return result
