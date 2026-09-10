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

# Country calling codes and conservative national-number lengths. Global risk
# matching favors false negatives over cross-person false positives: a local
# number is fingerprinted only when its country is known and its length is
# plausible for that market.
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
NATIONAL_NUMBER_LENGTHS = {
    "AR": {10, 11},
    "BO": {8},
    "BR": {10, 11},
    "CA": {10},
    "CL": {9},
    "CO": {10},
    "CR": {8},
    "DO": {10},
    "EC": {9},
    "GT": {8},
    "HN": {8},
    "MX": {10},
    "NI": {8},
    "PA": {7, 8},
    "PE": {9},
    "PR": {10},
    "PY": {9},
    "SV": {8},
    "US": {10},
    "UY": {8},
    "VE": {10},
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
    """Return a conservative E.164-like digit string for risk matching.

    Explicit international numbers are accepted when they fit E.164 length
    bounds. Local numbers require a known country and a plausible national
    length. A single domestic trunk ``0`` is removed only when doing so yields
    a valid national length (notably useful for Brazil).
    """
    raw = (value or "").strip()
    if not raw:
        return ""

    digits = re.sub(r"\D", "", raw)
    explicit_international = raw.startswith("+") or digits.startswith("00")
    if digits.startswith("00"):
        digits = digits[2:]

    if explicit_international:
        return digits if 8 <= len(digits) <= 15 else ""

    country = (country_code or "").upper()
    dial_code = COUNTRY_DIAL_CODES.get(country)
    national_lengths = NATIONAL_NUMBER_LENGTHS.get(country)
    if not dial_code or not national_lengths:
        # A local number without a trustworthy country must never participate
        # in a global cross-account match.
        return ""

    # Accept a country-prefixed number even if the user omitted '+'.
    if digits.startswith(dial_code):
        national = digits[len(dial_code):]
        if len(national) in national_lengths:
            return digits

    national = digits
    if national.startswith("0") and len(national[1:]) in national_lengths:
        national = national[1:]

    if len(national) not in national_lengths:
        return ""
    return f"{dial_code}{national}"


def _fingerprint_key() -> bytes:
    """Return the dedicated, stable key for global identifier matching.

    This feature intentionally does not fall back to provider token-encryption
    keys. Reusing or rotating an unrelated integration key would silently break
    historical matching. Deployments must configure a dedicated secret once and
    keep it stable for the lifetime of stored risk fingerprints.
    """
    raw = (os.getenv("CUSTOMER_RISK_HMAC_SECRET") or "").strip()
    if not raw:
        raise CustomerRiskConfigurationError(
            "CUSTOMER_RISK_HMAC_SECRET is not configured"
        )
    if len(raw.encode("utf-8")) < 32:
        raise CustomerRiskConfigurationError(
            "CUSTOMER_RISK_HMAC_SECRET must contain at least 32 bytes"
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


def _dedupe_reports(
    *groups: Iterable[CustomerRiskReport],
) -> list[CustomerRiskReport]:
    deduped: dict[int, CustomerRiskReport] = {}
    for group in groups:
        for report in group:
            if report.id is not None:
                deduped[report.id] = report
    return list(deduped.values())


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


def _latest_report(
    reports: Iterable[CustomerRiskReport],
) -> CustomerRiskReport | None:
    return max(
        reports,
        key=lambda item: (
            item.updated_at or item.created_at or datetime.min,
            item.id or 0,
        ),
        default=None,
    )


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


def _own_reports_for_customer(
    *,
    db: Session,
    organization_id: int,
    customer_id: int,
) -> list[CustomerRiskReport]:
    return (
        db.query(CustomerRiskReport)
        .filter(
            CustomerRiskReport.reporter_organization_id == organization_id,
            CustomerRiskReport.local_customer_id == customer_id,
        )
        .all()
    )


def _reports_for_subject(
    *,
    db: Session,
    organization_id: int,
    customer_id: int,
    phone_fingerprint: str | None,
    email_fingerprint: str | None,
) -> list[CustomerRiskReport]:
    """Match shared identity plus the viewer's durable local-customer link.

    The local link ensures that editing phone/email cannot orphan the reporting
    organization's own report. It does not make an old fingerprint follow a
    newly entered identifier; only an explicit report update does that.
    """
    return _dedupe_reports(
        _reports_for_fingerprints(db, phone_fingerprint, email_fingerprint),
        _own_reports_for_customer(
            db=db,
            organization_id=organization_id,
            customer_id=customer_id,
        ),
    )


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
        reports=_reports_for_subject(
            db=db,
            organization_id=organization_id,
            customer_id=customer.id,
            phone_fingerprint=phone_fp,
            email_fingerprint=email_fp,
        ),
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
    shared_reports = (
        db.query(CustomerRiskReport).filter(clause).all()
        if clause is not None
        else []
    )
    subject_ids = [subject_id for subject_id, *_ in subjects]
    own_reports = (
        db.query(CustomerRiskReport)
        .filter(
            CustomerRiskReport.reporter_organization_id == organization_id,
            CustomerRiskReport.local_customer_id.in_(subject_ids),
        )
        .all()
    )

    result: dict[int, dict[str, Any]] = {}
    for subject_id, _phone, _email, _country in subjects:
        phone_fp, email_fp = fingerprints[subject_id]
        identity_matches = [
            report
            for report in shared_reports
            if (
                phone_fp
                and report.phone_fingerprint == phone_fp
            )
            or (
                email_fp
                and report.email_fingerprint == email_fp
            )
        ]
        durable_own = [
            report
            for report in own_reports
            if report.local_customer_id == subject_id
        ]
        result[subject_id] = _build_summary(
            reports=_dedupe_reports(identity_matches, durable_own),
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
            {
                **item,
                "customer_risk": summaries.get(
                    int(item["id"]),
                    _empty_summary(),
                ),
            }
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


def _find_current_organization_report(
    *,
    db: Session,
    organization_id: int,
    customer_id: int,
    phone_fingerprint: str | None,
    email_fingerprint: str | None,
) -> CustomerRiskReport | None:
    """Prefer durable customer linkage, then fall back to identifier matching."""
    linked = _own_reports_for_customer(
        db=db,
        organization_id=organization_id,
        customer_id=customer_id,
    )
    current = _latest_report(linked)
    if current is not None:
        return current

    identity_matches = [
        report
        for report in _reports_for_fingerprints(
            db,
            phone_fingerprint,
            email_fingerprint,
        )
        if report.reporter_organization_id == organization_id
    ]
    return _latest_report(identity_matches)


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

    existing = _find_current_organization_report(
        db=db,
        organization_id=organization_id,
        customer_id=customer.id,
        phone_fingerprint=phone_fp,
        email_fingerprint=email_fp,
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
        # An explicit report update is the only operation allowed to move the
        # shared fingerprints to newly edited customer identifiers.
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
    current = _find_current_organization_report(
        db=db,
        organization_id=organization_id,
        customer_id=customer.id,
        phone_fingerprint=phone_fp,
        email_fingerprint=email_fp,
    )
    if current is None:
        raise CustomerRiskNotFoundError("Current organization report not found")

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
