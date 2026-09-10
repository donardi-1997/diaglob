"""Billing business orchestration service.

Handles plan validation, upgrade/downgrade logic, store-limit enforcement,
pending downgrade processing, auto-renew orchestration, and checkout orchestration.
Does NOT import FastAPI or httpx.
"""
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from ..billing import (
    add_billing_months,
    calculate_local_proration,
    resolve_billing_period,
    get_paddle_price_id,
    get_plan_from_price_id,
    get_subscription_price_id,
    get_billing_period_from_price_id,
)
from ..models import Organization, Store
from ..plan_limits import get_limits_for_plan
from ..paddle_client import (
    PaddleConfigError,
    PaddleProviderError,
    cancel_subscription,
    create_transaction,
    get_subscription,
    preview_subscription_update,
    resume_subscription,
    update_subscription,
)

logger = logging.getLogger(__name__)


def _build_upgrade_next_billed_at(
    billing_period_months: int,
    now: datetime | None = None,
) -> str:
    current = now or datetime.utcnow()
    cycle_end = add_billing_months(current, int(billing_period_months or 1))
    return cycle_end.replace(microsecond=0).isoformat() + "Z"


BILLING_PLAN_ORDER = {
    "starter": 1,
    "growth": 2,
    "pro": 3,
    "scale": 4,
}


class InvalidBillingPlanError(Exception):
    pass


class NoActiveSubscriptionError(Exception):
    pass


class UpgradeNotAllowedError(Exception):
    pass


class DowngradeBlockedError(Exception):
    pass


class DowngradePeriodChangeError(Exception):
    pass


class StoreSelectionError(Exception):
    pass


class DowngradeNoopError(Exception):
    pass


class AutoRenewConflictError(Exception):
    pass


def get_billing_price_id(plan_key: str, billing_period_months: int = 1) -> str:
    try:
        return get_paddle_price_id(plan_key, billing_period_months)
    except ValueError as exc:
        raise InvalidBillingPlanError(str(exc)) from exc


def validate_plan_upgrade(organization: Organization, target_plan: str):
    current_plan = (organization.plan or "none").strip().lower()
    target_plan = target_plan.strip().lower()

    if target_plan not in BILLING_PLAN_ORDER:
        logger.warning(
            "billing.preview.rejected org=%s reason=invalid_target_plan current=%s target=%s",
            organization.id,
            current_plan,
            target_plan,
        )
        raise InvalidBillingPlanError("Invalid target plan")

    if current_plan not in BILLING_PLAN_ORDER:
        logger.warning(
            "billing.preview.rejected org=%s reason=no_active_subscription current=%s",
            organization.id,
            current_plan,
        )
        raise NoActiveSubscriptionError(
            "No tienes una suscripcion activa "
            "para actualizar. Usa el checkout normal."
        )

    subscription_status = (organization.subscription_status or "").strip().lower()
    if subscription_status != "active":
        logger.warning(
            "billing.preview.rejected org=%s reason=subscription_not_active status=%s",
            organization.id,
            subscription_status or None,
        )
        raise UpgradeNotAllowedError(
            "La suscripción debe estar activa para realizar un upgrade con crédito prorrateado."
        )

    if BILLING_PLAN_ORDER[target_plan] <= BILLING_PLAN_ORDER[current_plan]:
        logger.warning(
            "billing.preview.rejected org=%s reason=not_upgrade current=%s target=%s",
            organization.id,
            current_plan,
            target_plan,
        )
        raise UpgradeNotAllowedError(
            "Este endpoint solo permite "
            "escalar hacia un plan superior."
        )

    return current_plan, target_plan


def validate_plan_downgrade(
    organization: Organization,
    target_plan: str,
    db: Session,
    target_billing_period_months: int | None = None,
):
    current_plan = (organization.plan or "none").lower()
    target_plan = (target_plan or "").strip().lower()

    if target_plan not in BILLING_PLAN_ORDER:
        raise InvalidBillingPlanError("Plan de destino inválido")

    current_rank = BILLING_PLAN_ORDER.get(current_plan, 0)
    target_rank = BILLING_PLAN_ORDER.get(target_plan, 0)

    if current_rank <= 0:
        raise NoActiveSubscriptionError("La organización no tiene un plan activo")

    current_period = int(organization.billing_period_months or 1)
    target_period = int(target_billing_period_months or current_period)

    if target_period not in {1, 3, 6, 12}:
        raise InvalidBillingPlanError("Período de facturación inválido")

    plan_changes = target_plan != current_plan
    period_changes = target_period != current_period

    if period_changes:
        raise DowngradePeriodChangeError(
            "No puedes cambiar el período de facturación "
            "de una suscripción activa. Puedes cambiar de "
            "plan manteniendo tu período actual."
        )

    if not plan_changes:
        raise DowngradeNoopError("No hay ningún cambio para realizar")

    if target_rank > current_rank and not period_changes:
        raise UpgradeNotAllowedError(
            "Los upgrades con el mismo período "
            "deben realizarse con prorrata inmediata"
        )

    if organization.subscription_status not in {"active", "trialing"}:
        raise DowngradeBlockedError(
            "La suscripción debe estar activa "
            "para programar el cambio"
        )

    if not organization.billing_subscription_id:
        raise DowngradeBlockedError("No existe una suscripción Paddle asociada")

    if not organization.auto_renew_enabled:
        raise DowngradeBlockedError(
            "Activa la renovación automática antes de "
            "programar un cambio de plan o período"
        )

    return current_plan, target_plan, current_period, target_period


def get_downgrade_active_stores(db: Session, organization_id: int):
    return (
        db.query(Store)
        .filter(
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
            Store.active.is_(True),
        )
        .order_by(
            Store.active_since.is_(None),
            Store.active_since.asc(),
            Store.id.asc(),
        )
        .all()
    )


def configure_pending_downgrade_stores(
    db: Session,
    organization: Organization,
    target_plan: str,
    requested_store_ids: list[int] | None,
):
    target_limit = int(get_limits_for_plan(target_plan).active_stores)

    available_stores = (
        db.query(Store)
        .filter(
            Store.organization_id == organization.id,
            Store.deleted.is_(False),
        )
        .order_by(Store.id.asc())
        .all()
    )

    available_ids = {store.id for store in available_stores}

    requested_ids = list(dict.fromkeys(requested_store_ids or []))

    invalid_ids = [store_id for store_id in requested_ids if store_id not in available_ids]

    if invalid_ids:
        raise StoreSelectionError("Una o más tiendas seleccionadas no están disponibles.")

    if len(requested_ids) > target_limit:
        raise StoreSelectionError(
            f"El plan {target_plan} permite máximo {target_limit} tiendas activas."
        )

    db.query(Store).filter(Store.organization_id == organization.id).update(
        {Store.keep_on_pending_downgrade: False},
        synchronize_session=False,
    )

    if requested_ids:
        db.query(Store).filter(
            Store.organization_id == organization.id,
            Store.id.in_(requested_ids),
        ).update(
            {Store.keep_on_pending_downgrade: True},
            synchronize_session=False,
        )

    return {"target_store_limit": target_limit, "selected_store_ids": requested_ids}


def process_pending_downgrades(db: Session, now: datetime | None = None):
    now = now or datetime.utcnow()
    preparation_window = timedelta(hours=2)

    organizations = (
        db.query(Organization)
        .filter(
            Organization.pending_plan.isnot(None),
            Organization.pending_plan_effective_at.isnot(None),
            Organization.pending_plan_prepared_at.is_(None),
            Organization.billing_subscription_id.isnot(None),
        )
        .all()
    )

    results = []

    for organization in organizations:
        effective_at = organization.pending_plan_effective_at

        if not effective_at:
            continue

        prepare_at = effective_at - preparation_window

        if now < prepare_at:
            continue

        if now >= effective_at:
            results.append({
                "organization_id": organization.id,
                "status": "effective_time_reached",
            })
            continue

        target_plan = (organization.pending_plan or "").lower()

        if target_plan not in BILLING_PLAN_ORDER:
            results.append({
                "organization_id": organization.id,
                "status": "invalid_pending_plan",
            })
            continue

        target_period = int(
            organization.pending_billing_period_months
            or organization.billing_period_months
            or 1
        )

        if target_period not in {1, 3, 6, 12}:
            results.append({
                "organization_id": organization.id,
                "status": "invalid_pending_period",
                "pending_billing_period_months": target_period,
            })
            continue

        try:
            target_price_id = get_paddle_price_id(target_plan, target_period)
        except Exception as exc:
            results.append({
                "organization_id": organization.id,
                "status": "price_error",
                "error": str(exc),
            })
            continue

        if not target_price_id:
            results.append({
                "organization_id": organization.id,
                "status": "price_not_configured",
                "pending_plan": target_plan,
            })
            continue

        subscription_id = organization.billing_subscription_id

        body = {
            "items": [{"price_id": target_price_id, "quantity": 1}],
            "proration_billing_mode": "do_not_bill",
            "on_payment_failure": "prevent_change",
            "custom_data": {
                "organization_id": str(organization.id),
                "pending_plan": target_plan,
                "pending_billing_period_months": target_period,
                "diaglob_plan_change": "scheduled",
            },
        }

        try:
            update_subscription(
                subscription_id,
                items=body["items"],
                proration_billing_mode="do_not_bill",
                on_payment_failure="prevent_change",
                custom_data=body["custom_data"],
                timeout=30,
            )
        except PaddleProviderError as exc:
            results.append({
                "organization_id": organization.id,
                "status": "paddle_rejected",
                "paddle_status": exc.status_code,
                "paddle_response": str(exc.detail),
            })
            continue

        organization.pending_plan_prepared_at = now
        db.commit()

        results.append({
            "organization_id": organization.id,
            "status": "prepared",
            "current_plan": organization.plan,
            "pending_plan": target_plan,
            "pending_billing_period_months": target_period,
            "effective_at": effective_at.isoformat(),
            "prepared_at": now.isoformat(),
        })

    return results


def execute_upgrade(
    organization: Organization,
    target_plan: str,
    db: Session,
) -> dict:
    target_price_id = get_paddle_price_id(
        target_plan, organization.billing_period_months
    )

    next_billed_at = _build_upgrade_next_billed_at(
        organization.billing_period_months
    )

    paddle_data = update_subscription(
        subscription_id=organization.billing_subscription_id,
        items=[{"price_id": target_price_id, "quantity": 1}],
        proration_billing_mode="prorated_immediately",
        on_payment_failure="prevent_change",
        custom_data={
            "organization_id": str(organization.id),
            "plan": target_plan,
        },
        next_billed_at=next_billed_at,
    )

    paddle_price_id = (
        get_subscription_price_id(paddle_data) or target_price_id
    )

    confirmed_plan = get_plan_from_price_id(paddle_price_id) if paddle_price_id else None
    organization.plan = confirmed_plan or target_plan

    organization.billing_price_id = paddle_price_id

    confirmed_period = (
        get_billing_period_from_price_id(paddle_price_id) if paddle_price_id else None
    )

    if confirmed_period is not None:
        organization.billing_period_months = confirmed_period

    organization.pending_plan = None
    organization.pending_billing_period_months = None
    organization.pending_plan_effective_at = None
    organization.pending_plan_prepared_at = None

    db.query(Store).filter(Store.organization_id == organization.id).update(
        {Store.keep_on_pending_downgrade: False},
        synchronize_session=False,
    )

    db.commit()
    db.refresh(organization)

    return {
        "ok": True,
        "current_plan": target_plan,
        "target_plan": target_plan,
        "subscription_id": organization.billing_subscription_id,
        "paddle_status": paddle_data.get("status"),
        "next_billed_at": paddle_data.get("next_billed_at"),
        "message": "Upgrade enviado a Paddle",
    }


def preview_upgrade_paddle(
    organization: Organization,
    target_plan: str,
) -> dict | None:
    paddle_api_key = os.getenv("PADDLE_API_KEY")

    if not paddle_api_key or not organization.billing_subscription_id:
        return None

    try:
        target_price_id = get_paddle_price_id(
            target_plan, organization.billing_period_months
        )
    except ValueError:
        logger.warning(
            "billing.preview paddle_price_unavailable org=%s plan=%s period=%s",
            organization.id,
            target_plan,
            organization.billing_period_months,
        )
        return None

    if not target_price_id:
        return None

    items = [{"price_id": target_price_id, "quantity": 1}]
    next_billed_at = _build_upgrade_next_billed_at(
        organization.billing_period_months
    )

    paddle_data = preview_subscription_update(
        subscription_id=organization.billing_subscription_id,
        items=items,
        proration_billing_mode="prorated_immediately",
        on_payment_failure="prevent_change",
        next_billed_at=next_billed_at,
    )

    if not paddle_data:
        return None

    immediate_transaction = paddle_data.get("immediate_transaction") or {}
    details = immediate_transaction.get("details") or {}
    totals = details.get("totals") or {}
    line_items = details.get("line_items") or []

    provider_summary = paddle_data.get("update_summary") or {}
    provider_credit = provider_summary.get("credit") or {}
    provider_charge = provider_summary.get("charge") or {}
    provider_result = provider_summary.get("result") or {}

    def minor_amount(value) -> int:
        try:
            return abs(int(value or 0))
        except (TypeError, ValueError):
            return 0

    if provider_result:
        result_action = provider_result.get("action") or "none"
        result_amount = minor_amount(provider_result.get("amount"))
        credit_amount = minor_amount(provider_credit.get("amount"))
        charge_amount = minor_amount(provider_charge.get("amount"))
        currency_code = (
            provider_result.get("currency_code")
            or provider_charge.get("currency_code")
            or provider_credit.get("currency_code")
            or totals.get("currency_code")
            or "USD"
        )
    else:
        charge_amount = 0
        credit_amount = 0

        for line_item in line_items:
            line_totals = line_item.get("totals") or {}
            try:
                line_total = int(line_totals.get("total") or 0)
            except (TypeError, ValueError):
                line_total = 0

            if line_total > 0:
                charge_amount += line_total
            elif line_total < 0:
                credit_amount += abs(line_total)

        try:
            raw_result_amount = int(totals.get("total") or 0)
        except (TypeError, ValueError):
            raw_result_amount = 0

        if raw_result_amount > 0:
            result_action = "charge"
        elif raw_result_amount < 0:
            result_action = "credit"
        else:
            result_action = "none"

        result_amount = abs(raw_result_amount)
        currency_code = totals.get("currency_code") or "USD"

    normalized_update_summary = {
        "charge": {
            "amount": str(charge_amount),
            "currency_code": currency_code,
        },
        "credit": {
            "amount": str(credit_amount),
            "currency_code": currency_code,
        },
        "result": {
            "action": result_action,
            "amount": str(result_amount),
            "currency_code": currency_code,
        },
    }

    amount_due = result_amount if result_action == "charge" else 0

    next_transaction = paddle_data.get("next_transaction") or {}
    next_billing_period = next_transaction.get("billing_period") or {}

    return {
        "current_plan": None,
        "target_plan": None,
        "subscription_id": organization.billing_subscription_id,
        "next_billed_at": paddle_data.get("next_billed_at") or next_billing_period.get("starts_at"),
        "currency_code": currency_code,
        "amount_due": str(amount_due),
        "subtotal": totals.get("subtotal"),
        "tax": totals.get("tax"),
        "update_summary": normalized_update_summary,
        "immediate_transaction": immediate_transaction,
        "next_transaction": paddle_data.get("next_transaction"),
    }


def preview_upgrade_local(
    organization: Organization,
    current_plan: str,
    target_plan: str,
) -> dict:
    billing_period = organization.billing_period_months or 1
    now = datetime.utcnow()
    period_start, period_end = resolve_billing_period(
        organization.created_at or now,
        billing_period,
        now,
    )

    local_preview = calculate_local_proration(
        current_plan=current_plan,
        target_plan=target_plan,
        billing_period_months=billing_period,
        current_period_start=period_start,
        current_period_end=period_end,
        now=now,
    )

    amount_cents = int(Decimal(local_preview["amount_due_now"]) * 100)
    credit_cents = int(Decimal(local_preview["credit"]) * 100)
    charge_cents = int(Decimal(local_preview["charge"]) * 100)

    return {
        "current_plan": current_plan,
        "target_plan": target_plan,
        "subscription_id": organization.billing_subscription_id,
        "next_billed_at": local_preview["next_billed_at"],
        "currency_code": local_preview["currency"],
        "amount_due": str(amount_cents),
        "subtotal": None,
        "tax": None,
        "update_summary": {
            "charge": {"amount": str(charge_cents), "currency_code": local_preview["currency"]},
            "credit": {"amount": str(credit_cents), "currency_code": local_preview["currency"]},
            "result": {
                "action": "charge" if amount_cents > 0 else "none",
                "amount": str(abs(amount_cents)),
                "currency_code": local_preview["currency"],
            },
        },
        "immediate_transaction": None,
        "next_transaction": None,
        "_source": "local",
    }


def apply_downgrade(
    organization: Organization,
    target_plan: str,
    target_period: int,
    current_plan: str,
    current_period: int,
    store_ids: list[int] | None,
    db: Session,
) -> dict:
    subscription_id = organization.billing_subscription_id

    is_plan_downgrade = (
        BILLING_PLAN_ORDER.get(target_plan, 0)
        < BILLING_PLAN_ORDER.get(current_plan, 0)
    )

    if is_plan_downgrade:
        selection = configure_pending_downgrade_stores(
            db, organization, target_plan, store_ids
        )
    else:
        db.query(Store).filter(Store.organization_id == organization.id).update(
            {Store.keep_on_pending_downgrade: False},
            synchronize_session=False,
        )
        selection = {
            "target_store_limit": int(get_limits_for_plan(target_plan).active_stores),
            "selected_store_ids": [],
        }

    paddle_data = get_subscription(subscription_id)

    next_billed_at_raw = paddle_data.get("next_billed_at")

    if not next_billed_at_raw:
        raise DowngradeBlockedError(
            "Paddle no informó la próxima fecha de renovación"
        )

    try:
        effective_at = (
            datetime.fromisoformat(
                next_billed_at_raw.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        )
    except ValueError:
        raise DowngradeBlockedError(
            "Paddle devolvió una fecha de renovación inválida"
        )

    organization.pending_plan = target_plan
    organization.pending_billing_period_months = target_period
    organization.pending_plan_effective_at = effective_at
    organization.pending_plan_prepared_at = None

    db.commit()
    db.refresh(organization)

    return {
        "ok": True,
        "current_plan": current_plan,
        "pending_plan": target_plan,
        "pending_billing_period_months": target_period,
        "effective_at": next_billed_at_raw,
        "subscription_id": subscription_id,
        "selected_store_ids": selection.get("selected_store_ids", []),
        "target_store_limit": selection.get("target_store_limit"),
        "paddle_status": paddle_data.get("status"),
        "message": (
            "Downgrade programado. "
            "Paddle conservará el plan actual "
            "hasta el procesamiento de la renovación."
        ),
    }


def cancel_downgrade(organization: Organization, db: Session):
    if not organization.pending_plan:
        return {"ok": True, "pending_plan": None}

    organization.pending_plan = None
    organization.pending_billing_period_months = None
    organization.pending_plan_effective_at = None
    organization.pending_plan_prepared_at = None

    db.query(Store).filter(Store.organization_id == organization.id).update(
        {Store.keep_on_pending_downgrade: False},
        synchronize_session=False,
    )

    db.commit()

    return {"ok": True, "pending_plan": None, "message": "Cambio de plan programado cancelado"}


def toggle_auto_renew_enable(
    organization: Organization,
    db: Session,
) -> dict:
    subscription_id = organization.billing_subscription_id

    paddle_data = get_subscription(subscription_id)

    scheduled_change = paddle_data.get("scheduled_change")
    scheduled_action = (
        scheduled_change.get("action")
        if isinstance(scheduled_change, dict)
        else None
    )

    if scheduled_action is None:
        organization.auto_renew_enabled = True
        db.commit()
        return {
            "ok": True,
            "auto_renew_enabled": True,
            "scheduled_change": None,
            "message": "La renovación automática ya está activa.",
        }

    if scheduled_action != "cancel":
        raise AutoRenewConflictError(
            "La suscripción tiene otro cambio "
            "programado en Paddle y no puede "
            "reactivarse automáticamente."
        )

    resume_data = resume_subscription(subscription_id)

    organization.auto_renew_enabled = True
    db.commit()

    return {
        "ok": True,
        "auto_renew_enabled": True,
        "scheduled_change": resume_data.get("scheduled_change"),
        "next_billed_at": resume_data.get("next_billed_at"),
        "message": "Renovación automática activada.",
    }


def toggle_auto_renew_disable(
    organization: Organization,
    db: Session,
) -> dict:
    subscription_id = organization.billing_subscription_id

    paddle_data = get_subscription(subscription_id)

    scheduled_change = paddle_data.get("scheduled_change")
    scheduled_action = (
        scheduled_change.get("action")
        if isinstance(scheduled_change, dict)
        else None
    )

    if scheduled_action == "cancel":
        organization.auto_renew_enabled = False
        db.commit()
        return {
            "ok": True,
            "auto_renew_enabled": False,
            "scheduled_change": scheduled_change,
            "effective_at": scheduled_change.get("effective_at"),
            "message": "La renovación ya estaba desactivada.",
        }

    if scheduled_action is not None:
        raise AutoRenewConflictError(
            "La suscripción ya tiene otro cambio programado en Paddle."
        )

    cancel_data = cancel_subscription(subscription_id)

    paddle_data_inner = cancel_data

    scheduled_change_inner = paddle_data_inner.get("scheduled_change") or {}

    organization.pending_plan = None
    organization.pending_billing_period_months = None
    organization.pending_plan_effective_at = None
    organization.pending_plan_prepared_at = None

    db.query(Store).filter(Store.organization_id == organization.id).update(
        {Store.keep_on_pending_downgrade: False},
        synchronize_session=False,
    )

    organization.auto_renew_enabled = False
    db.commit()

    return {
        "ok": True,
        "auto_renew_enabled": False,
        "scheduled_change": paddle_data_inner.get("scheduled_change"),
        "effective_at": scheduled_change_inner.get("effective_at"),
        "next_billed_at": paddle_data_inner.get("next_billed_at"),
        "message": "Renovación automática desactivada.",
    }


def create_checkout(
    organization: Organization,
    plan_key: str,
    billing_period_months: int,
) -> dict:
    price_id = get_paddle_price_id(plan_key, billing_period_months)

    data = create_transaction(
        price_id=price_id,
        organization_id=organization.id,
        plan_key=plan_key,
        billing_period_months=billing_period_months,
    )

    checkout = data.get("checkout") or {}
    checkout_url = checkout.get("url")

    if not checkout_url:
        raise PaddleProviderError(
            status_code=502,
            detail={"message": "Paddle no devolvió una URL de checkout"},
        )

    # Analytics: checkout started
    from .product_analytics import track_checkout_started
    track_checkout_started(
        user_id=0,  # No user context in service
        organization_id=organization.id,
        plan=plan_key,
    )

    return {
        "plan": plan_key,
        "transaction_id": data.get("id"),
        "checkout_url": checkout_url,
    }


def get_downgrade_preview_data(
    organization: Organization,
    current_plan: str,
    target_plan: str,
    target_period: int,
    current_period: int,
    db: Session,
) -> dict:
    is_period_change = target_period != current_period

    if is_period_change:
        subscription_data = get_subscription(organization.billing_subscription_id)
        current_billing_period = subscription_data.get("current_billing_period") or {}
        effective_at = current_billing_period.get("ends_at")
        if not effective_at:
            effective_at = subscription_data.get("next_billed_at")

        if not effective_at:
            raise DowngradeBlockedError(
                "Paddle no devolvió la fecha de fin del período actual"
            )

        paddle_data = {
            "next_billed_at": effective_at,
            "immediate_transaction": None,
            "next_transaction": None,
        }
    else:
        items = [{"price_id": get_paddle_price_id(target_plan, target_period), "quantity": 1}]
        paddle_data = preview_subscription_update(
            subscription_id=organization.billing_subscription_id,
            items=items,
            proration_billing_mode="do_not_bill",
            on_payment_failure="prevent_change",
        )

        if not paddle_data:
            raise PaddleProviderError(
                status_code=502,
                detail={"message": "No fue posible consultar Paddle"},
            )

    available_stores = (
        db.query(Store)
        .filter(
            Store.organization_id == organization.id,
            Store.deleted.is_(False),
        )
        .order_by(
            Store.active.desc(),
            Store.active_since.is_(None),
            Store.active_since.asc(),
            Store.id.asc(),
        )
        .all()
    )

    target_store_limit = int(get_limits_for_plan(target_plan).active_stores)

    return {
        "ok": True,
        "target_store_limit": target_store_limit,
        "requires_store_selection": bool(
            available_stores
            and (
                BILLING_PLAN_ORDER.get(target_plan, 0)
                < BILLING_PLAN_ORDER.get(current_plan, 0)
            )
        ),
        "available_stores": [
            {
                "id": store.id,
                "name": store.name,
                "active": bool(store.active),
                "active_since": (
                    store.active_since.isoformat() + "Z"
                    if store.active_since
                    else None
                ),
            }
            for store in available_stores
        ],
        "current_plan": current_plan,
        "target_plan": target_plan,
        "current_billing_period_months": current_period,
        "target_billing_period_months": target_period,
        "subscription_id": organization.billing_subscription_id,
        "effective_at": paddle_data.get("next_billed_at"),
        "next_billed_at": paddle_data.get("next_billed_at"),
        "immediate_transaction": paddle_data.get("immediate_transaction"),
        "next_transaction": paddle_data.get("next_transaction"),
    }
