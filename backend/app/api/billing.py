"""Billing HTTP router with a backwards-compatible Paddle webhook endpoint."""

import json
import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..billing_providers import (
    BillingProviderConfigurationError,
    BillingProviderError,
    get_billing_provider,
)
from ..db import get_db
from ..models import Organization, OrganizationMembership
from .deps import get_current_membership
from ..services.ai_usage_packages import fulfill_ai_usage_package_transaction
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

router = APIRouter()
logger = logging.getLogger(__name__)


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


@router.post("/api/billing/webhook")
async def paddle_billing_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Compatibility endpoint for the currently active Paddle provider."""
    provider = get_billing_provider("paddle")
    raw_body = await request.body()
    signature_header = provider.webhook_signature_header or "Paddle-Signature"
    signature = request.headers.get(signature_header, "")

    try:
        provider.verify_webhook(raw_body, signature)
    except BillingProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
    subscription_id = (
        data.get("id") if is_subscription_event else data.get("subscription_id")
    )
    transaction_id = data.get("id") if is_transaction_event else None
    customer_id = data.get("customer_id")
    custom_data = data.get("custom_data") or {}
    organization_id_raw = custom_data.get("organization_id")

    organization = resolve_organization(
        db,
        event_type,
        subscription_id,
        customer_id,
        organization_id_raw,
    )
    if organization is None:
        return {
            "ok": True,
            "ignored": True,
            "reason": "organization_not_found",
            "event_type": event_type,
        }

    if (
        is_transaction_event
        and custom_data.get("purchase_type") == "ai_usage_package"
    ):
        package_occurred_at = None
        if occurred_at_raw:
            try:
                package_occurred_at = datetime.fromisoformat(
                    occurred_at_raw.replace("Z", "+00:00")
                ).replace(tzinfo=None)
            except ValueError:
                package_occurred_at = None

        result = fulfill_ai_usage_package_transaction(
            db=db,
            organization_id=organization.id,
            data=data,
            occurred_at=package_occurred_at,
        )
        result["event_type"] = event_type
        result["transaction_id"] = transaction_id
        return result

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
            occurred_at = datetime.fromisoformat(
                occurred_at_raw.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except ValueError:
            occurred_at = None

    if is_out_of_order_event(organization, occurred_at):
        return {
            "ok": True,
            "ignored": True,
            "reason": "out_of_order_event",
            "event_type": event_type,
        }

    price_id = provider.get_subscription_price_id(data)
    plan_key = provider.get_plan_from_price_id(price_id) if price_id else None
    billing_period_months = (
        provider.get_billing_period_from_price_id(price_id) if price_id else None
    )

    update_billing_fields(
        organization,
        customer_id,
        subscription_id,
        price_id,
        billing_period_months,
    )

    status = data.get("status")
    if is_transaction_event:
        result = process_transaction_event(
            organization,
            event_id,
            occurred_at,
            plan_key,
            data,
            db,
        )
        result["event_type"] = event_type
        result["transaction_id"] = transaction_id
        return result

    return process_subscription_event(
        organization,
        event_id,
        occurred_at,
        event_type,
        plan_key,
        price_id,
        billing_period_months,
        status,
        data,
        db,
    )


@router.patch("/api/billing/auto-renew")
def update_billing_auto_renew(
    payload: BillingAutoRenewRequest,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    if membership.role not in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Billing access denied")

    organization = membership.organization
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

    organization = db.query(Organization).filter(
        Organization.id == membership.organization_id
    ).first()
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

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

    organization = membership.organization
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

    organization = membership.organization
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
