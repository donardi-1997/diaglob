"""Platform admin growth analytics.

Adds auditable time-based platform metrics without pretending that billing history
exists where the current schema only stores subscription state snapshots.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Conversation, Message, Order, Organization, User


def _iso_day(value: datetime) -> str:
    return value.date().isoformat()


def _blank_daily_series(start: datetime, days: int) -> dict[str, dict[str, int]]:
    return {
        (start + timedelta(days=index)).date().isoformat(): {
            "organizations": 0,
            "users": 0,
            "ai_responses": 0,
            "orders": 0,
        }
        for index in range(days)
    }


def _rank_rows(rows, org_map: dict[int, Organization], metric: str, limit: int = 10):
    ranked = []
    for organization_id, value in rows:
        organization = org_map.get(organization_id)
        if not organization:
            continue
        ranked.append(
            {
                "organization_id": organization.id,
                "organization_name": organization.name,
                "plan": organization.plan or "none",
                metric: int(value or 0),
            }
        )
    return ranked[:limit]


def get_admin_growth_metrics(db: Session, days: int = 30) -> dict:
    """Return recent platform growth, billing health, and organization rankings.

    Historical MRR/churn/upgrade/downgrade metrics are intentionally marked as
    unavailable because Organization stores only current billing state and the
    most recent billing event, not an immutable billing event ledger.
    """
    days = max(1, min(days, 90))
    now = datetime.utcnow()
    start = datetime(now.year, now.month, now.day) - timedelta(days=days - 1)
    end = start + timedelta(days=days)

    daily = _blank_daily_series(start, days)

    organizations = (
        db.query(Organization)
        .filter(Organization.created_at >= start, Organization.created_at < end)
        .all()
    )
    for organization in organizations:
        daily[_iso_day(organization.created_at)]["organizations"] += 1

    users = (
        db.query(User)
        .filter(User.created_at >= start, User.created_at < end)
        .all()
    )
    for user in users:
        daily[_iso_day(user.created_at)]["users"] += 1

    ai_messages = (
        db.query(Message.created_at)
        .filter(
            Message.sender == "ai",
            Message.created_at >= start,
            Message.created_at < end,
        )
        .all()
    )
    for row in ai_messages:
        daily[_iso_day(row[0])]["ai_responses"] += 1

    orders = (
        db.query(Order.created_at)
        .filter(Order.created_at >= start, Order.created_at < end)
        .all()
    )
    for row in orders:
        daily[_iso_day(row[0])]["orders"] += 1

    status_rows = (
        db.query(Organization.subscription_status, func.count(Organization.id))
        .group_by(Organization.subscription_status)
        .all()
    )
    subscription_statuses = {
        (status or "unknown"): int(count or 0)
        for status, count in status_rows
    }

    pending_plan_changes = (
        db.query(func.count(Organization.id))
        .filter(Organization.pending_plan.isnot(None))
        .scalar()
        or 0
    )
    auto_renew_disabled = (
        db.query(func.count(Organization.id))
        .filter(Organization.auto_renew_enabled.is_(False))
        .scalar()
        or 0
    )

    all_orgs = db.query(Organization).all()
    org_map = {organization.id: organization for organization in all_orgs}

    ai_rank_rows = (
        db.query(
            Conversation.organization_id,
            func.count(Message.id).label("ai_responses"),
        )
        .join(Message, Message.conversation_id == Conversation.id)
        .filter(
            Message.sender == "ai",
            Message.created_at >= start,
            Message.created_at < end,
        )
        .group_by(Conversation.organization_id)
        .order_by(func.count(Message.id).desc())
        .limit(10)
        .all()
    )

    order_rank_rows = (
        db.query(
            Order.organization_id,
            func.count(Order.id).label("orders"),
        )
        .filter(Order.created_at >= start, Order.created_at < end)
        .group_by(Order.organization_id)
        .order_by(func.count(Order.id).desc())
        .limit(10)
        .all()
    )

    conversation_rank_rows = (
        db.query(
            Conversation.organization_id,
            func.count(Conversation.id).label("conversations"),
        )
        .filter(Conversation.created_at >= start, Conversation.created_at < end)
        .group_by(Conversation.organization_id)
        .order_by(func.count(Conversation.id).desc())
        .limit(10)
        .all()
    )

    series = [
        {"date": day, **values}
        for day, values in sorted(daily.items())
    ]

    return {
        "window_days": days,
        "period": {
            "from": start.isoformat() + "Z",
            "to": end.isoformat() + "Z",
        },
        "totals": {
            "new_organizations": len(organizations),
            "new_users": len(users),
            "ai_responses": len(ai_messages),
            "orders": len(orders),
        },
        "daily": series,
        "billing_health": {
            "subscription_statuses": subscription_statuses,
            "pending_plan_changes": int(pending_plan_changes),
            "auto_renew_disabled": int(auto_renew_disabled),
            "historical_billing_available": False,
            "historical_billing_reason": (
                "The current schema stores subscription snapshots but not an immutable "
                "billing event ledger, so historical MRR, churn, upgrades, and downgrades "
                "cannot be reconstructed reliably."
            ),
        },
        "rankings": {
            "top_ai_usage": _rank_rows(ai_rank_rows, org_map, "ai_responses"),
            "top_orders": _rank_rows(order_rank_rows, org_map, "orders"),
            "top_conversations": _rank_rows(
                conversation_rank_rows,
                org_map,
                "conversations",
            ),
        },
    }
