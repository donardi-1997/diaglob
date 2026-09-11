"""Platform moderation workflow for shared customer-risk signals.

Only platform-admin HTTP handlers should call this service. It intentionally
keeps reporter-private evidence inside the moderation boundary. Customer-facing
risk summaries remain aggregate and never expose reporter identity.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..model_domains.customer_risk import (
    CustomerRiskDispute,
    CustomerRiskDisputeEvent,
    CustomerRiskReport,
    CustomerRiskReportEvent,
)
from ..models import Customer, Organization, User
from .customer_risk_governance_service import (
    add_dispute_event,
    add_report_event,
    dispute_write_limit_24h,
    report_write_limit_24h,
)


class CustomerRiskModerationError(Exception):
    pass


class CustomerRiskModerationNotFoundError(CustomerRiskModerationError):
    pass


class CustomerRiskModerationValidationError(CustomerRiskModerationError):
    pass


REPORT_ACTIONS = {
    "confirm": ("confirmed", "moderation_confirmed"),
    "dismiss": ("dismissed", "moderation_dismissed"),
    "mark_disputed": ("disputed", "moderation_disputed"),
    "reset_pending": ("pending", "moderation_reset_pending"),
}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _mask_email(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value or "@" not in value:
        return None
    local, domain = value.split("@", 1)
    visible = local[:2] if len(local) > 1 else local[:1]
    return f"{visible}{'*' * max(2, len(local) - len(visible))}@{domain}"


def _mask_phone(value: str | None) -> str | None:
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def _customer_snapshot(customer: Customer | None) -> dict[str, Any] | None:
    if customer is None:
        return None
    return {
        "id": customer.id,
        "name": customer.name,
        "email_masked": _mask_email(customer.email),
        "phone_masked": _mask_phone(customer.phone),
        "country_code": customer.country_code,
    }


def _organization_names(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.query(Organization).filter(Organization.id.in_(ids)).all()
    return {row.id: row.name for row in rows}


def _user_labels(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.query(User).filter(User.id.in_(ids)).all()
    return {
        row.id: (row.name or "").strip() or row.email
        for row in rows
    }


def _reputation_from_counts(counts: Counter[str]) -> dict[str, Any]:
    confirmed = counts["confirmed"]
    dismissed = counts["dismissed"]
    disputed = counts["disputed"]
    pending = counts["pending"]
    moderated = confirmed + dismissed
    # Bayesian smoothing keeps tiny samples near neutral instead of labeling a
    # new reporter as highly trusted/untrusted after one decision.
    score = round(100 * (confirmed + 2) / (moderated + 4))
    if moderated < 3:
        level = "new"
    elif score >= 70:
        level = "trusted"
    elif score < 35:
        level = "watch"
    else:
        level = "established"
    return {
        "score": score,
        "level": level,
        "moderated_reports": moderated,
        "confirmed_reports": confirmed,
        "dismissed_reports": dismissed,
        "disputed_reports": disputed,
        "pending_reports": pending,
    }


def _reputation_map(db: Session, organization_ids: set[int]) -> dict[int, dict[str, Any]]:
    if not organization_ids:
        return {}
    rows = (
        db.query(CustomerRiskReport.reporter_organization_id, CustomerRiskReport.status)
        .filter(CustomerRiskReport.reporter_organization_id.in_(organization_ids))
        .all()
    )
    counts: dict[int, Counter[str]] = {
        organization_id: Counter() for organization_id in organization_ids
    }
    for organization_id, status in rows:
        counts[organization_id][status] += 1
    return {
        organization_id: _reputation_from_counts(org_counts)
        for organization_id, org_counts in counts.items()
    }


def _matching_disputes_for_reports(
    db: Session,
    reports: list[CustomerRiskReport],
    *,
    statuses: set[str] | None = None,
) -> list[CustomerRiskDispute]:
    phone_values = {row.phone_fingerprint for row in reports if row.phone_fingerprint}
    email_values = {row.email_fingerprint for row in reports if row.email_fingerprint}
    clauses = []
    if phone_values:
        clauses.append(CustomerRiskDispute.phone_fingerprint.in_(phone_values))
    if email_values:
        clauses.append(CustomerRiskDispute.email_fingerprint.in_(email_values))
    if not clauses:
        return []
    query = db.query(CustomerRiskDispute).filter(or_(*clauses))
    if statuses:
        query = query.filter(CustomerRiskDispute.status.in_(statuses))
    return query.all()


def _dispute_matches_report(
    dispute: CustomerRiskDispute,
    report: CustomerRiskReport,
) -> bool:
    return bool(
        (
            report.phone_fingerprint
            and dispute.phone_fingerprint == report.phone_fingerprint
        )
        or (
            report.email_fingerprint
            and dispute.email_fingerprint == report.email_fingerprint
        )
    )


def _priority_score(
    report: CustomerRiskReport,
    open_disputes: int,
    reputation: dict[str, Any],
) -> int:
    base = {
        "pending": 50,
        "disputed": 80,
        "confirmed": 20,
        "dismissed": 0,
    }.get(report.status, 0)
    age_days = max(
        0,
        (datetime.utcnow() - (report.updated_at or report.created_at)).days,
    )
    score = base + min(20, age_days) + min(40, open_disputes * 20)
    if report.evidence_reference:
        score += 5
    # Low-confidence reporters are reviewed sooner to reduce the time an
    # unsupported signal can remain visible. Reputation never auto-dismisses.
    if reputation.get("level") == "watch" and report.status != "dismissed":
        score += 15
    return score


def _serialize_queue_report(
    report: CustomerRiskReport,
    *,
    organization_name: str | None,
    reporter_label: str | None,
    open_disputes: int,
    reputation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": report.id,
        "status": report.status,
        "reason": report.reason,
        "reporter_organization_id": report.reporter_organization_id,
        "reporter_organization_name": organization_name,
        "reporter_user_id": report.reporter_user_id,
        "reporter_label": reporter_label,
        "has_notes": bool(report.notes),
        "has_evidence": bool(report.evidence_reference),
        "open_disputes": open_disputes,
        "reporter_reputation": reputation,
        "priority_score": _priority_score(report, open_disputes, reputation),
        "created_at": _iso(report.created_at),
        "updated_at": _iso(report.updated_at),
    }


def get_customer_risk_moderation_stats(db: Session) -> dict[str, Any]:
    report_statuses = Counter(
        status for (status,) in db.query(CustomerRiskReport.status).all()
    )
    dispute_statuses = Counter(
        status for (status,) in db.query(CustomerRiskDispute.status).all()
    )
    return {
        "reports": {
            "total": sum(report_statuses.values()),
            "pending": report_statuses["pending"],
            "confirmed": report_statuses["confirmed"],
            "disputed": report_statuses["disputed"],
            "dismissed": report_statuses["dismissed"],
        },
        "disputes": {
            "total": sum(dispute_statuses.values()),
            "open": dispute_statuses["open"],
            "accepted": dispute_statuses["accepted"],
            "rejected": dispute_statuses["rejected"],
            "withdrawn": dispute_statuses["withdrawn"],
        },
        "limits": {
            "report_writes_24h": report_write_limit_24h(),
            "dispute_writes_24h": dispute_write_limit_24h(),
        },
    }


def list_customer_risk_moderation_reports(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 25,
    status: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    query = db.query(CustomerRiskReport)
    if status:
        query = query.filter(CustomerRiskReport.status == status)
    if reason:
        query = query.filter(CustomerRiskReport.reason == reason)
    total = query.count()
    reports = (
        query.order_by(
            CustomerRiskReport.updated_at.desc(),
            CustomerRiskReport.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    organization_ids = {row.reporter_organization_id for row in reports}
    user_ids = {row.reporter_user_id for row in reports if row.reporter_user_id}
    org_names = _organization_names(db, organization_ids)
    user_labels = _user_labels(db, user_ids)
    reputations = _reputation_map(db, organization_ids)
    open_disputes = _matching_disputes_for_reports(
        db,
        reports,
        statuses={"open"},
    )

    items = []
    for report in reports:
        dispute_count = sum(
            1 for dispute in open_disputes if _dispute_matches_report(dispute, report)
        )
        items.append(
            _serialize_queue_report(
                report,
                organization_name=org_names.get(report.reporter_organization_id),
                reporter_label=user_labels.get(report.reporter_user_id),
                open_disputes=dispute_count,
                reputation=reputations.get(
                    report.reporter_organization_id,
                    _reputation_from_counts(Counter()),
                ),
            )
        )
    items.sort(
        key=lambda item: (item["priority_score"], item["id"]),
        reverse=True,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _report_events(db: Session, report_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(CustomerRiskReportEvent)
        .filter(CustomerRiskReportEvent.report_id == report_id)
        .order_by(
            CustomerRiskReportEvent.created_at.desc(),
            CustomerRiskReportEvent.id.desc(),
        )
        .all()
    )
    user_labels = _user_labels(
        db,
        {row.actor_user_id for row in rows if row.actor_user_id},
    )
    return [
        {
            "id": row.id,
            "actor_role": row.actor_role,
            "actor_user_id": row.actor_user_id,
            "actor_label": user_labels.get(row.actor_user_id),
            "action": row.action,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "note": row.note,
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]


def _serialize_dispute_for_admin(
    dispute: CustomerRiskDispute,
    *,
    organization_name: str | None = None,
    requester_label: str | None = None,
) -> dict[str, Any]:
    return {
        "id": dispute.id,
        "status": dispute.status,
        "requester_organization_id": dispute.requester_organization_id,
        "requester_organization_name": organization_name,
        "requester_user_id": dispute.requester_user_id,
        "requester_label": requester_label,
        "local_customer_id": dispute.local_customer_id,
        "statement": dispute.statement,
        "evidence_reference": dispute.evidence_reference,
        "resolution_note": dispute.resolution_note,
        "resolved_by_user_id": dispute.resolved_by_user_id,
        "resolved_at": _iso(dispute.resolved_at),
        "created_at": _iso(dispute.created_at),
        "updated_at": _iso(dispute.updated_at),
    }


def get_customer_risk_moderation_report(
    db: Session,
    report_id: int,
) -> dict[str, Any]:
    report = db.query(CustomerRiskReport).filter(CustomerRiskReport.id == report_id).first()
    if report is None:
        raise CustomerRiskModerationNotFoundError("Risk report not found")

    organization = (
        db.query(Organization)
        .filter(Organization.id == report.reporter_organization_id)
        .first()
    )
    reporter = (
        db.query(User).filter(User.id == report.reporter_user_id).first()
        if report.reporter_user_id
        else None
    )
    customer = (
        db.query(Customer).filter(Customer.id == report.local_customer_id).first()
        if report.local_customer_id
        else None
    )
    disputes = [
        row
        for row in _matching_disputes_for_reports(db, [report])
        if row.requester_organization_id != report.reporter_organization_id
    ]
    dispute_orgs = _organization_names(
        db,
        {row.requester_organization_id for row in disputes},
    )
    dispute_users = _user_labels(
        db,
        {row.requester_user_id for row in disputes if row.requester_user_id},
    )
    reputation = _reputation_map(db, {report.reporter_organization_id}).get(
        report.reporter_organization_id,
        _reputation_from_counts(Counter()),
    )

    return {
        "id": report.id,
        "status": report.status,
        "reason": report.reason,
        "notes": report.notes,
        "evidence_reference": report.evidence_reference,
        "reporter": {
            "organization_id": report.reporter_organization_id,
            "organization_name": organization.name if organization else None,
            "user_id": report.reporter_user_id,
            "user_label": (
                ((reporter.name or "").strip() or reporter.email)
                if reporter
                else None
            ),
            "store_id": report.reporter_store_id,
            "reputation": reputation,
        },
        "customer": _customer_snapshot(customer),
        "disputes": [
            _serialize_dispute_for_admin(
                row,
                organization_name=dispute_orgs.get(row.requester_organization_id),
                requester_label=dispute_users.get(row.requester_user_id),
            )
            for row in sorted(
                disputes,
                key=lambda item: (item.updated_at, item.id),
                reverse=True,
            )
        ],
        "audit": _report_events(db, report.id),
        "created_at": _iso(report.created_at),
        "updated_at": _iso(report.updated_at),
    }


def moderate_customer_risk_report(
    db: Session,
    *,
    report_id: int,
    admin_user_id: int,
    action: str,
    note: str,
) -> dict[str, Any]:
    if action not in REPORT_ACTIONS:
        raise CustomerRiskModerationValidationError("Invalid moderation action")
    note = note.strip()
    if len(note) < 5 or len(note) > 2000:
        raise CustomerRiskModerationValidationError(
            "Moderation note must contain between 5 and 2000 characters"
        )

    report = db.query(CustomerRiskReport).filter(CustomerRiskReport.id == report_id).first()
    if report is None:
        raise CustomerRiskModerationNotFoundError("Risk report not found")

    new_status, event_action = REPORT_ACTIONS[action]
    old_status = report.status
    if old_status != new_status:
        report.status = new_status
        report.updated_at = datetime.utcnow()
        add_report_event(
            db,
            report_id=report.id,
            organization_id=report.reporter_organization_id,
            actor_user_id=admin_user_id,
            actor_role="platform_admin",
            action=event_action,
            from_status=old_status,
            to_status=new_status,
            note=note,
        )
        db.commit()
    return get_customer_risk_moderation_report(db, report.id)


def list_customer_risk_disputes(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 25,
    status: str | None = "open",
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    query = db.query(CustomerRiskDispute)
    if status:
        query = query.filter(CustomerRiskDispute.status == status)
    total = query.count()
    rows = (
        query.order_by(
            CustomerRiskDispute.updated_at.desc(),
            CustomerRiskDispute.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    org_names = _organization_names(
        db,
        {row.requester_organization_id for row in rows},
    )
    user_labels = _user_labels(
        db,
        {row.requester_user_id for row in rows if row.requester_user_id},
    )
    return {
        "items": [
            _serialize_dispute_for_admin(
                row,
                organization_name=org_names.get(row.requester_organization_id),
                requester_label=user_labels.get(row.requester_user_id),
            )
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def _matching_reports_for_dispute(
    db: Session,
    dispute: CustomerRiskDispute,
) -> list[CustomerRiskReport]:
    clauses = []
    if dispute.phone_fingerprint:
        clauses.append(
            CustomerRiskReport.phone_fingerprint == dispute.phone_fingerprint
        )
    if dispute.email_fingerprint:
        clauses.append(
            CustomerRiskReport.email_fingerprint == dispute.email_fingerprint
        )
    if not clauses:
        return []
    return (
        db.query(CustomerRiskReport)
        .filter(
            or_(*clauses),
            CustomerRiskReport.reporter_organization_id
            != dispute.requester_organization_id,
        )
        .all()
    )


def _dispute_events(db: Session, dispute_id: int) -> list[dict[str, Any]]:
    rows = (
        db.query(CustomerRiskDisputeEvent)
        .filter(CustomerRiskDisputeEvent.dispute_id == dispute_id)
        .order_by(
            CustomerRiskDisputeEvent.created_at.desc(),
            CustomerRiskDisputeEvent.id.desc(),
        )
        .all()
    )
    user_labels = _user_labels(
        db,
        {row.actor_user_id for row in rows if row.actor_user_id},
    )
    return [
        {
            "id": row.id,
            "actor_role": row.actor_role,
            "actor_user_id": row.actor_user_id,
            "actor_label": user_labels.get(row.actor_user_id),
            "action": row.action,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "note": row.note,
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]


def get_customer_risk_dispute_detail(
    db: Session,
    dispute_id: int,
) -> dict[str, Any]:
    dispute = (
        db.query(CustomerRiskDispute)
        .filter(CustomerRiskDispute.id == dispute_id)
        .first()
    )
    if dispute is None:
        raise CustomerRiskModerationNotFoundError("Risk dispute not found")

    organization = (
        db.query(Organization)
        .filter(Organization.id == dispute.requester_organization_id)
        .first()
    )
    requester = (
        db.query(User).filter(User.id == dispute.requester_user_id).first()
        if dispute.requester_user_id
        else None
    )
    customer = (
        db.query(Customer).filter(Customer.id == dispute.local_customer_id).first()
        if dispute.local_customer_id
        else None
    )
    matching_reports = _matching_reports_for_dispute(db, dispute)
    org_names = _organization_names(
        db,
        {row.reporter_organization_id for row in matching_reports},
    )

    payload = _serialize_dispute_for_admin(
        dispute,
        organization_name=organization.name if organization else None,
        requester_label=(
            ((requester.name or "").strip() or requester.email)
            if requester
            else None
        ),
    )
    payload["customer"] = _customer_snapshot(customer)
    payload["matching_reports"] = [
        {
            "id": row.id,
            "status": row.status,
            "reason": row.reason,
            "reporter_organization_id": row.reporter_organization_id,
            "reporter_organization_name": org_names.get(row.reporter_organization_id),
            "has_evidence": bool(row.evidence_reference),
            "updated_at": _iso(row.updated_at),
        }
        for row in matching_reports
    ]
    payload["audit"] = _dispute_events(db, dispute.id)
    return payload


def resolve_customer_risk_dispute(
    db: Session,
    *,
    dispute_id: int,
    admin_user_id: int,
    outcome: str,
    note: str,
) -> dict[str, Any]:
    if outcome not in {"accepted", "rejected"}:
        raise CustomerRiskModerationValidationError("Invalid dispute outcome")
    note = note.strip()
    if len(note) < 5 or len(note) > 2000:
        raise CustomerRiskModerationValidationError(
            "Resolution note must contain between 5 and 2000 characters"
        )

    dispute = (
        db.query(CustomerRiskDispute)
        .filter(CustomerRiskDispute.id == dispute_id)
        .first()
    )
    if dispute is None:
        raise CustomerRiskModerationNotFoundError("Risk dispute not found")
    if dispute.status != "open":
        raise CustomerRiskModerationValidationError("Only open disputes can be resolved")

    if outcome == "accepted":
        for report in _matching_reports_for_dispute(db, dispute):
            if report.status in {"pending", "confirmed"}:
                old_status = report.status
                report.status = "disputed"
                report.updated_at = datetime.utcnow()
                add_report_event(
                    db,
                    report_id=report.id,
                    organization_id=report.reporter_organization_id,
                    actor_user_id=admin_user_id,
                    actor_role="platform_admin",
                    action="moderation_disputed",
                    from_status=old_status,
                    to_status="disputed",
                    note=f"Accepted dispute #{dispute.id}: {note}",
                )

    dispute.status = outcome
    dispute.resolution_note = note
    dispute.resolved_by_user_id = admin_user_id
    dispute.resolved_at = datetime.utcnow()
    dispute.updated_at = dispute.resolved_at
    add_dispute_event(
        db,
        dispute_id=dispute.id,
        organization_id=dispute.requester_organization_id,
        actor_user_id=admin_user_id,
        actor_role="platform_admin",
        action="dispute_accepted" if outcome == "accepted" else "dispute_rejected",
        from_status="open",
        to_status=outcome,
        note=note,
    )
    db.commit()
    return get_customer_risk_dispute_detail(db, dispute.id)
