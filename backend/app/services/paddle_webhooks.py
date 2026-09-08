"""Paddle webhook event orchestration / state machine.

Handles organization resolution, idempotency, subscription state transitions,
transaction processing, and store deactivation.
Does NOT import FastAPI or httpx.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..billing import (
    get_billing_period_from_price_id,
    get_plan_from_price_id,
    get_subscription_price_id,
)
from ..models import Organization, Store

logger = logging.getLogger(__name__)

BILLING_PLAN_ORDER = {
    "starter": 1,
    "growth": 2,
    "pro": 3,
    "scale": 4,
}

SUBSCRIPTION_EVENTS = {
    "subscription.created",
    "subscription.activated",
    "subscription.updated",
    "subscription.past_due",
    "subscription.paused",
    "subscription.resumed",
    "subscription.canceled",
}

TRANSACTION_EVENTS = {
    "transaction.completed",
}

SUPPORTED_EVENTS = SUBSCRIPTION_EVENTS | TRANSACTION_EVENTS


def resolve_organization(
    db: Session,
    event_type: str,
    subscription_id: str | None,
    customer_id: str | None,
    organization_id_raw: str | None,
) -> Organization | None:
    organization = None

    if organization_id_raw:
        try:
            organization_id = int(organization_id_raw)
        except (TypeError, ValueError):
            organization_id = None

        if organization_id is not None:
            organization = (
                db.query(Organization)
                .filter(Organization.id == organization_id)
                .first()
            )

    if organization is None and subscription_id:
        organization = (
            db.query(Organization)
            .filter(Organization.billing_subscription_id == subscription_id)
            .first()
        )

    if organization is None and customer_id:
        organization = (
            db.query(Organization)
            .filter(Organization.billing_customer_id == customer_id)
            .first()
        )

    return organization


def is_canonical_subscription(
    organization: Organization,
    subscription_id: str | None,
) -> bool:
    if (
        subscription_id
        and organization.billing_subscription_id
        and subscription_id != organization.billing_subscription_id
    ):
        return False
    return True


def is_duplicate_event(
    organization: Organization,
    event_id: str,
) -> bool:
    return organization.billing_last_event_id == event_id


def is_out_of_order_event(
    organization: Organization,
    occurred_at: datetime | None,
) -> bool:
    if (
        occurred_at is not None
        and organization.billing_last_event_at is not None
        and occurred_at < organization.billing_last_event_at
    ):
        return True
    return False


def update_billing_fields(
    organization: Organization,
    customer_id: str | None,
    subscription_id: str | None,
    price_id: str | None,
    billing_period_months: int | None,
):
    organization.billing_provider = "paddle"

    if customer_id:
        organization.billing_customer_id = customer_id

    if subscription_id:
        organization.billing_subscription_id = subscription_id

    if price_id:
        organization.billing_price_id = price_id

    if billing_period_months is not None and not organization.pending_plan:
        organization.billing_period_months = billing_period_months


def process_transaction_event(
    organization: Organization,
    event_id: str,
    occurred_at: datetime | None,
    plan_key: str | None,
    data: dict,
    db: Session,
) -> dict:
    if (
        organization.pending_plan
        and organization.pending_plan_effective_at
        and occurred_at is not None
        and occurred_at >= organization.pending_plan_effective_at
    ):
        target_plan = organization.pending_plan
        target_period = int(
            organization.pending_billing_period_months
            or organization.billing_period_months
            or 1
        )

        current_rank = BILLING_PLAN_ORDER.get(organization.plan, 0)
        target_rank = BILLING_PLAN_ORDER.get(target_plan, 0)
        is_plan_downgrade = target_rank < current_rank

        target_limit = int(
            __import__(
                "app.plan_limits", fromlist=["get_limits_for_plan"]
            ).get_limits_for_plan(target_plan).active_stores
        )

        selected_all = (
            db.query(Store)
            .filter(
                Store.organization_id == organization.id,
                Store.keep_on_pending_downgrade.is_(True),
            )
            .order_by(Store.id.asc())
            .all()
        )

        intended_selection_count = min(len(selected_all), target_limit)

        selected_valid = [
            store for store in selected_all if not store.deleted
        ]

        selected_valid = selected_valid[:target_limit]

        keep_ids = {store.id for store in selected_valid}

        if not is_plan_downgrade:
            keep_ids = {
                store.id
                for store in (
                    db.query(Store)
                    .filter(
                        Store.organization_id == organization.id,
                        Store.deleted.is_(False),
                        Store.active.is_(True),
                    )
                    .all()
                )
            }

            intended_selection_count = len(keep_ids)
            selected_valid = []

        missing_selected = max(0, intended_selection_count - len(selected_valid))

        if missing_selected > 0:
            fallback_stores = (
                db.query(Store)
                .filter(
                    Store.organization_id == organization.id,
                    Store.deleted.is_(False),
                    Store.active.is_(True),
                    Store.id.notin_(keep_ids) if keep_ids else True,
                )
                .order_by(
                    Store.active_since.is_(None),
                    Store.active_since.asc(),
                    Store.id.asc(),
                )
                .limit(missing_selected)
                .all()
            )

            for store in fallback_stores:
                keep_ids.add(store.id)

        stores = (
            db.query(Store)
            .filter(
                Store.organization_id == organization.id,
                Store.deleted.is_(False),
            )
            .all()
        )

        for store in stores:
            should_be_active = store.id in keep_ids
            if store.active != should_be_active:
                store.active = should_be_active

        for store in selected_all:
            store.keep_on_pending_downgrade = False

        organization.plan = target_plan
        organization.billing_period_months = target_period
        organization.pending_plan = None
        organization.pending_billing_period_months = None
        organization.pending_plan_effective_at = None
        organization.pending_plan_prepared_at = None

    elif plan_key and not organization.pending_plan:
        organization.plan = plan_key

    organization.billing_last_event_id = event_id

    if occurred_at is not None:
        organization.billing_last_event_at = occurred_at

    db.commit()

    return {
        "ok": True,
        "organization_id": organization.id,
        "transaction_id": data.get("id"),
        "customer_id": organization.billing_customer_id,
        "subscription_id": organization.billing_subscription_id,
        "price_id": organization.billing_price_id,
        "plan": organization.plan,
        "subscription_status": organization.subscription_status,
    }


def process_subscription_event(
    organization: Organization,
    event_id: str,
    occurred_at: datetime | None,
    event_type: str,
    plan_key: str | None,
    price_id: str | None,
    billing_period_months: int | None,
    status: str | None,
    data: dict,
    db: Session,
) -> dict:
    if status:
        organization.subscription_status = status

    scheduled_change = data.get("scheduled_change")
    scheduled_action = (
        scheduled_change.get("action")
        if isinstance(scheduled_change, dict)
        else None
    )

    if status == "canceled":
        organization.auto_renew_enabled = False
    elif scheduled_action == "cancel":
        organization.auto_renew_enabled = False
    elif status in {"active", "trialing"}:
        organization.auto_renew_enabled = True

    if plan_key and status in {"active", "trialing", "past_due"}:
        current_rank = BILLING_PLAN_ORDER.get(organization.plan, 0)
        incoming_rank = BILLING_PLAN_ORDER.get(plan_key, 0)
        pending_plan = organization.pending_plan
        pending_rank = BILLING_PLAN_ORDER.get(pending_plan, 0) if pending_plan else 0

        has_pending_change = bool(
            pending_plan and organization.pending_plan_effective_at
        )

        incoming_is_current_plan = plan_key == organization.plan
        incoming_is_pending_target = has_pending_change and plan_key == pending_plan

        if has_pending_change and (
            incoming_is_current_plan or incoming_is_pending_target
        ):
            pass
        else:
            organization.plan = plan_key
            organization.pending_plan = None
            organization.pending_billing_period_months = None
            organization.pending_plan_effective_at = None
            organization.pending_plan_prepared_at = None

            db.query(Store).filter(
                Store.organization_id == organization.id,
            ).update(
                {Store.keep_on_pending_downgrade: False},
                synchronize_session=False,
            )

    if status in {"canceled", "paused"}:
        db.query(Store).filter(
            Store.organization_id == organization.id,
            Store.deleted.is_(False),
            Store.active.is_(True),
        ).update(
            {Store.active: False, Store.active_since: None},
            synchronize_session=False,
        )

    if status == "canceled":
        organization.plan = "none"

    organization.billing_last_event_id = event_id

    if occurred_at is not None:
        organization.billing_last_event_at = occurred_at

    db.commit()

    return {
        "ok": True,
        "event_type": event_type,
        "organization_id": organization.id,
        "subscription_status": organization.subscription_status,
        "plan": organization.plan,
    }
