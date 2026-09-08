"""AI usage service.

Tracks successful AI responses per organization billing period.
Commercial unit: AI responses (not tokens).
Internal unit: tokens (for cost analysis only).
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Message, Conversation, Organization
from ..plan_limits import get_organization_limits

logger = logging.getLogger(__name__)

OVERAGE_PRICE_PER_1000 = Decimal("5.00")


def get_ai_usage(
    db: Session,
    organization_id: int,
    billing_period_start: datetime | None = None,
    billing_period_end: datetime | None = None,
) -> dict:
    """Get AI usage for an organization within billing period."""
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .first()
    )
    if not organization:
        return {"error": "Organization not found"}

    plan = (organization.plan or "none").strip().lower()
    limits = get_organization_limits(organization)
    included = limits.included_ai_responses

    # Count successful AI responses in this organization
    query = (
        db.query(func.count(Message.id))
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

    used = query.scalar() or 0

    remaining = max(included - used, 0)
    usage_pct = (used / included * 100) if included > 0 else 0
    overage = max(used - included, 0)

    if usage_pct >= 100:
        status = "INCLUDED_EXHAUSTED"
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
        "remaining_ai_responses": remaining,
        "usage_percent": round(usage_pct, 1),
        "overage_ai_responses": overage,
        "status": status,
        "overage_price_per_1000": str(OVERAGE_PRICE_PER_1000),
    }


def get_ai_usage_by_store(
    db: Session,
    organization_id: int,
    billing_period_start: datetime | None = None,
    billing_period_end: datetime | None = None,
) -> list[dict]:
    """Get per-store AI usage breakdown."""
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


def check_ai_availability(
    db: Session,
    organization_id: int,
) -> dict:
    """Check if AI responses are available for this organization."""
    usage = get_ai_usage(db, organization_id)

    if "error" in usage:
        return usage

    return {
        "available": usage["status"] != "INCLUDED_EXHAUSTED",
        "status": usage["status"],
        "remaining": usage["remaining_ai_responses"],
    }
