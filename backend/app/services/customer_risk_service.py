"""Privacy-preserving shared customer-risk signals.

A report is a cautionary signal, never an automated finding of wrongdoing.
Cross-organization matching uses keyed HMAC fingerprints. Raw phone/email
values, reporter identity, notes, and evidence are never exposed across
organizations.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from collections import Counter
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..model_domains.customer_risk import CustomerRiskReport
from ..models import Customer, Order


REPORT_REASONS = {
    "suspected_fraud",
    "payment_abuse",
    "delivery_claim",
    "identity_mismatch",
    "abusive_behavior",
    "other",
}
ACTIVE_STATUSES = {"pending", "confirmed", "disputed"}

# Covers Diaglob's primary Americas markets. Unknown countries still match
# when the source already provides an international-format phone number.
COUNTRY_DIAL_CODES = {
    "AR": "54",
    "BO": "591",
    "BR": "55",
    "CA": "1",
    "CL": "56",
    "CO": "57",
    "CR": "506",
    "DO": "1",
    "EC": "593",
    "GT": "502",
    "HN": "504",
    "MX": "52",
    "NI": "505",
    "PA": "507",
    "PE": "51",
    "PR": "1",
    "PY": "595",
    "SV": "503",
    "US": "1",
    "UY": "598",
    "VE": "58",
}


class CustomerRiskError(Exception):
    """Base error for customer-risk business rules."""


class CustomerRiskNotFoundError(CustomerRiskError):
    pass


class CustomerRiskAccessError(CustomerRiskError):
    pass


class CustomerRiskValidationError(CustomerRiskError):
    pass


class CustomerRiskConfigurationError(CustomerRiskError):
    pass


def normalize_email(value: str | None) -> str:
    return (value or "").strip().casefold()


def normalize_phone(value: str | None, country_code: str | None = None) -> str:
    """Normalize a phone for deterministic matching without changing storage.

    International numbers remain intact. For common Americas markets, local
    7-11 digit numbers receive the known country calling code.
    """
    raw = (value or "").strip()
    if not raw:
        return ""

    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) < 7:
        return ""

    explicit_international = raw.startswith("+") or raw.startswith("00")
    dial_code = COUNTRY_DIAL_CODES.get((country_code or "").upper())

    if dial_code and not explicit_international:
        local = digits.lstrip("0") or digits
        if not (
            local.startswith(dial_code)
            and len(local) > len(dial_code) + 7
        ):
            digits = f"{dial_code}{local}"
        else:
            digits = local

    return digits


def _fingerprint_key() -> bytes:
    """Return a domain-separated key for global identifier matching.

    CUSTOMER_RISK_HMAC_SECRET is preferred. Existing token-encryption secrets
    are accepted only as a deployment-compatibility fallback and are first
    domain-separated through SHA-256, so the derived key is not the encryption
    key itself.
    """
    raw = (
        os.getenv("CUSTOMER_RISK_HMAC_SECRET")
        or os.getenv("SHOPIFY_TOKEN_ENCRYPTION_KEY")
        or os.getenv("WHATSAPP_TOKEN_ENCRYPTION_KEY")
        or os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY")
    )
    if not raw:
        raise CustomerRiskConfigurationError(
            "Customer risk fingerprint secret is not configured"
        )

    return hashlib.sha256(
        b"diaglob.customer-risk.v1\x00" + raw.encode("utf-8")
    ).digest()


def _fingerprint(kind: str, normalized_value: str) -> str | None:
    if not normalized_value:
        return None
    return hmac.new(
        _fingerprint_key(),
        f"{kind}:{normalized_value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def customer_fingerprints(
    *,
    phone: str | None,
    email: str | None,
    country_code: str | None,
) -> tuple[str | None, str | None]:
    return (
        _fingerprint("phone", normalize_phone(phone, country_code)),
        _fingerprint("email", normalize_email(email)),
    )


def _empty_summary(*, available: bool = True) -> dict[str, Any]:
    return {
        "available": available,
        "alert": False,
        "severity": "none",
        "reporting_organizations": 0,
        "external_reporting_organizations": 0,
        "confirmed_reports": 0,
        "pending_reports": 0,
        "disputed_reports": 0,
        "reason_counts": {},
        "last_reported_at": None,
        "matched_on": [],
        "reported_by_current_organization": False,
        "current_organization_report": None,
    }


def _matching_clause(
    phone_fingerprints: Iterable[str],
    email_fingerprints: Iterable[str],
):
    phone_values = list(phone_fingerprints)
    email_values = list(email_fingerprints)
    clauses = []
    if phone_values:
        clauses.append(CustomerRiskReport.phone_fingerprint.in_(phone_values))
    if email_values:
        clauses.append(CustomerRiskReport.email_fingerprint.in_(email_values))
    if not clauses:
        return None
    return or_(*clauses)


def _latest_per_organization(
    reports: Iterable[CustomerRiskReport],
) -> list[CustomerRiskReport]:
    latest: dict[int, CustomerRiskReport] = {}
    for report in sorted(
        reports,
        key=lambda item: (
            item.updated_at or item.created_at or datetime.min,
            item.id or 0,
        ),
        reverse=True,
    ):
        latest.setdefault(report.reporter_organization_id, report)
    return list(latest.values())


def _build_summary(
    *,
    reports: Iterable[CustomerRiskReport],
    viewer_organization_id: int,
    phone_fingerprint: str | None,
    email_fingerprint: str | None,
) -> dict[str, Any]:
    latest = _latest_per_organization(reports)
    active = [item for item in latest if item.status in ACTIVE_STATUSES]
    if not active:
        return _empty_summary()

    statuses = Counter(item.status for item in active)
    reasons = Counter(item.reason for item in active)
    reporting_orgs = {item.reporter_organization_id for item in active}
    my_report = next(
        (
            item
            for item in active
            if item.reporter_organization_id == viewer_organization_id
        ),
        None,
    )

    matched_on: list[str] = []
    if phone_fingerprint and any(
        item.phone_fingerprint == phone_fingerprint for item in active
    ):
        matched_on.append("phone")
    if email_fingerprint and any(
        item.email_fingerprint == email_fingerprint for item in active
    ):
        matched_on.append("email")

    if statuses["confirmed"] > 0 or len(reporting_orgs) >= 2:
        severity = "high"
    elif statuses["pending"] > 0:
        severity = "elevated"
    else:
        severity = "notice"

    last_reported = max(
        (item.updated_at or item.created_at for item in active),
        default=None,
    )

    current_org_payload = None
    if my_report is not None:
        current_org_payload = {
            "id": my_report.id,
            "reason": my_report.reason,
            "status": my_report.status,
            "notes": my_report.notes,
            "evidence_reference": my_report.evidence_reference,
            "created_at": (
                my_report.created_at.isoformat() if my_report.created_at else None
            ),
            "updated_at": (
                my_report.updated_at.isoformat() if my_report.updated_at else None
            ),
        }

    return {
        "available": True,
        "alert": True,
        "severity": severity,
        "reporting_organizations": len(reporting_orgs),
        "external_reporting_organizations": len(
            reporting_orgs - {viewer_organization_id}
        ),
        "confirmed_reports": statuses["confirmed"],
        "pending_reports": statuses["pending"],
        "disputed_reports": statuses["disputed"],
        "reason_counts": dict(sorted(reasons.items())),
        "last_reported_at": last_reported.isoformat() if last_reported else None,
        "matched_on": matched_on,
        "reported_by_current_organization": my_report is not None,
        "current_organization_report": current_org_payload,
    }


def _assert_customer_access(
    *,
    customer: Customer | None,
    organization_id: int,
    allowed_store_ids: list[int] | None,
) -> Customer:
    if customer is None or customer.organization_id != organization_id:
        raise CustomerRiskNotFoundError("Customer not found")

    if allowed_store_ids is not None:
        customer_store_ids = {
            profile.store_id for profile in customer.store_profiles
        }
        if not customer_store_ids.intersection(allowed_store_ids):
            raise CustomerRiskAccessError("Customer access denied")

    return customer


def _load_customer(
    *,
    db: Session,
    organization_id: int,
    customer_id: int,
    allowed_store_ids: list[int] | None,
) -> Customer:
    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.organization_id == organization_id,
        )
        .first()
    )
    return _assert_customer_access(
        customer=customer,
        organization_id=organization_id,
        allowed_store_ids=allowed_store_ids,
    )


def _reports_for_fingerprints(
    db: Session,
    phone_fingerprint: str | None,
    email_fingerprint: str | None,
) -> list[CustomerRiskReport]:
    clause = _matching_clause(
        [phone_fingerprint] if phone_fingerprint else [],
        [email_fingerprint] if email_fingerprint else [],
    )
    if clause is None:
        return []
    return db.query(CustomerRiskReport).filter(clause).all()


def get_customer_risk_summary(
    *,
    db: Session,
    organization_id: int,
    customer_id: int,
    allowed_store_ids: list[int] | None = None,
) -> dict[str, Any]:
    customer = _load_customer(
        db=db,
        organization_id=organization_id,
        customer_id=customer_id,
        allowed_store_ids=allowed_store_ids,
    )
    phone_fp, email_fp = customer_fingerprints(
        phone=customer.phone,
        email=customer.email,
        country_code=customer.country_code,
    )
    return _build_summary(
        reports=_reports_for_fingerprints(db, phone_fp, email_fp),
        viewer_organization_id=organization_id,
        phone_fingerprint=phone_fp,
        email_fingerprint=email_fp,
    )


def _safe_subject_summaries(
    *,
    db: Session,
    organization_id: int,
    subjects: list[tuple[int, str | None, str | None, str | None]],
) -> dict[int, dict[str, Any]]:
    """Batch risk summaries; configuration failure never breaks core reads."""
    if not subjects:
        return {}

    try:
        fingerprints: dict[int, tuple[str | None, str | None]] = {
            subject_id: customer_fingerprints(
                phone=phone,
                email=email,
                country_code=country_code,
            )
            for subject_id, phone, email, country_code in subjects
        }
    except CustomerRiskConfigurationError:
        return {
            subject_id: _empty_summary(available=False)
            for subject_id, *_ in subjects
        }

    phone_values = {phone for phone, _ in fingerprints.values() if phone}
    email_values = {email for _, email in fingerprints.values() if email}
    clause = _matching_clause(phone_values, email_values)
    reports = db.query(CustomerRiskReport).filter(clause).all() if clause is not None else []

    result: dict[int, dict[str, Any]] = {}
    for subject_id, _phone, _email, _country in subjects:
        phone_fp, email_fp = fingerprints[subject_id]
        matched = [
            report
            for report in reports
            if (
                phone_fp
                and report.phone_fingerprint == phone_fp
            )
            or (
                email_fp
                and report.email_fingerprint == email_fp
            )
        ]
        result[subject_id] = _build_summary(
            reports=matched,
            viewer_organization_id=organization_id,
            phone_fingerprint=phone_fp,
            email_fingerprint=email_fp,
        )
    return result


def enrich_customer_list_response(
    *,
    db: Session,
    organization_id: int,
    response: dict[str, Any],
) -> dict[str, Any]:
    items = response.get("items") or []
    subjects = [
        (
            int(item["id"]),
            item.get("phone"),
            item.get("email"),
            item.get("country_code"),
        )
        for item in items
    ]
    summaries = _safe_subject_summaries(
        db=db,
        organization_id=organization_id,
        subjects=subjects,
    )
    return {
        **response,
        "items": [
            {**item, "customer_risk": summaries.get(int(item["id"]), _empty_summary())}
            for item in items
        ],
    }


def enrich_customer_detail_response(
    *,
    db: Session,
    organization_id: int,
    response: dict[str, Any],
) -> dict[str, Any]:
    subject_id = int(response["id"])
    summaries = _safe_subject_summaries(
        db=db,
        organization_id=organization_id,
        subjects=[(
            subject_id,
            response.get("phone"),
            response.get("email"),
            response.get("country_code"),
        )],
    )
    return {**response, "customer_risk": summaries[subject_id]}


def enrich_conversation_payloads(
    *,
    db: Session,
    organization_id: int,
    conversations: list[Any],
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    customers = {
        conversation.customer.id: conversation.customer
        for conversation in conversations
        if conversation.customer is not None
    }
    summaries = _safe_subject_summaries(
        db=db,
        organization_id=organization_id,
        subjects=[
            (customer.id, customer.phone, customer.email, customer.country_code)
            for customer in customers.values()
        ],
    )
    enriched = []
    for conversation, payload in zip(conversations, payloads):
        customer_id = conversation.customer_id
        enriched.append({
            **payload,
            "customer_id": customer_id,
            "customer_risk": summaries.get(customer_id, _empty_summary()),
        })
    return enriched


def enrich_order_payloads(
    *,
    db: Session,
    organization_id: int,
    store_id: int,
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    order_ids = [int(item["id"]) for item in payloads]
    if not order_ids:
        return payloads

    orders = (
        db.query(Order)
        .filter(
            Order.id.in_(order_ids),
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
        .all()
    )
    customer_ids = {order.customer_id for order in orders if order.customer_id}
    customers = (
        db.query(Customer)
        .filter(
            Customer.organization_id == organization_id,
            Customer.id.in_(customer_ids),
        )
        .all()
        if customer_ids
        else []
    )
    customer_map = {customer.id: customer for customer in customers}
    summaries = _safe_subject_summaries(
        db=db,
        organization_id=organization_id,
        subjects=[
            (customer.id, customer.phone, customer.email, customer.country_code)
            for customer in customers
        ],
    )
    order_map = {order.id: order for order in orders}

    result = []
    for payload in payloads:
        order = order_map.get(int(payload["id"]))
        customer_id = order.customer_id if order else None
        result.append({
            **payload,
            "customer_id": customer_id,
            "customer_risk": (
                summaries.get(customer_id, _empty_summary())
                if customer_id
                else _empty_summary()
            ),
        })
    return result


def report_customer(
    *,
    db: Session,
    organization_id: int,
    reporter_user_id: int,
    customer_id: int,
    reason: str,
    notes: str | None = None,
    evidence_reference: str | None = None,
    reporter_store_id: int | None = None,
    allowed_store_ids: list[int] | None = None,
) -> dict[str, Any]:
    if reason not in REPORT_REASONS:
        raise CustomerRiskValidationError("Invalid report reason")
    if notes and len(notes) > 2000:
        raise CustomerRiskValidationError("Notes must be 2000 characters or fewer")
    if evidence_reference and len(evidence_reference) > 1000:
        raise CustomerRiskValidationError(
            "Evidence reference must be 1000 characters or fewer"
        )
    if (
        reporter_store_id is not None
        and allowed_store_ids is not None
        and reporter_store_id not in allowed_store_ids
    ):
        raise CustomerRiskAccessError("Store access denied")

    customer = _load_customer(
        db=db,
        organization_id=organization_id,
        customer_id=customer_id,
        allowed_store_ids=allowed_store_ids,
    )
    if reporter_store_id is not None:
        valid_store_ids = {profile.store_id for profile in customer.store_profiles}
        if reporter_store_id not in valid_store_ids:
            raise CustomerRiskValidationError(
                "Customer does not belong to the selected store"
            )

    phone_fp, email_fp = customer_fingerprints(
        phone=customer.phone,
        email=customer.email,
        country_code=customer.country_code,
    )
    if not phone_fp and not email_fp:
        raise CustomerRiskValidationError(
            "Customer needs a phone or email before a risk report can be shared"
        )

    reports = _reports_for_fingerprints(db, phone_fp, email_fp)
    own_reports = [
        item
        for item in reports
        if item.reporter_organization_id == organization_id
    ]
    existing = (
        _latest_per_organization(own_reports)[0]
        if own_reports
        else None
    )

    if existing is None:
        existing = CustomerRiskReport(
            reporter_organization_id=organization_id,
            reporter_store_id=reporter_store_id,
            reporter_user_id=reporter_user_id,
            local_customer_id=customer.id,
            phone_fingerprint=phone_fp,
            email_fingerprint=email_fp,
            reason=reason,
            status="pending",
            notes=(notes or "").strip() or None,
            evidence_reference=(evidence_reference or "").strip() or None,
        )
        db.add(existing)
    else:
        existing.reporter_store_id = reporter_store_id
        existing.reporter_user_id = reporter_user_id
        existing.local_customer_id = customer.id
        existing.phone_fingerprint = phone_fp
        existing.email_fingerprint = email_fp
        existing.reason = reason
        existing.status = "pending"
        existing.notes = (notes or "").strip() or None
        existing.evidence_reference = (
            (evidence_reference or "").strip() or None
        )
        existing.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(existing)

    return get_customer_risk_summary(
        db=db,
        organization_id=organization_id,
        customer_id=customer.id,
        allowed_store_ids=allowed_store_ids,
    )


def dismiss_current_organization_report(
    *,
    db: Session,
    organization_id: int,
    reporter_user_id: int,
    customer_id: int,
    allowed_store_ids: list[int] | None = None,
) -> dict[str, Any]:
    customer = _load_customer(
        db=db,
        organization_id=organization_id,
        customer_id=customer_id,
        allowed_store_ids=allowed_store_ids,
    )
    phone_fp, email_fp = customer_fingerprints(
        phone=customer.phone,
        email=customer.email,
        country_code=customer.country_code,
    )
    own_reports = [
        report
        for report in _reports_for_fingerprints(db, phone_fp, email_fp)
        if report.reporter_organization_id == organization_id
    ]
    if not own_reports:
        raise CustomerRiskNotFoundError("Current organization report not found")

    current = _latest_per_organization(own_reports)[0]
    current.status = "dismissed"
    current.reporter_user_id = reporter_user_id
    current.updated_at = datetime.utcnow()
    db.commit()

    return get_customer_risk_summary(
        db=db,
        organization_id=organization_id,
        customer_id=customer.id,
        allowed_store_ids=allowed_store_ids,
    )
