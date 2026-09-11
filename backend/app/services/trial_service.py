"""Merchant trial lifecycle and external-store anti-abuse rules."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..model_domains.trials import TrialEntitlement, TrialIdentity
from ..models import Organization

TRIAL_DAYS = 7
TRIAL_AI_RESPONSES = 1000
PAID_PLANS = {"starter", "growth", "pro", "scale", "agency", "enterprise"}
ACTIVE_PAID_STATUSES = {"active", "trialing"}


class TrialIdentityAlreadyUsed(Exception):
    """Raised when a real commerce store has already consumed a Diaglob trial."""


@dataclass(frozen=True)
class TrialStatus:
    status: str
    started_at: datetime | None
    ends_at: datetime | None
    days_remaining: int | None
    ai_response_limit: int


def _normalize_provider(provider: str) -> str:
    return (provider or "").strip().lower()


def _normalize_external_identity(provider: str, external_identity: str) -> str:
    normalized_provider = _normalize_provider(provider)
    value = (external_identity or "").strip().lower().rstrip("/")
    if normalized_provider == "shopify":
        value = value.removeprefix("https://").removeprefix("http://")
    if not normalized_provider or not value:
        raise ValueError("provider and external identity are required")
    return value


def hash_trial_identity(provider: str, external_identity: str) -> str:
    normalized_provider = _normalize_provider(provider)
    normalized_identity = _normalize_external_identity(provider, external_identity)
    payload = f"{normalized_provider}:{normalized_identity}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_paid_active(organization: Organization) -> bool:
    plan = (organization.plan or "none").strip().lower()
    status = (organization.subscription_status or "").strip().lower()
    return plan in PAID_PLANS and status in ACTIVE_PAID_STATUSES


def get_trial_entitlement(
    db: Session,
    organization_id: int,
) -> TrialEntitlement | None:
    return (
        db.query(TrialEntitlement)
        .filter(TrialEntitlement.organization_id == organization_id)
        .first()
    )


def create_pending_trial(
    db: Session,
    organization: Organization,
    *,
    now: datetime | None = None,
) -> TrialEntitlement:
    existing = get_trial_entitlement(db, organization.id)
    if existing:
        return existing

    current = now or datetime.utcnow()
    entitlement = TrialEntitlement(
        organization_id=organization.id,
        status="pending",
        ai_response_limit=TRIAL_AI_RESPONSES,
        created_at=current,
        updated_at=current,
    )
    db.add(entitlement)

    # A pending trial can only bootstrap a commerce store. The 7-day clock does
    # not start until a real provider identity is verified through OAuth.
    organization.plan = "trial"
    organization.subscription_status = "trial_pending"
    db.flush()
    return entitlement


def refresh_trial_state(
    db: Session,
    organization: Organization,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> TrialEntitlement | None:
    entitlement = get_trial_entitlement(db, organization.id)
    if not entitlement:
        return None

    current = now or datetime.utcnow()
    changed = False

    if _is_paid_active(organization) and entitlement.status in {"pending", "active"}:
        entitlement.status = "converted"
        entitlement.converted_at = entitlement.converted_at or current
        entitlement.updated_at = current
        changed = True
    elif (
        entitlement.status == "active"
        and entitlement.ends_at is not None
        and entitlement.ends_at <= current
    ):
        entitlement.status = "expired"
        entitlement.updated_at = current
        if (organization.plan or "").strip().lower() == "trial":
            organization.plan = "none"
            organization.subscription_status = "trial_expired"
        changed = True

    if changed:
        if commit:
            db.commit()
            db.refresh(entitlement)
            db.refresh(organization)
        else:
            db.flush()

    return entitlement


def _get_identity(
    db: Session,
    provider: str,
    identity_hash: str,
) -> TrialIdentity | None:
    return (
        db.query(TrialIdentity)
        .filter(
            TrialIdentity.provider == _normalize_provider(provider),
            TrialIdentity.identity_hash == identity_hash,
        )
        .first()
    )


def activate_trial_for_verified_store(
    db: Session,
    *,
    organization_id: int,
    store_id: int,
    provider: str,
    external_identity: str,
    now: datetime | None = None,
) -> dict:
    """Claim a verified commerce identity and activate a pending 7-day trial.

    Paid organizations may connect a store that previously consumed a trial; they do
    not receive another trial. Trial organizations are rejected if the same provider
    store was first claimed by another organization.
    """
    organization = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .first()
    )
    if not organization:
        raise ValueError("Organization not found")

    current = now or datetime.utcnow()
    provider_key = _normalize_provider(provider)
    identity_hash = hash_trial_identity(provider_key, external_identity)
    identity = _get_identity(db, provider_key, identity_hash)

    if identity and identity.first_organization_id != organization.id:
        identity.last_seen_at = current
        if not _is_paid_active(organization):
            entitlement = get_trial_entitlement(db, organization.id)
            if entitlement and entitlement.status in {"pending", "active"}:
                entitlement.status = "blocked"
                entitlement.blocked_at = current
                entitlement.updated_at = current
            if (organization.plan or "").strip().lower() == "trial":
                organization.plan = "none"
                organization.subscription_status = "trial_blocked"
            db.flush()
            raise TrialIdentityAlreadyUsed("TRIAL_STORE_ALREADY_USED")

        return {
            "allowed": True,
            "trial_activated": False,
            "reason": "paid_organization",
        }

    entitlement = get_trial_entitlement(db, organization.id)

    if identity is None:
        identity = TrialIdentity(
            provider=provider_key,
            identity_hash=identity_hash,
            first_organization_id=organization.id,
            first_store_id=store_id,
            trial_entitlement_id=entitlement.id if entitlement else None,
            first_seen_at=current,
            last_seen_at=current,
            trial_consumed_at=current,
        )
        db.add(identity)
    else:
        identity.last_seen_at = current

    if _is_paid_active(organization):
        db.flush()
        return {
            "allowed": True,
            "trial_activated": False,
            "reason": "paid_organization",
        }

    if entitlement is None:
        entitlement = create_pending_trial(db, organization, now=current)

    if entitlement.status == "pending":
        entitlement.status = "active"
        entitlement.started_at = current
        entitlement.ends_at = current + timedelta(days=TRIAL_DAYS)
        entitlement.activated_by_provider = provider_key
        entitlement.activated_by_identity_hash = identity_hash
        entitlement.updated_at = current
        organization.plan = "trial"
        organization.subscription_status = "trialing"
        db.flush()
        return {
            "allowed": True,
            "trial_activated": True,
            "started_at": entitlement.started_at,
            "ends_at": entitlement.ends_at,
        }

    if entitlement.status == "active":
        refresh_trial_state(db, organization, now=current, commit=False)
        if entitlement.status == "active":
            db.flush()
            return {
                "allowed": True,
                "trial_activated": False,
                "reason": "already_active",
                "started_at": entitlement.started_at,
                "ends_at": entitlement.ends_at,
            }

    if not _is_paid_active(organization):
        raise TrialIdentityAlreadyUsed("TRIAL_NOT_AVAILABLE")

    db.flush()
    return {"allowed": True, "trial_activated": False, "reason": "paid_organization"}


def serialize_trial_status(
    db: Session,
    organization: Organization,
    *,
    now: datetime | None = None,
) -> dict:
    current = now or datetime.utcnow()
    entitlement = refresh_trial_state(db, organization, now=current, commit=True)
    if not entitlement:
        return {
            "status": "unavailable",
            "started_at": None,
            "ends_at": None,
            "days_remaining": None,
            "ai_response_limit": TRIAL_AI_RESPONSES,
        }

    days_remaining = None
    if entitlement.ends_at and entitlement.status == "active":
        remaining_seconds = max((entitlement.ends_at - current).total_seconds(), 0)
        days_remaining = int((remaining_seconds + 86399) // 86400)

    return {
        "status": entitlement.status,
        "started_at": entitlement.started_at.isoformat() + "Z"
        if entitlement.started_at
        else None,
        "ends_at": entitlement.ends_at.isoformat() + "Z" if entitlement.ends_at else None,
        "days_remaining": days_remaining,
        "ai_response_limit": entitlement.ai_response_limit,
    }


def pending_trial_can_bootstrap_store(
    db: Session,
    organization: Organization,
) -> bool:
    entitlement = get_trial_entitlement(db, organization.id)
    return bool(
        (organization.plan or "").strip().lower() == "trial"
        and (organization.subscription_status or "").strip().lower() == "trial_pending"
        and entitlement
        and entitlement.status == "pending"
    )
