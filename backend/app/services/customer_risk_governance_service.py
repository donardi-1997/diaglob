"""Governance primitives for customer-risk reports and disputes.

These helpers keep immutable audit writes and abuse controls out of HTTP
routers. They do not decide whether a customer is risky and never auto-block a
customer or order.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..model_domains.customer_risk import (
    CustomerRiskDisputeEvent,
    CustomerRiskReportEvent,
)


class CustomerRiskRateLimitError(Exception):
    """Raised when an organization exceeds a risk-governance write budget."""


def _bounded_env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def report_write_limit_24h() -> int:
    return _bounded_env_int(
        "CUSTOMER_RISK_REPORT_LIMIT_24H",
        25,
        minimum=1,
        maximum=500,
    )


def dispute_write_limit_24h() -> int:
    return _bounded_env_int(
        "CUSTOMER_RISK_DISPUTE_LIMIT_24H",
        10,
        minimum=1,
        maximum=200,
    )


def enforce_report_write_limit(db: Session, organization_id: int) -> None:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    count = (
        db.query(CustomerRiskReportEvent)
        .filter(
            CustomerRiskReportEvent.organization_id == organization_id,
            CustomerRiskReportEvent.actor_role == "reporter",
            CustomerRiskReportEvent.action.in_([
                "report_submitted",
                "report_updated",
            ]),
            CustomerRiskReportEvent.created_at >= cutoff,
        )
        .count()
    )
    limit = report_write_limit_24h()
    if count >= limit:
        raise CustomerRiskRateLimitError(
            f"Customer risk report limit reached ({limit} writes per 24 hours)"
        )


def enforce_dispute_write_limit(db: Session, organization_id: int) -> None:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    count = (
        db.query(CustomerRiskDisputeEvent)
        .filter(
            CustomerRiskDisputeEvent.organization_id == organization_id,
            CustomerRiskDisputeEvent.actor_role == "requester",
            CustomerRiskDisputeEvent.action.in_([
                "dispute_submitted",
                "dispute_updated",
            ]),
            CustomerRiskDisputeEvent.created_at >= cutoff,
        )
        .count()
    )
    limit = dispute_write_limit_24h()
    if count >= limit:
        raise CustomerRiskRateLimitError(
            f"Customer risk dispute limit reached ({limit} writes per 24 hours)"
        )


def add_report_event(
    db: Session,
    *,
    report_id: int,
    organization_id: int,
    actor_user_id: int | None,
    actor_role: str,
    action: str,
    from_status: str | None,
    to_status: str | None,
    note: str | None = None,
) -> CustomerRiskReportEvent:
    event = CustomerRiskReportEvent(
        report_id=report_id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        from_status=from_status,
        to_status=to_status,
        note=(note or "").strip() or None,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    return event


def add_dispute_event(
    db: Session,
    *,
    dispute_id: int,
    organization_id: int,
    actor_user_id: int | None,
    actor_role: str,
    action: str,
    from_status: str | None,
    to_status: str | None,
    note: str | None = None,
) -> CustomerRiskDisputeEvent:
    event = CustomerRiskDisputeEvent(
        dispute_id=dispute_id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        from_status=from_status,
        to_status=to_status,
        note=(note or "").strip() or None,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    return event
