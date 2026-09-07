"""Billing and Paddle HTTP router."""

import json
import logging
import os
import secrets
import httpx
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..billing import (
    calculate_local_proration,
    get_billing_period_from_price_id,
    get_paddle_price_id,
    get_plan_from_price_id,
    get_subscription_price_id,
    verify_paddle_signature,
)
from ..plans import get_plan
from ..plan_limits import (
    get_organization_limits,
    get_limits_for_plan,
)
from ..db import get_db
from ..models import Organization, OrganizationMembership, Store
from .deps import get_current_membership

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
# CONSTANTS
# ============================================================

BILLING_PLAN_ORDER = {
    "starter": 1,
    "growth": 2,
    "pro": 3,
    "scale": 4,
}

# ============================================================
# HELPERS
# ============================================================

def get_paddle_base_url():
    environment = (
        os.getenv(
            "PADDLE_ENVIRONMENT",
            "sandbox",
        )
        .strip()
        .lower()
    )

    if environment == "production":
        return "https://api.paddle.com"

    return "https://sandbox-api.paddle.com"


def get_paddle_headers():
    api_key = os.getenv("PADDLE_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Paddle API key not configured",
        )

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def get_billing_price_id(
    plan_key: str,
    billing_period_months: int = 1,
):
    try:
        return get_paddle_price_id(
            plan_key,
            billing_period_months,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


def validate_plan_upgrade(
    organization: Organization,
    target_plan: str,
):
    import logging as _vpu_log
    logger = _vpu_log.getLogger(__name__)

    current_plan = (
        organization.plan
        or "none"
    ).strip().lower()

    target_plan = target_plan.strip().lower()

    if target_plan not in BILLING_PLAN_ORDER:
        logger.warning(
            "billing.preview.rejected org=%s reason=invalid_target_plan current=%s target=%s",
            organization.id,
            current_plan,
            target_plan,
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid target plan",
        )

    if current_plan not in BILLING_PLAN_ORDER:
        logger.warning(
            "billing.preview.rejected org=%s reason=no_active_subscription current=%s",
            organization.id,
            current_plan,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "No tienes una suscripcion activa "
                "para actualizar. Usa el checkout normal."
            ),
        )

    if (
        BILLING_PLAN_ORDER[target_plan]
        <= BILLING_PLAN_ORDER[current_plan]
    ):
        logger.warning(
            "billing.preview.rejected org=%s reason=not_upgrade current=%s target=%s",
            organization.id,
            current_plan,
            target_plan,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "Este endpoint solo permite "
                "escalar hacia un plan superior."
            ),
        )

    return (
        current_plan,
        target_plan,
    )


def validate_plan_downgrade(
    organization: Organization,
    target_plan: str,
    db: Session,
    target_billing_period_months: int | None = None,
):
    current_plan = (
        organization.plan
        or "none"
    ).lower()

    target_plan = (
        target_plan
        or ""
    ).strip().lower()

    if target_plan not in BILLING_PLAN_ORDER:
        raise HTTPException(
            status_code=400,
            detail="Plan de destino inválido",
        )

    current_rank = (
        BILLING_PLAN_ORDER.get(
            current_plan,
            0,
        )
    )

    target_rank = (
        BILLING_PLAN_ORDER.get(
            target_plan,
            0,
        )
    )

    if current_rank <= 0:
        raise HTTPException(
            status_code=400,
            detail="La organización no tiene un plan activo",
        )

    current_period = int(
        organization.billing_period_months
        or 1
    )

    target_period = int(
        target_billing_period_months
        or current_period
    )

    if target_period not in {
        1,
        3,
        6,
        12,
    }:
        raise HTTPException(
            status_code=400,
            detail="Período de facturación inválido",
        )

    plan_changes = (
        target_plan
        != current_plan
    )

    period_changes = (
        target_period
        != current_period
    )

    # ========================================================
    # MVP: EL PERÍODO DE UNA SUSCRIPCIÓN EXISTENTE ES FIJO
    # ========================================================
    #
    # El cliente puede cambiar de nivel de plan, pero debe
    # conservar siempre la duración contratada actualmente.
    #
    # Ejemplos:
    #
    # Starter 1M -> Growth 1M   permitido
    # Starter 1M -> Pro 1M      permitido
    # Starter 1M -> Starter 3M  bloqueado
    # Starter 1M -> Growth 3M   bloqueado
    # ========================================================

    if period_changes:
        raise HTTPException(
            status_code=409,
            detail=(
                "No puedes cambiar el período de facturación "
                "de una suscripción activa. Puedes cambiar de "
                "plan manteniendo tu período actual."
            ),
        )

    if not plan_changes:
        raise HTTPException(
            status_code=400,
            detail="No hay ningún cambio para realizar",
        )

    # Un upgrade que mantiene exactamente el mismo período
    # debe utilizar el flujo inmediato con prorrata.
    if (
        target_rank > current_rank
        and not period_changes
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Los upgrades con el mismo período "
                "deben realizarse con prorrata inmediata"
            ),
        )

    if (
        organization.subscription_status
        not in {
            "active",
            "trialing",
        }
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "La suscripción debe estar activa "
                "para programar el cambio"
            ),
        )

    if not organization.billing_subscription_id:
        raise HTTPException(
            status_code=409,
            detail="No existe una suscripción Paddle asociada",
        )

    if not organization.auto_renew_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Activa la renovación automática antes de "
                "programar un cambio de plan o período"
            ),
        )

    return (
        current_plan,
        target_plan,
        current_period,
        target_period,
    )


def get_downgrade_active_stores(
    db: Session,
    organization_id: int,
):
    return (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization_id,
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
    target_limit = int(
        get_limits_for_plan(
            target_plan
        ).active_stores
    )

    available_stores = (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
            Store.deleted.is_(False),
        )
        .order_by(Store.id.asc())
        .all()
    )

    available_ids = {
        store.id
        for store in available_stores
    }

    requested_ids = list(
        dict.fromkeys(
            requested_store_ids
            or []
        )
    )

    invalid_ids = [
        store_id
        for store_id in requested_ids
        if store_id not in available_ids
    ]

    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "Una o más tiendas seleccionadas "
                "no están disponibles."
            ),
        )

    if len(requested_ids) > target_limit:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El plan {target_plan} permite "
                f"máximo {target_limit} tiendas activas."
            ),
        )

    (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
        )
        .update(
            {
                Store.keep_on_pending_downgrade:
                    False,
            },
            synchronize_session=False,
        )
    )

    if requested_ids:
        (
            db.query(Store)
            .filter(
                Store.organization_id
                == organization.id,
                Store.id.in_(
                    requested_ids
                ),
            )
            .update(
                {
                    Store.keep_on_pending_downgrade:
                        True,
                },
                synchronize_session=False,
            )
        )

    return {
        "target_store_limit":
            target_limit,

        "selected_store_ids":
            requested_ids,
    }


def process_pending_downgrades(
    db: Session,
    now: datetime | None = None,
):
    now = (
        now
        or datetime.utcnow()
    )

    preparation_window = timedelta(
        hours=2
    )

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

        effective_at = (
            organization.pending_plan_effective_at
        )

        if not effective_at:
            continue

        prepare_at = (
            effective_at
            - preparation_window
        )

        if now < prepare_at:
            continue

        # Si ya pasó demasiado tiempo tampoco repetimos
        # cambios a ciegas. La renovación/webhook resolverá
        # el estado correspondiente.
        if now >= effective_at:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "effective_time_reached",
            })

            continue

        target_plan = (
            organization.pending_plan
            or ""
        ).lower()

        if target_plan not in BILLING_PLAN_ORDER:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "invalid_pending_plan",
            })

            continue

        target_period = int(
            organization.pending_billing_period_months
            or organization.billing_period_months
            or 1
        )

        if target_period not in {
            1,
            3,
            6,
            12,
        }:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "invalid_pending_period",
                "pending_billing_period_months":
                    target_period,
            })

            continue

        try:
            target_price_id = (
                get_paddle_price_id(
                    target_plan,
                    target_period,
                )
            )

        except Exception as exc:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "price_error",
                "error":
                    str(exc),
            })

            continue

        if not target_price_id:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "price_not_configured",
                "pending_plan":
                    target_plan,
            })

            continue

        subscription_id = (
            organization.billing_subscription_id
        )

        url = (
            f"{get_paddle_base_url()}"
            f"/subscriptions/"
            f"{subscription_id}"
        )

        body = {
            "items": [
                {
                    "price_id":
                        target_price_id,
                    "quantity":
                        1,
                }
            ],

            "proration_billing_mode":
                "do_not_bill",

            "on_payment_failure":
                "prevent_change",

            "custom_data": {
                "organization_id":
                    str(organization.id),

                "pending_plan":
                    target_plan,

                "pending_billing_period_months":
                    target_period,

                "diaglob_plan_change":
                    "scheduled",
            },
        }

        try:
            response = httpx.patch(
                url,
                headers=get_paddle_headers(),
                json=body,
                timeout=30,
            )

        except httpx.HTTPError as exc:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "paddle_network_error",
                "error":
                    str(exc),
            })

            continue

        if response.status_code >= 400:
            results.append({
                "organization_id":
                    organization.id,
                "status":
                    "paddle_rejected",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            })

            continue

        organization.pending_plan_prepared_at = (
            now
        )

        db.commit()

        results.append({
            "organization_id":
                organization.id,
            "status":
                "prepared",
            "current_plan":
                organization.plan,
            "pending_plan":
                target_plan,
            "pending_billing_period_months":
                target_period,
            "effective_at":
                effective_at.isoformat(),
            "prepared_at":
                now.isoformat(),
        })

    return results


# ============================================================
# ROUTES
# ============================================================

@router.post("/api/billing/webhook")
async def paddle_billing_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    signature = request.headers.get(
        "Paddle-Signature",
        "",
    )

    webhook_secret = os.getenv(
        "PADDLE_WEBHOOK_SECRET"
    )

    if not webhook_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Paddle webhook secret "
                "not configured"
            ),
        )

    try:
        verify_paddle_signature(
            raw_body,
            signature,
            webhook_secret,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
        ) from exc

    try:
        event = json.loads(
            raw_body.decode("utf-8")
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook payload",
        ) from exc

    event_id = event.get(
        "event_id"
    )

    event_type = event.get(
        "event_type"
    )

    occurred_at_raw = event.get(
        "occurred_at"
    )

    data = event.get(
        "data"
    ) or {}

    if not event_id or not event_type:
        raise HTTPException(
            status_code=400,
            detail="Invalid Paddle event",
        )

    # ========================================================
    # EVENTOS QUE DIAGLOB PROCESA
    # ========================================================

    subscription_events = {
        "subscription.created",
        "subscription.activated",
        "subscription.updated",
        "subscription.past_due",
        "subscription.paused",
        "subscription.resumed",
        "subscription.canceled",
    }

    transaction_events = {
        "transaction.completed",
    }

    supported_events = (
        subscription_events
        | transaction_events
    )

    if event_type not in supported_events:
        return {
            "ok": True,
            "ignored": True,
            "event_type": event_type,
        }

    is_subscription_event = (
        event_type in subscription_events
    )

    is_transaction_event = (
        event_type in transaction_events
    )

    # ========================================================
    # IDENTIFICADORES DE PADDLE
    # ========================================================
    #
    # En subscription.*:
    #   data.id = subscription_id
    #
    # En transaction.completed:
    #   data.id = transaction_id
    #   data.subscription_id = subscription_id
    # ========================================================

    if is_subscription_event:
        subscription_id = data.get(
            "id"
        )
    else:
        subscription_id = data.get(
            "subscription_id"
        )

    transaction_id = None

    if is_transaction_event:
        transaction_id = data.get(
            "id"
        )

    customer_id = data.get(
        "customer_id"
    )

    custom_data = (
        data.get("custom_data")
        or {}
    )

    organization_id_raw = (
        custom_data.get(
            "organization_id"
        )
    )

    # ========================================================
    # BUSCAR ORGANIZACIÓN
    #
    # Prioridad:
    # 1. custom_data.organization_id
    # 2. subscription_id conocido
    # 3. customer_id conocido
    # ========================================================

    organization = None

    if organization_id_raw:
        try:
            organization_id = int(
                organization_id_raw
            )
        except (
            TypeError,
            ValueError,
        ):
            organization_id = None

        if organization_id is not None:
            organization = (
                db.query(Organization)
                .filter(
                    Organization.id
                    == organization_id
                )
                .first()
            )

    if (
        organization is None
        and subscription_id
    ):
        organization = (
            db.query(Organization)
            .filter(
                Organization.billing_subscription_id
                == subscription_id
            )
            .first()
        )

    if (
        organization is None
        and customer_id
    ):
        organization = (
            db.query(Organization)
            .filter(
                Organization.billing_customer_id
                == customer_id
            )
            .first()
        )

    if organization is None:
        return {
            "ok": True,
            "ignored": True,
            "reason":
                "organization_not_found",
            "event_type":
                event_type,
        }

    # ========================================================
    # PROTEGER SUSCRIPCION CANONICA
    # ========================================================
    #
    # Una organización solo puede tener una suscripción
    # administrada por DIAGLOB.
    #
    # Si llega un webhook de otra suscripción, por ejemplo
    # una suscripción duplicada creada accidentalmente,
    # no debe modificar plan, estado ni tiendas.
    # ========================================================

    if (
        subscription_id
        and organization.billing_subscription_id
        and subscription_id
        != organization.billing_subscription_id
    ):
        return {
            "ok": True,
            "ignored": True,
            "reason":
                "non_canonical_subscription",
            "event_type":
                event_type,
            "organization_id":
                organization.id,
            "subscription_id":
                subscription_id,
            "canonical_subscription_id":
                organization.billing_subscription_id,
        }

    # ========================================================
    # IDEMPOTENCIA
    # ========================================================

    if (
        organization.billing_last_event_id
        == event_id
    ):
        return {
            "ok": True,
            "duplicate": True,
            "event_type": event_type,
        }

    # ========================================================
    # FECHA DEL EVENTO
    # ========================================================

    occurred_at = None

    if occurred_at_raw:
        try:
            occurred_at = (
                datetime.fromisoformat(
                    occurred_at_raw.replace(
                        "Z",
                        "+00:00",
                    )
                )
                .replace(
                    tzinfo=None
                )
            )
        except ValueError:
            occurred_at = None

    if (
        occurred_at is not None
        and organization.billing_last_event_at
        is not None
        and occurred_at
        < organization.billing_last_event_at
    ):
        return {
            "ok": True,
            "ignored": True,
            "reason":
                "out_of_order_event",
            "event_type":
                event_type,
        }

    # ========================================================
    # PRECIO Y PLAN
    #
    # La estructura items[].price.id funciona tanto para
    # subscriptions como para transactions de Paddle.
    # ========================================================

    price_id = (
        get_subscription_price_id(
            data
        )
    )

    plan_key = None
    billing_period_months = None

    if price_id:
        plan_key = (
            get_plan_from_price_id(
                price_id
            )
        )

        billing_period_months = (
            get_billing_period_from_price_id(
                price_id
            )
        )

    # ========================================================
    # DATOS COMUNES DE BILLING
    # ========================================================

    organization.billing_provider = (
        "paddle"
    )

    if customer_id:
        organization.billing_customer_id = (
            customer_id
        )

    if subscription_id:
        organization.billing_subscription_id = (
            subscription_id
        )

    if price_id:
        organization.billing_price_id = (
            price_id
        )

    if (
        billing_period_months is not None
        and not organization.pending_plan
    ):
        organization.billing_period_months = (
            billing_period_months
        )

    # ========================================================
    # TRANSACTION.COMPLETED
    #
    # Vincula el pago real con la organización.
    #
    # IMPORTANTE:
    # NO modifica subscription_status.
    # Los eventos subscription.* son la autoridad del estado.
    # Tampoco activa/suspende tiendas.
    # ========================================================

    if is_transaction_event:

        if (
            organization.pending_plan
            and organization.pending_plan_effective_at
            and occurred_at is not None
            and occurred_at
            >= organization.pending_plan_effective_at
        ):
            target_plan = (
                organization.pending_plan
            )

            target_period = int(
                organization.pending_billing_period_months
                or organization.billing_period_months
                or 1
            )

            current_rank = (
                BILLING_PLAN_ORDER.get(
                    organization.plan,
                    0,
                )
            )

            target_rank = (
                BILLING_PLAN_ORDER.get(
                    target_plan,
                    0,
                )
            )

            is_plan_downgrade = (
                target_rank
                < current_rank
            )

            target_limit = int(
                get_limits_for_plan(
                    target_plan
                ).active_stores
            )

            # ====================================================
            # TIENDAS ELEGIDAS POR EL CLIENTE
            # ====================================================
            #
            # Pueden estar activas o suspendidas.
            #
            # Una tienda suspendida seleccionada se activará
            # cuando entre en vigencia el nuevo plan.
            #
            # Las eliminadas no son válidas.
            # ====================================================

            selected_all = (
                db.query(Store)
                .filter(
                    Store.organization_id
                    == organization.id,
                    Store.keep_on_pending_downgrade.is_(True),
                )
                .order_by(Store.id.asc())
                .all()
            )

            intended_selection_count = min(
                len(selected_all),
                target_limit,
            )

            selected_valid = [
                store
                for store in selected_all
                if not store.deleted
            ]

            selected_valid = (
                selected_valid[
                    :target_limit
                ]
            )

            keep_ids = {
                store.id
                for store in selected_valid
            }

            if not is_plan_downgrade:
                # En un cambio de período o upgrade programado
                # no modificamos el estado de las tiendas.
                keep_ids = {
                    store.id
                    for store in (
                        db.query(Store)
                        .filter(
                            Store.organization_id
                            == organization.id,
                            Store.deleted.is_(False),
                            Store.active.is_(True),
                        )
                        .all()
                    )
                }

                intended_selection_count = (
                    len(keep_ids)
                )

                selected_valid = []

            # ====================================================
            # FALLBACK
            # ====================================================
            #
            # Solo completamos cupos si una tienda que el cliente
            # había seleccionado fue eliminada.
            #
            # Si el cliente eligió voluntariamente menos tiendas
            # que el máximo del plan, respetamos esa decisión.
            #
            # El fallback usa únicamente tiendas que YA estén
            # activas, priorizando las que llevan más tiempo
            # activas.
            #
            # Nunca reactivamos una suspendida que no fue elegida.
            # ====================================================

            missing_selected = max(
                0,
                intended_selection_count
                - len(selected_valid),
            )

            if missing_selected > 0:
                fallback_stores = (
                    db.query(Store)
                    .filter(
                        Store.organization_id
                        == organization.id,
                        Store.deleted.is_(False),
                        Store.active.is_(True),
                        Store.id.notin_(keep_ids)
                        if keep_ids
                        else True,
                    )
                    .order_by(
                        Store.active_since.is_(None),
                        Store.active_since.asc(),
                        Store.id.asc(),
                    )
                    .limit(
                        missing_selected
                    )
                    .all()
                )

                for store in fallback_stores:
                    keep_ids.add(
                        store.id
                    )

            # ====================================================
            # APLICAR ESTADO FINAL
            # ====================================================

            stores = (
                db.query(Store)
                .filter(
                    Store.organization_id
                    == organization.id,
                    Store.deleted.is_(False),
                )
                .all()
            )

            for store in stores:
                should_be_active = (
                    store.id in keep_ids
                )

                if store.active != should_be_active:
                    store.active = (
                        should_be_active
                    )

            # Limpiar selección temporal.
            for store in selected_all:
                store.keep_on_pending_downgrade = False

            organization.plan = (
                target_plan
            )

            organization.billing_period_months = (
                target_period
            )

            organization.pending_plan = None
            organization.pending_billing_period_months = None
            organization.pending_plan_effective_at = None
            organization.pending_plan_prepared_at = None

        elif (
            plan_key
            and not organization.pending_plan
        ):
            organization.plan = (
                plan_key
            )

        organization.billing_last_event_id = (
            event_id
        )

        if occurred_at is not None:
            organization.billing_last_event_at = (
                occurred_at
            )

        db.commit()

        return {
            "ok": True,
            "event_type":
                event_type,
            "organization_id":
                organization.id,
            "transaction_id":
                transaction_id,
            "customer_id":
                organization.billing_customer_id,
            "subscription_id":
                organization.billing_subscription_id,
            "price_id":
                organization.billing_price_id,
            "plan":
                organization.plan,
            "subscription_status":
                organization.subscription_status,
        }

    # ========================================================
    # SUBSCRIPTION EVENTS
    # ========================================================

    status = data.get(
        "status"
    )

    if status:
        organization.subscription_status = (
            status
        )

    # Paddle es también la autoridad sobre
    # la renovación automática.
    if is_subscription_event:
        scheduled_change = (
            data.get("scheduled_change")
        )

        scheduled_action = (
            scheduled_change.get("action")
            if isinstance(
                scheduled_change,
                dict,
            )
            else None
        )

        if status == "canceled":
            organization.auto_renew_enabled = False

        elif scheduled_action == "cancel":
            organization.auto_renew_enabled = False

        elif status in {
            "active",
            "trialing",
        }:
            organization.auto_renew_enabled = True

    # Solo cambiamos el plan desde subscription.*
    # cuando Paddle nos entrega un Price ID reconocido
    # y la suscripción está en un estado válido.
    if (
        plan_key
        and status in {
            "active",
            "trialing",
            "past_due",
        }
    ):
        current_rank = (
            BILLING_PLAN_ORDER.get(
                organization.plan,
                0,
            )
        )

        incoming_rank = (
            BILLING_PLAN_ORDER.get(
                plan_key,
                0,
            )
        )

        pending_plan = (
            organization.pending_plan
        )

        pending_rank = (
            BILLING_PLAN_ORDER.get(
                pending_plan,
                0,
            )
            if pending_plan
            else 0
        )

        has_pending_change = bool(
            pending_plan
            and organization.pending_plan_effective_at
        )

        incoming_is_current_plan = (
            plan_key
            == organization.plan
        )

        incoming_is_pending_target = (
            has_pending_change
            and plan_key
            == pending_plan
        )

        # Mientras existe un cambio programado:
        #
        # Paddle puede notificar tanto el Price actual como el
        # Price futuro preparado por el worker.
        #
        # El plan/período de DIAGLOB no cambia hasta recibir
        # transaction.completed en la fecha efectiva.
        if (
            has_pending_change
            and (
                incoming_is_current_plan
                or incoming_is_pending_target
            )
        ):
            pass

        else:
            # Un plan superior representa un upgrade real.
            # También permite sincronizar cambios normales
            # cuando no existe un downgrade pendiente.
            organization.plan = (
                plan_key
            )

            organization.pending_plan = None
            organization.pending_billing_period_months = None
            organization.pending_plan_effective_at = None
            organization.pending_plan_prepared_at = None

            (
                db.query(Store)
                .filter(
                    Store.organization_id
                    == organization.id,
                )
                .update(
                    {
                        Store.keep_on_pending_downgrade:
                            False,
                    },
                    synchronize_session=False,
                )
            )

    # ========================================================
    # CANCELACIÓN / PAUSA
    #
    # No borramos datos.
    # Suspendemos las tiendas activas.
    # ========================================================

    if status in {
        "canceled",
        "paused",
    }:
        (
            db.query(Store)
            .filter(
                Store.organization_id
                == organization.id,
                Store.deleted.is_(False),
                Store.active.is_(True),
            )
            .update(
                {
                    Store.active: False,
                    Store.active_since: None,
                },
                synchronize_session=False,
            )
        )

    # Si la suscripción terminó realmente,
    # la organización queda sin plan contratado.
    if status == "canceled":
        organization.plan = "none"

    organization.billing_last_event_id = (
        event_id
    )

    if occurred_at is not None:
        organization.billing_last_event_at = (
            occurred_at
        )

    db.commit()

    return {
        "ok": True,
        "event_type":
            event_type,
        "organization_id":
            organization.id,
        "subscription_status":
            organization.subscription_status,
        "plan":
            organization.plan,
    }


@router.patch("/api/billing/auto-renew")
def update_billing_auto_renew(
    payload: BillingAutoRenewRequest,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Billing access denied",
        )

    organization = membership.organization

    subscription_id = (
        organization.billing_subscription_id
    )

    if not subscription_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "La organización no tiene una "
                "suscripción Paddle asociada."
            ),
        )

    status = (
        organization.subscription_status
        or ""
    ).strip().lower()

    if status not in {
        "active",
        "trialing",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "La renovación automática solo puede "
                "modificarse mientras la suscripción "
                "está activa."
            ),
        )

    subscription_url = (
        f"{get_paddle_base_url()}"
        f"/subscriptions/{subscription_id}"
    )

    # --------------------------------------------------------
    # CONSULTAR ESTADO ACTUAL EN PADDLE
    # --------------------------------------------------------

    try:
        response = httpx.get(
            subscription_url,
            headers=get_paddle_headers(),
            timeout=30,
        )

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No fue posible consultar Paddle."
            ),
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "Paddle rechazó la consulta "
                    "de la suscripción.",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            },
        )

    paddle_subscription = (
        response.json().get("data")
        or {}
    )

    scheduled_change = (
        paddle_subscription.get(
            "scheduled_change"
        )
    )

    scheduled_action = (
        scheduled_change.get("action")
        if isinstance(
            scheduled_change,
            dict,
        )
        else None
    )

    # ========================================================
    # ACTIVAR RENOVACIÓN
    # ========================================================

    if payload.enabled:

        # Ya está renovando normalmente.
        if scheduled_action is None:
            organization.auto_renew_enabled = True

            db.commit()

            return {
                "ok": True,
                "auto_renew_enabled": True,
                "scheduled_change": None,
                "message":
                    "La renovación automática ya está activa.",
            }

        # No debemos borrar silenciosamente un pause u otro
        # cambio que no haya sido creado por este control.
        if scheduled_action != "cancel":
            raise HTTPException(
                status_code=409,
                detail=(
                    "La suscripción tiene otro cambio "
                    "programado en Paddle y no puede "
                    "reactivarse automáticamente."
                ),
            )

        try:
            response = httpx.patch(
                subscription_url,
                headers=get_paddle_headers(),
                json={
                    "scheduled_change": None,
                },
                timeout=30,
            )

        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "No fue posible reactivar "
                    "la renovación en Paddle."
                ),
            ) from exc

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "message":
                        "Paddle rechazó la reactivación "
                        "de la renovación.",
                    "paddle_status":
                        response.status_code,
                    "paddle_response":
                        response.text,
                },
            )

        paddle_data = (
            response.json().get("data")
            or {}
        )

        organization.auto_renew_enabled = True

        db.commit()

        return {
            "ok": True,
            "auto_renew_enabled": True,
            "scheduled_change":
                paddle_data.get(
                    "scheduled_change"
                ),
            "next_billed_at":
                paddle_data.get(
                    "next_billed_at"
                ),
            "message":
                "Renovación automática activada.",
        }

    # ========================================================
    # DESACTIVAR RENOVACIÓN
    # ========================================================

    if scheduled_action == "cancel":

        organization.auto_renew_enabled = False

        db.commit()

        return {
            "ok": True,
            "auto_renew_enabled": False,
            "scheduled_change":
                scheduled_change,
            "effective_at":
                scheduled_change.get(
                    "effective_at"
                ),
            "message":
                "La renovación ya estaba desactivada.",
        }

    if scheduled_action is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "La suscripción ya tiene otro "
                "cambio programado en Paddle."
            ),
        )

    cancel_url = (
        f"{subscription_url}/cancel"
    )

    try:
        response = httpx.post(
            cancel_url,
            headers=get_paddle_headers(),
            json={
                "effective_from":
                    "next_billing_period",
            },
            timeout=30,
        )

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No fue posible programar "
                "la cancelación en Paddle."
            ),
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "Paddle rechazó la cancelación "
                    "programada.",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            },
        )

    paddle_data = (
        response.json().get("data")
        or {}
    )

    scheduled_change = (
        paddle_data.get(
            "scheduled_change"
        )
        or {}
    )

    # Una cancelación futura hace irrelevante
    # cualquier downgrade interno pendiente.
    organization.pending_plan = None
    organization.pending_billing_period_months = None
    organization.pending_plan_effective_at = None
    organization.pending_plan_prepared_at = None

    (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
        )
        .update(
            {
                Store.keep_on_pending_downgrade:
                    False,
            },
            synchronize_session=False,
        )
    )

    organization.auto_renew_enabled = False

    db.commit()

    return {
        "ok": True,
        "auto_renew_enabled": False,
        "scheduled_change":
            paddle_data.get(
                "scheduled_change"
            ),
        "effective_at":
            scheduled_change.get(
                "effective_at"
            ),
        "next_billed_at":
            paddle_data.get(
                "next_billed_at"
            ),
        "message":
            "Renovación automática desactivada.",
    }


@router.post("/api/billing/upgrade/preview")
def preview_billing_upgrade(
    payload: BillingUpgradeRequest,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Billing access denied",
        )

    organization = (
        db.query(Organization)
        .filter(
            Organization.id
            == membership.organization_id
        )
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=404,
            detail="Organization not found",
        )

    try:
        (
            current_plan,
            target_plan,
        ) = validate_plan_upgrade(
            organization,
            payload.plan,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    import logging as _log
    logger = _log.getLogger(__name__)
    logger.info(
        "billing.preview org=%s current=%s target=%s",
        organization.id,
        current_plan,
        target_plan,
    )

    if (
        organization.subscription_status
        and organization.subscription_status
        not in {"active", "trialing"}
    ):
        logger.warning(
            "billing.preview.rejected org=%s reason=subscription_not_active status=%s",
            organization.id,
            organization.subscription_status,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                "La suscripcion debe estar activa "
                "para realizar un upgrade."
            ),
        )

    paddle_api_key = os.getenv("PADDLE_API_KEY")

    if (
        paddle_api_key
        and organization.billing_subscription_id
    ):
        try:
            target_price_id = get_paddle_price_id(
                target_plan,
                organization.billing_period_months,
            )
        except ValueError:
            _log.getLogger(__name__).warning(
                "billing.preview paddle_price_unavailable org=%s plan=%s period=%s",
                organization.id,
                target_plan,
                organization.billing_period_months,
            )
            target_price_id = None

        if target_price_id:
            body = {
                "items": [
                    {
                        "price_id": target_price_id,
                        "quantity": 1,
                    }
                ],
                "proration_billing_mode":
                    "prorated_immediately",
                "on_payment_failure":
                    "prevent_change",
            }

            try:
                response = httpx.patch(
                    (
                        f"{get_paddle_base_url()}"
                        f"/subscriptions/"
                        f"{organization.billing_subscription_id}"
                        f"/preview"
                    ),
                    headers=get_paddle_headers(),
                    json=body,
                    timeout=30,
                )
            except httpx.RequestError:
                response = None

            if response is not None and response.status_code < 400:
                paddle_data = (
                    response.json().get("data")
                    or {}
                )

                immediate_transaction = (
                    paddle_data.get(
                        "immediate_transaction"
                    )
                    or {}
                )

                details = (
                    immediate_transaction.get("details")
                    or {}
                )

                totals = (
                    details.get("totals")
                    or {}
                )

                line_items = (
                    details.get("line_items")
                    or []
                )

                charge_amount = 0
                credit_amount = 0

                for line_item in line_items:
                    line_totals = (
                        line_item.get("totals")
                        or {}
                    )

                    try:
                        line_total = int(
                            line_totals.get("total")
                            or 0
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        line_total = 0

                    if line_total > 0:
                        charge_amount += line_total

                    elif line_total < 0:
                        credit_amount += abs(
                            line_total
                        )

                try:
                    result_amount = int(
                        totals.get("total")
                        or 0
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    result_amount = 0

                currency_code = (
                    totals.get("currency_code")
                    or "USD"
                )

                if result_amount > 0:
                    result_action = "charge"

                elif result_amount < 0:
                    result_action = "credit"

                else:
                    result_action = "none"

                normalized_update_summary = {
                    "charge": {
                        "amount": str(
                            charge_amount
                        ),
                        "currency_code":
                            currency_code,
                    },
                    "credit": {
                        "amount": str(
                            credit_amount
                        ),
                        "currency_code":
                            currency_code,
                    },
                    "result": {
                        "action":
                            result_action,
                        "amount": str(
                            abs(result_amount)
                        ),
                        "currency_code":
                            currency_code,
                    },
                }

                next_transaction = (
                    paddle_data.get(
                        "next_transaction"
                    )
                    or {}
                )

                next_billing_period = (
                    next_transaction.get(
                        "billing_period"
                    )
                    or {}
                )

                return {
                    "current_plan": current_plan,
                    "target_plan": target_plan,
                    "subscription_id":
                        organization.billing_subscription_id,
                    "next_billed_at":
                        (
                            paddle_data.get(
                                "next_billed_at"
                            )
                            or next_billing_period.get(
                                "starts_at"
                            )
                        ),
                    "currency_code":
                        currency_code,
                    "amount_due":
                        str(result_amount),
                    "subtotal":
                        totals.get("subtotal"),
                    "tax":
                        totals.get("tax"),
                    "update_summary":
                        normalized_update_summary,
                    "immediate_transaction":
                        immediate_transaction,
                    "next_transaction":
                        paddle_data.get(
                            "next_transaction"
                        ),
                }

    # ============================================================
    # FALLBACK: LOCAL PRORATION CALCULATION
    # ============================================================
    # Used when:
    #   - Paddle API key not configured
    #   - No billing subscription yet
    #   - Paddle API unreachable
    # ============================================================

    from datetime import timedelta

    billing_period = (
        organization.billing_period_months or 1
    )

    now = datetime.utcnow()

    period_end = (
        now + timedelta(days=30 * billing_period)
    )

    period_start = (
        now - timedelta(days=30 * billing_period)
    )

    local_preview = calculate_local_proration(
        current_plan=current_plan,
        target_plan=target_plan,
        billing_period_months=billing_period,
        current_period_start=period_start,
        current_period_end=period_end,
        now=now,
    )

    amount_cents = int(
        float(local_preview["amount_due_now"]) * 100
    )

    credit_cents = int(
        float(local_preview["credit"]) * 100
    )

    charge_cents = int(
        float(local_preview["charge"]) * 100
    )

    return {
        "current_plan": current_plan,
        "target_plan": target_plan,
        "subscription_id":
            organization.billing_subscription_id,
        "next_billed_at":
            local_preview["next_billed_at"],
        "currency_code":
            local_preview["currency"],
        "amount_due":
            str(amount_cents),
        "subtotal": None,
        "tax": None,
        "update_summary": {
            "charge": {
                "amount": str(charge_cents),
                "currency_code":
                    local_preview["currency"],
            },
            "credit": {
                "amount": str(credit_cents),
                "currency_code":
                    local_preview["currency"],
            },
            "result": {
                "action": (
                    "charge"
                    if amount_cents > 0
                    else "none"
                ),
                "amount": str(abs(amount_cents)),
                "currency_code":
                    local_preview["currency"],
            },
        },
        "immediate_transaction": None,
        "next_transaction": None,
        "_source": "local",
    }


@router.post("/api/billing/upgrade")
def apply_billing_upgrade(
    payload: BillingUpgradeRequest,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Billing access denied",
        )

    organization = (
        db.query(Organization)
        .filter(
            Organization.id
            == membership.organization_id
        )
        .first()
    )

    if not organization:
        raise HTTPException(
            status_code=404,
            detail="Organization not found",
        )

    (
        current_plan,
        target_plan,
    ) = validate_plan_upgrade(
        organization,
        payload.plan,
    )

    target_price_id = get_paddle_price_id(
        target_plan,
        organization.billing_period_months,
    )

    body = {
        "items": [
            {
                "price_id": target_price_id,
                "quantity": 1,
            }
        ],
        "proration_billing_mode":
            "prorated_immediately",
        "on_payment_failure":
            "prevent_change",
        "custom_data": {
            "organization_id":
                str(organization.id),
            "plan":
                target_plan,
        },
    }

    try:
        response = httpx.patch(
            (
                f"{get_paddle_base_url()}"
                f"/subscriptions/"
                f"{organization.billing_subscription_id}"
            ),
            headers=get_paddle_headers(),
            json=body,
            timeout=45,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to contact Paddle",
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "Unable to upgrade Paddle subscription",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            },
        )

    paddle_data = (
        response.json().get("data")
        or {}
    )

    # Paddle confirmó el upgrade.
    #
    # Sincronizamos DIAGLOB inmediatamente para que la UI
    # no dependa de que el webhook llegue en ese instante.
    #
    # Los webhooks siguen siendo autoridad para eventos
    # posteriores y cambios externos.

    paddle_price_id = (
        get_subscription_price_id(
            paddle_data
        )
        or target_price_id
    )

    confirmed_plan = (
        get_plan_from_price_id(
            paddle_price_id
        )
        if paddle_price_id
        else None
    )

    organization.plan = (
        confirmed_plan
        or target_plan
    )

    organization.billing_price_id = (
        paddle_price_id
    )

    confirmed_period = (
        get_billing_period_from_price_id(
            paddle_price_id
        )
        if paddle_price_id
        else None
    )

    if confirmed_period is not None:
        organization.billing_period_months = (
            confirmed_period
        )

    organization.pending_plan = None
    organization.pending_billing_period_months = None
    organization.pending_plan_effective_at = None
    organization.pending_plan_prepared_at = None

    (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
        )
        .update(
            {
                Store.keep_on_pending_downgrade:
                    False,
            },
            synchronize_session=False,
        )
    )

    db.commit()
    db.refresh(organization)

    return {
        "ok": True,
        "current_plan": current_plan,
        "target_plan": target_plan,
        "subscription_id":
            organization.billing_subscription_id,
        "paddle_status":
            paddle_data.get("status"),
        "next_billed_at":
            paddle_data.get("next_billed_at"),
        "message":
            "Upgrade enviado a Paddle",
    }


@router.post("/api/billing/downgrade/preview")
def preview_billing_downgrade(
    payload: BillingDowngradeRequest,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Billing access denied",
        )

    organization = (
        membership.organization
    )

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

    (
        current_plan,
        target_plan,
        current_period,
        target_period,
    ) = validate_plan_downgrade(
        organization,
        payload.plan,
        db,
        payload.billing_period_months,
    )

    price_id = (
        get_billing_price_id(
            target_plan,
            target_period,
        )
    )

    # ========================================================
    # PREVIEW SEGÚN TIPO DE CAMBIO
    # ========================================================
    #
    # Si cambia la duración:
    #
    #   1M -> 3M
    #   1M -> 6M
    #   3M -> 12M
    #
    # NO simulamos todavía el Price nuevo en Paddle.
    #
    # El cliente conserva exactamente su período actual hasta
    # current_billing_period.ends_at.
    #
    # DIAGLOB guardará el cambio como pendiente y el worker
    # actualizará Paddle cerca de esa renovación.
    #
    # Si la duración NO cambia, este endpoint corresponde a un
    # downgrade real de plan y conservamos el preview existente.
    # ========================================================

    is_period_change = (
        target_period
        != current_period
    )

    if is_period_change:
        url = (
            f"{get_paddle_base_url()}"
            f"/subscriptions/"
            f"{organization.billing_subscription_id}"
        )

        try:
            response = httpx.get(
                url,
                headers=get_paddle_headers(),
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "No fue posible consultar Paddle: "
                    f"{exc}"
                ),
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "message":
                        "Paddle rechazó la consulta de la suscripción",
                    "paddle_status":
                        response.status_code,
                    "paddle_response":
                        response.text,
                },
            )

        subscription_data = (
            response.json().get("data")
            or {}
        )

        current_billing_period = (
            subscription_data.get(
                "current_billing_period"
            )
            or {}
        )

        effective_at = (
            current_billing_period.get(
                "ends_at"
            )
        )

        if not effective_at:
            effective_at = (
                subscription_data.get(
                    "next_billed_at"
                )
            )

        if not effective_at:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Paddle no devolvió la fecha de fin "
                    "del período actual"
                ),
            )

        paddle_data = {
            "next_billed_at":
                effective_at,
            "immediate_transaction":
                None,
            "next_transaction":
                None,
        }

    else:
        url = (
            f"{get_paddle_base_url()}"
            f"/subscriptions/"
            f"{organization.billing_subscription_id}"
            f"/preview"
        )

        body = {
            "items": [
                {
                    "price_id":
                        price_id,
                    "quantity":
                        1,
                }
            ],
            "proration_billing_mode":
                "do_not_bill",
            "on_payment_failure":
                "prevent_change",
        }

        try:
            response = httpx.patch(
                url,
                headers=get_paddle_headers(),
                json=body,
                timeout=30,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=(
                    "No fue posible consultar Paddle: "
                    f"{exc}"
                ),
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "message":
                        "Paddle rechazó el preview del downgrade",
                    "paddle_status":
                        response.status_code,
                    "paddle_response":
                        response.text,
                },
            )

        paddle_data = (
            response.json().get("data")
            or {}
        )

    available_stores = (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
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

    target_store_limit = int(
        get_limits_for_plan(
            target_plan
        ).active_stores
    )

    return {
        "ok": True,

        "target_store_limit":
            target_store_limit,

        "requires_store_selection":
            bool(
                available_stores
                and (
                    BILLING_PLAN_ORDER.get(
                        target_plan,
                        0,
                    )
                    <
                    BILLING_PLAN_ORDER.get(
                        current_plan,
                        0,
                    )
                )
            ),

        "available_stores": [
            {
                "id":
                    store.id,
                "name":
                    store.name,
                "active":
                    bool(store.active),
                "active_since":
                    (
                        store.active_since.isoformat()
                        + "Z"
                        if store.active_since
                        else None
                    ),
            }
            for store in available_stores
        ],
        "current_plan":
            current_plan,
        "target_plan":
            target_plan,
        "current_billing_period_months":
            current_period,
        "target_billing_period_months":
            target_period,
        "subscription_id":
            organization.billing_subscription_id,
        "effective_at":
            paddle_data.get(
                "next_billed_at"
            ),
        "next_billed_at":
            paddle_data.get(
                "next_billed_at"
            ),
        "immediate_transaction":
            paddle_data.get(
                "immediate_transaction"
            ),
        "next_transaction":
            paddle_data.get(
                "next_transaction"
            ),
    }


@router.post("/api/billing/downgrade")
def apply_billing_downgrade(
    payload: BillingDowngradeRequest,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Billing access denied",
        )

    organization = (
        membership.organization
    )

    (
        current_plan,
        target_plan,
        current_period,
        target_period,
    ) = validate_plan_downgrade(
        organization,
        payload.plan,
        db,
        payload.billing_period_months,
    )

    subscription_id = (
        organization.billing_subscription_id
    )

    # ========================================================
    # CONFIGURAR TIENDAS DEL PLAN FUTURO
    # ========================================================

    is_plan_downgrade = (
        BILLING_PLAN_ORDER.get(
            target_plan,
            0,
        )
        <
        BILLING_PLAN_ORDER.get(
            current_plan,
            0,
        )
    )

    if is_plan_downgrade:
        selection = (
            configure_pending_downgrade_stores(
                db,
                organization,
                target_plan,
                payload.store_ids,
            )
        )
    else:
        # Cambio de período o upgrade + cambio de período:
        # las tiendas actuales permanecen intactas.
        (
            db.query(Store)
            .filter(
                Store.organization_id
                == organization.id,
            )
            .update(
                {
                    Store.keep_on_pending_downgrade:
                        False,
                },
                synchronize_session=False,
            )
        )

        selection = {
            "target_store_limit":
                int(
                    get_limits_for_plan(
                        target_plan
                    ).active_stores
                ),
            "selected_store_ids":
                [],
        }

    # ========================================================
    # CONSULTAR FECHA REAL DE RENOVACION EN PADDLE
    # ========================================================
    #
    # IMPORTANTE:
    # NO cambiamos el Price ID todavía.
    #
    # Paddle debe seguir viendo el plan ACTUAL durante todo
    # el período ya pagado para que:
    #
    # - los upgrades se calculen contra el plan actual;
    # - no alteremos la renovación antes de tiempo;
    # - el cliente conserve correctamente su servicio.
    # ========================================================

    get_url = (
        f"{get_paddle_base_url()}"
        f"/subscriptions/"
        f"{subscription_id}"
    )

    try:
        response = httpx.get(
            get_url,
            headers=get_paddle_headers(),
            timeout=30,
        )

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No fue posible consultar Paddle: "
                f"{exc}"
            ),
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "No fue posible consultar la suscripción",
                "paddle_status":
                    response.status_code,
                "paddle_response":
                    response.text,
            },
        )

    paddle_data = (
        response.json().get("data")
        or {}
    )

    next_billed_at_raw = (
        paddle_data.get(
            "next_billed_at"
        )
    )

    if not next_billed_at_raw:
        raise HTTPException(
            status_code=409,
            detail=(
                "Paddle no informó la próxima "
                "fecha de renovación"
            ),
        )

    try:
        effective_at = (
            datetime.fromisoformat(
                next_billed_at_raw.replace(
                    "Z",
                    "+00:00",
                )
            )
            .replace(
                tzinfo=None
            )
        )

    except ValueError:
        raise HTTPException(
            status_code=502,
            detail=(
                "Paddle devolvió una fecha "
                "de renovación inválida"
            ),
        )

    # ========================================================
    # GUARDAR DOWNGRADE SOLO EN DIAGLOB
    # ========================================================

    organization.pending_plan = (
        target_plan
    )

    organization.pending_billing_period_months = (
        target_period
    )

    organization.pending_plan_effective_at = (
        effective_at
    )

    organization.pending_plan_prepared_at = None

    db.commit()

    db.refresh(organization)

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

    return {
        "ok": True,

        "current_plan":
            current_plan,

        "pending_plan":
            target_plan,

        "pending_billing_period_months":
            target_period,

        "effective_at":
            next_billed_at_raw,

        "subscription_id":
            subscription_id,

        "selected_store_ids":
            selection.get(
                "selected_store_ids",
                [],
            ),

        "target_store_limit":
            selection.get(
                "target_store_limit",
            ),

        "paddle_status":
            paddle_data.get(
                "status"
            ),

        "message":
            (
                "Downgrade programado. "
                "Paddle conservará el plan actual "
                "hasta el procesamiento de la renovación."
            ),
    }


@router.delete("/api/billing/downgrade")
def cancel_billing_downgrade(
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
    db: Session = Depends(get_db),
):
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Billing access denied",
        )

    organization = (
        membership.organization
    )

    if not organization.pending_plan:
        return {
            "ok": True,
            "pending_plan": None,
        }

    # Paddle nunca fue modificado al programar el downgrade,
    # por lo tanto cancelar solo limpia el estado pendiente
    # dentro de DIAGLOB.

    organization.pending_plan = None
    organization.pending_billing_period_months = None
    organization.pending_plan_effective_at = None
    organization.pending_plan_prepared_at = None

    (
        db.query(Store)
        .filter(
            Store.organization_id
            == organization.id,
        )
        .update(
            {
                Store.keep_on_pending_downgrade:
                    False,
            },
            synchronize_session=False,
        )
    )

    db.commit()

    return {
        "ok": True,
        "pending_plan": None,
        "message":
            "Cambio de plan programado cancelado",
    }


@router.post("/api/internal/billing/process-downgrades")
def process_downgrades_internal(
    x_internal_secret: str | None = Header(
        None,
        alias="X-Internal-Secret",
    ),
    db: Session = Depends(get_db),
):
    expected_secret = (
        os.getenv(
            "DIAGLOB_INTERNAL_SECRET"
        )
    )

    if (
        not expected_secret
        or not x_internal_secret
        or not secrets.compare_digest(
            x_internal_secret,
            expected_secret,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized internal request",
        )

    results = (
        process_pending_downgrades(
            db
        )
    )

    return {
        "ok": True,
        "processed":
            len(results),
        "results":
            results,
    }


@router.post("/api/billing/checkout")
def create_billing_checkout(
    payload: BillingCheckoutRequest,
    membership: OrganizationMembership = Depends(
        get_current_membership
    ),
):
    # El checkout debe estar disponible aunque
    # la organización todavía no tenga plan.
    #
    # Solo roles administrativos pueden contratar
    # o cambiar una suscripción.
    if membership.role not in {
        "owner",
        "manager",
    }:
        raise HTTPException(
            status_code=403,
            detail="Billing access denied",
        )

    organization = membership.organization

    if (
        organization.billing_subscription_id
        and organization.subscription_status
        in {
            "active",
            "trialing",
            "past_due",
        }
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "La organización ya tiene una suscripción activa. "
                "Usa upgrade o downgrade en lugar de crear "
                "un checkout nuevo."
            ),
        )

    plan_key = (
        payload.plan
        .strip()
        .lower()
    )

    if plan_key not in {
        "starter",
        "growth",
        "pro",
        "scale",
    }:
        raise HTTPException(
            status_code=400,
            detail="Plan inválido",
        )

    try:
        price_id = get_paddle_price_id(
            plan_key,
            payload.billing_period_months,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    api_key = os.getenv(
        "PADDLE_API_KEY"
    )

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Paddle no está configurado"
            ),
        )

    organization = (
        membership.organization
    )

    body = {
        "items": [
            {
                "price_id": price_id,
                "quantity": 1,
            }
        ],
        "collection_mode":
            "automatic",
        "custom_data": {
            "organization_id":
                str(organization.id),
            "plan":
                plan_key,
            "billing_period_months":
                payload.billing_period_months,
        },
    }

    headers = {
        "Authorization":
            f"Bearer {api_key}",
        "Content-Type":
            "application/json",
    }

    environment = (
        os.getenv(
            "PADDLE_ENVIRONMENT",
            "sandbox",
        )
        .strip()
        .lower()
    )

    if environment == "production":
        base_url = (
            "https://api.paddle.com"
        )
    else:
        base_url = (
            "https://sandbox-api.paddle.com"
        )

    try:
        response = httpx.post(
            f"{base_url}/transactions",
            headers=headers,
            json=body,
            timeout=20,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "No fue posible conectar "
                "con Paddle"
            ),
        ) from exc

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message":
                    "Paddle rechazó "
                    "la transacción",
                "provider_response":
                    response.json(),
            },
        )

    data = response.json().get(
        "data",
        {}
    )

    checkout = (
        data.get("checkout")
        or {}
    )

    checkout_url = checkout.get(
        "url"
    )

    if not checkout_url:
        raise HTTPException(
            status_code=502,
            detail=(
                "Paddle no devolvió "
                "una URL de checkout"
            ),
        )

    return {
        "plan":
            plan_key,
        "transaction_id":
            data.get("id"),
        "checkout_url":
            checkout_url,
    }
