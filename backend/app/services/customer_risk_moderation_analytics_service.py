"""Platform-admin analytics for shared customer-risk moderation.

This module is read-only: it aggregates moderation workload, response times,
outcomes and reporting-organization activity. It never changes report/dispute
state and its metrics must not be used for automatic customer blocking.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..model_domains.customer_risk import (
    CustomerRiskDispute,
    CustomerRiskReport,
    CustomerRiskReportEvent,
)
from ..models import Organization


REPORT_MODERATION_ACTIONS = {
    "moderation_confirmed",
    "moderation_dismissed",
    "moderation_disputed",
    "moderation_reset_pending",
}
REPORT_REASONS = (
    "suspected_fraud",
    "payment_abuse",
    "delivery_claim",
    "identity_mismatch",
    "abusive_behavior",
    "other",
)


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _window(days: int, now: datetime) -> tuple[int, datetime]:
    bounded_days = max(7, min(90, int(days)))
    start_date = now.date() - timedelta(days=bounded_days - 1)
    return bounded_days, datetime.combine(start_date, time.min)


def get_customer_risk_moderation_analytics(
    db: Session,
    *,
    days: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return platform moderation analytics for the requested rolling date window.

    The window is aligned to UTC calendar days because customer-risk timestamps
    are stored as naive UTC datetimes. ``days`` is intentionally bounded to
    7..90 to keep this platform-admin endpoint predictable.
    """
    now = now or datetime.utcnow()
    days, cutoff = _window(days, now)
    stale_cutoff = now - timedelta(hours=24)

    report_rows = (
        db.query(
            CustomerRiskReport.id,
            CustomerRiskReport.reporter_organization_id,
            CustomerRiskReport.reason,
            CustomerRiskReport.status,
            CustomerRiskReport.evidence_reference,
            CustomerRiskReport.created_at,
        )
        .filter(
            CustomerRiskReport.created_at >= cutoff,
            CustomerRiskReport.created_at <= now,
        )
        .all()
    )
    dispute_rows = (
        db.query(
            CustomerRiskDispute.id,
            CustomerRiskDispute.status,
            CustomerRiskDispute.created_at,
            CustomerRiskDispute.resolved_at,
        )
        .filter(
            CustomerRiskDispute.created_at >= cutoff,
            CustomerRiskDispute.created_at <= now,
        )
        .all()
    )
    moderation_event_rows = (
        db.query(
            CustomerRiskReportEvent.report_id,
            CustomerRiskReportEvent.action,
            CustomerRiskReportEvent.created_at,
        )
        .filter(
            CustomerRiskReportEvent.action.in_(REPORT_MODERATION_ACTIONS),
            CustomerRiskReportEvent.created_at >= cutoff,
            CustomerRiskReportEvent.created_at <= now,
        )
        .all()
    )

    resolved_disputes = [
        row
        for row in dispute_rows
        if row.status in {"accepted", "rejected"}
        and row.resolved_at is not None
        and cutoff <= row.resolved_at <= now
    ]

    report_action_counts = Counter(row.action for row in moderation_event_rows)
    definitive_report_actions = (
        report_action_counts["moderation_confirmed"]
        + report_action_counts["moderation_dismissed"]
    )
    dispute_status_counts = Counter(row.status for row in resolved_disputes)

    moderated_report_ids = {row.report_id for row in moderation_event_rows}
    report_resolution_hours: list[float] = []
    if moderated_report_ids:
        all_moderation_events = (
            db.query(
                CustomerRiskReportEvent.report_id,
                CustomerRiskReportEvent.created_at,
            )
            .filter(
                CustomerRiskReportEvent.report_id.in_(moderated_report_ids),
                CustomerRiskReportEvent.action.in_(REPORT_MODERATION_ACTIONS),
            )
            .order_by(
                CustomerRiskReportEvent.report_id.asc(),
                CustomerRiskReportEvent.created_at.asc(),
                CustomerRiskReportEvent.id.asc(),
            )
            .all()
        )
        first_moderation_at: dict[int, datetime] = {}
        for report_id, created_at in all_moderation_events:
            first_moderation_at.setdefault(report_id, created_at)

        first_resolved_in_window = {
            report_id: created_at
            for report_id, created_at in first_moderation_at.items()
            if cutoff <= created_at <= now
        }
        if first_resolved_in_window:
            created_rows = (
                db.query(CustomerRiskReport.id, CustomerRiskReport.created_at)
                .filter(CustomerRiskReport.id.in_(first_resolved_in_window))
                .all()
            )
            for report_id, created_at in created_rows:
                elapsed = first_resolved_in_window[report_id] - created_at
                report_resolution_hours.append(max(0.0, elapsed.total_seconds() / 3600))

    dispute_resolution_hours = [
        max(0.0, (row.resolved_at - row.created_at).total_seconds() / 3600)
        for row in resolved_disputes
        if row.resolved_at is not None
    ]

    backlog = {
        "pending_reports": db.query(CustomerRiskReport)
        .filter(CustomerRiskReport.status == "pending")
        .count(),
        "disputed_reports": db.query(CustomerRiskReport)
        .filter(CustomerRiskReport.status == "disputed")
        .count(),
        "open_disputes": db.query(CustomerRiskDispute)
        .filter(CustomerRiskDispute.status == "open")
        .count(),
        "pending_reports_over_24h": db.query(CustomerRiskReport)
        .filter(
            CustomerRiskReport.status == "pending",
            CustomerRiskReport.created_at < stale_cutoff,
        )
        .count(),
        "open_disputes_over_24h": db.query(CustomerRiskDispute)
        .filter(
            CustomerRiskDispute.status == "open",
            CustomerRiskDispute.created_at < stale_cutoff,
        )
        .count(),
    }

    daily: dict[str, dict[str, int]] = {}
    for offset in range(days):
        day = (cutoff.date() + timedelta(days=offset)).isoformat()
        daily[day] = {
            "reports_created": 0,
            "reports_moderated": 0,
            "disputes_created": 0,
            "disputes_resolved": 0,
        }

    for row in report_rows:
        key = row.created_at.date().isoformat()
        if key in daily:
            daily[key]["reports_created"] += 1
    for row in moderation_event_rows:
        key = row.created_at.date().isoformat()
        if key in daily:
            daily[key]["reports_moderated"] += 1
    for row in dispute_rows:
        key = row.created_at.date().isoformat()
        if key in daily:
            daily[key]["disputes_created"] += 1
    for row in resolved_disputes:
        key = row.resolved_at.date().isoformat()
        if key in daily:
            daily[key]["disputes_resolved"] += 1

    reason_counts = Counter(row.reason for row in report_rows)
    reason_breakdown = [
        {
            "reason": reason,
            "count": reason_counts[reason],
            "percentage": _percentage(reason_counts[reason], len(report_rows)),
        }
        for reason in REPORT_REASONS
        if reason_counts[reason] > 0
    ]
    reason_breakdown.sort(key=lambda item: (item["count"], item["reason"]), reverse=True)

    organization_activity: dict[int, dict[str, Any]] = defaultdict(
        lambda: {
            "report_count": 0,
            "with_evidence": 0,
            "status_counts": Counter(),
        }
    )
    for row in report_rows:
        activity = organization_activity[row.reporter_organization_id]
        activity["report_count"] += 1
        activity["with_evidence"] += int(bool(row.evidence_reference))
        activity["status_counts"][row.status] += 1

    org_ids = set(organization_activity)
    organization_names = {}
    if org_ids:
        organization_names = {
            row.id: row.name
            for row in db.query(Organization.id, Organization.name)
            .filter(Organization.id.in_(org_ids))
            .all()
        }

    organizations = []
    for organization_id, activity in organization_activity.items():
        status_counts = activity["status_counts"]
        reviewed = status_counts["confirmed"] + status_counts["dismissed"]
        organizations.append(
            {
                "organization_id": organization_id,
                "organization_name": organization_names.get(organization_id),
                "report_count": activity["report_count"],
                "evidence_rate": _percentage(
                    activity["with_evidence"],
                    activity["report_count"],
                ),
                "confirmed": status_counts["confirmed"],
                "dismissed": status_counts["dismissed"],
                "disputed": status_counts["disputed"],
                "pending": status_counts["pending"],
                "dismissal_rate": _percentage(status_counts["dismissed"], reviewed),
            }
        )
    organizations.sort(
        key=lambda item: (item["report_count"], item["organization_id"]),
        reverse=True,
    )

    return {
        "window": {
            "days": days,
            "from": cutoff.isoformat(),
            "to": now.isoformat(),
        },
        "summary": {
            "reports_created": len(report_rows),
            "moderated_reports": len(moderated_report_ids),
            "moderation_actions": len(moderation_event_rows),
            "disputes_created": len(dispute_rows),
            "disputes_resolved": len(resolved_disputes),
            "average_report_resolution_hours": _average(report_resolution_hours),
            "average_dispute_resolution_hours": _average(dispute_resolution_hours),
            "confirmation_rate": _percentage(
                report_action_counts["moderation_confirmed"],
                definitive_report_actions,
            ),
            "appeal_acceptance_rate": _percentage(
                dispute_status_counts["accepted"],
                len(resolved_disputes),
            ),
        },
        "outcomes": {
            "reports": {
                "confirmed": report_action_counts["moderation_confirmed"],
                "dismissed": report_action_counts["moderation_dismissed"],
                "disputed": report_action_counts["moderation_disputed"],
                "reset_pending": report_action_counts["moderation_reset_pending"],
            },
            "disputes": {
                "accepted": dispute_status_counts["accepted"],
                "rejected": dispute_status_counts["rejected"],
            },
        },
        "backlog": backlog,
        "daily": [
            {"date": day, **counts}
            for day, counts in daily.items()
        ],
        "reason_breakdown": reason_breakdown,
        "reporting_organizations": organizations[:10],
        "governance_note": (
            "Reporting-organization outcome metrics are human-review signals only; "
            "they must not automatically block customers, orders, or reporters."
        ),
    }
