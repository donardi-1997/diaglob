"""AI usage metering and capacity service.

Commercial unit: successful AI responses, not tokens. Included responses reset
on the first day of each UTC calendar month. Purchased response packages are an
organization-level balance that does not expire and is consumed only after the
monthly included allowance is exhausted.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..model_domains.ai_usage import AiUsageCreditGrant
from ..models import Conversation, Message, Organization
from ..plan_limits import get_organization_limits
from .trial_service import get_trial_entitlement, refresh_trial_state

logger = logging.getLogger(__name__)

OVERAGE_PRICE_PER_1000 = Decimal("5.00")
_ACTIVE_GRANT_STATUSES = {"active", "consumed"}


def get_ai_usage_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the current UTC calendar-month usage window as naive datetimes."""
    current = now or datetime.utcnow()
    start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _count_ai_responses(
    db: Session,
    organization_id: int,
    start: datetime | None,
    end: datetime | None,
) -> int:
    query = (
        db.query(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.organization_id == organization_id,
            Message.sender == "ai",
        )
    )
    if start:
        query = query.filter(Message.created_at >= start)
    if end:
        query = query.filter(Message.created_at < end)
    return int(query.scalar() or 0)


def _extra_credit_totals(db: Session, organization_id: int) -> tuple[int, int]:
    row = (
        db.query(
            func.coalesce(func.sum(AiUsageCreditGrant.responses_total), 0),
            func.coalesce(func.sum(AiUsageCreditGrant.responses_remaining), 0),
        )
        .filter(
            AiUsageCreditGrant.organization_id == organization_id,
            AiUsageCreditGrant.status.in_(_ACTIVE_GRANT_STATUSES),
        )
        .one()
    )
    return int(row[0] or 0), int(row[1] or 0)


def get_ai_usage(
    db: Session,
    organization_id: int,
    billing_period_start: datetime | None = None,
    billing_period_end: datetime | None = None,
) -> dict:
    """Get monthly included usage plus non-expiring purchased extra balance."""
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )
    if not organization:
        return {"error": "Organization not found"}

    trial_entitlement = refresh_trial_state(db, organization)
    plan = (organization.plan or "none").strip().lower()

    if billing_period_start is None and billing_period_end is None:
        if (
            plan == "trial"
            and trial_entitlement is not None
            and trial_entitlement.started_at is not None
        ):
            billing_period_start = trial_entitlement.started_at
            billing_period_end = trial_entitlement.ends_at
        else:
            billing_period_start, billing_period_end = get_ai_usage_window()
    included = get_organization_limits(organization).included_ai_responses
    used = _count_ai_responses(
        db,
        organization_id,
        billing_period_start,
        billing_period_end,
    )

    purchased_total, extra_remaining = _extra_credit_totals(db, organization_id)
    remaining_included = max(included - used, 0)
    remaining = remaining_included + extra_remaining
    usage_pct = (used / included * 100) if included > 0 else 0
    beyond_included = max(used - included, 0)

    if remaining <= 0:
        status = "INCLUDED_EXHAUSTED"
    elif remaining_included <= 0 and extra_remaining > 0:
        status = "EXTRA_ACTIVE"
    elif usage_pct >= 95:
        status = "WARNING_95"
    elif usage_pct >= 80:
        status = "WARNING_80"
    else:
        status = "NORMAL"

    return {
        "plan": plan,
        "included_ai_responses": included,
        "used_ai_responses": used,
        "remaining_included_ai_responses": remaining_included,
        "extra_ai_responses_purchased": purchased_total,
        "extra_ai_responses_remaining": extra_remaining,
        "remaining_ai_responses": remaining,
        "usage_percent": round(usage_pct, 1),
        "overage_ai_responses": beyond_included,
        "status": status,
        "overage_price_per_1000": str(OVERAGE_PRICE_PER_1000),
        "usage_period_start": (
            billing_period_start.isoformat() if billing_period_start else None
        ),
        "usage_period_end": (
            billing_period_end.isoformat() if billing_period_end else None
        ),
    }


def get_ai_usage_by_store(
    db: Session,
    organization_id: int,
    billing_period_start: datetime | None = None,
    billing_period_end: datetime | None = None,
) -> list[dict]:
    """Get per-store AI usage for the current month unless a window is supplied."""
    if billing_period_start is None and billing_period_end is None:
        billing_period_start, billing_period_end = get_ai_usage_window()

    query = (
        db.query(
            Conversation.store_id,
            func.count(Message.id).label("count"),
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Conversation.organization_id == organization_id,
            Message.sender == "ai",
        )
    )
    if billing_period_start:
        query = query.filter(Message.created_at >= billing_period_start)
    if billing_period_end:
        query = query.filter(Message.created_at < billing_period_end)

    rows = query.group_by(Conversation.store_id).all()
    return [
        {"store_id": row[0], "ai_responses": row[1]}
        for row in rows
    ]


def check_ai_availability(db: Session, organization_id: int) -> dict:
    """Check effective capacity including purchased response packages."""
    usage = get_ai_usage(db, organization_id)
    if "error" in usage:
        return usage
    return {
        "available": usage["remaining_ai_responses"] > 0,
        "status": usage["status"],
        "remaining": usage["remaining_ai_responses"],
        "extra_remaining": usage["extra_ai_responses_remaining"],
    }


def acquire_ai_capacity(
    db: Session,
    organization_id: int,
    now: datetime | None = None,
) -> dict:
    """Reserve one extra response when the monthly included allowance is spent.

    Included capacity needs no reservation because persisted AI messages are the
    source of truth. Extra capacity is decremented before inference and can be
    refunded when generation fails.
    """
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )
    if not organization:
        return {"available": False, "source": None, "reason": "organization_not_found"}

    trial_entitlement = refresh_trial_state(db, organization, now=now)
    plan = (organization.plan or "none").strip().lower()
    subscription_status = (
        organization.subscription_status or ""
    ).strip().lower()

    if subscription_status in {
        "trial_pending",
        "trial_expired",
        "trial_blocked",
    }:
        return {
            "available": False,
            "source": None,
            "grant_id": None,
            "reason": subscription_status,
        }

    if (
        plan == "trial"
        and subscription_status == "trialing"
        and trial_entitlement is not None
        and trial_entitlement.started_at is not None
    ):
        start = trial_entitlement.started_at
        end = trial_entitlement.ends_at
    else:
        start, end = get_ai_usage_window(now)

    included = get_organization_limits(organization).included_ai_responses
    used = _count_ai_responses(db, organization_id, start, end)

    if used < included:
        return {
            "available": True,
            "source": "included",
            "grant_id": None,
            "remaining_included": max(included - used, 0),
        }

    grant = (
        db.query(AiUsageCreditGrant)
        .filter(
            AiUsageCreditGrant.organization_id == organization_id,
            AiUsageCreditGrant.status == "active",
            AiUsageCreditGrant.responses_remaining > 0,
        )
        .order_by(
            AiUsageCreditGrant.purchased_at.asc(),
            AiUsageCreditGrant.id.asc(),
        )
        .with_for_update()
        .first()
    )

    if not grant:
        return {
            "available": False,
            "source": None,
            "grant_id": None,
            "reason": "ai_usage_exhausted",
        }

    grant.responses_remaining -= 1
    if grant.responses_remaining <= 0:
        grant.responses_remaining = 0
        grant.status = "consumed"
    db.commit()

    return {
        "available": True,
        "source": "extra",
        "grant_id": grant.id,
        "remaining_extra_in_grant": grant.responses_remaining,
    }


def refund_ai_capacity(db: Session, reservation: dict | None) -> None:
    """Return an extra response reservation when generation did not succeed."""
    if not reservation or reservation.get("source") != "extra":
        return

    grant_id = reservation.get("grant_id")
    if not grant_id:
        return

    grant = (
        db.query(AiUsageCreditGrant)
        .filter(AiUsageCreditGrant.id == grant_id)
        .with_for_update()
        .first()
    )
    if not grant:
        return

    if grant.responses_remaining < grant.responses_total:
        grant.responses_remaining += 1
    if grant.responses_remaining > 0:
        grant.status = "active"
    db.commit()
