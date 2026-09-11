"""Persistent free-trial state and anti-abuse identities.

Trial identities deliberately store only a SHA-256 digest of an external commerce
identity. The ledger survives commerce disconnects so reconnecting the same real
store through another Diaglob organization cannot mint another free trial.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class TrialEntitlement(Base):
    __tablename__ = "trial_entitlements"

    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_trial_entitlement_organization"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_by_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    activated_by_identity_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    ai_response_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class TrialIdentity(Base):
    __tablename__ = "trial_identities"

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "identity_hash",
            name="uq_trial_identity_provider_hash",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    identity_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    first_organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    first_store_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trial_entitlement_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    trial_consumed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


__all__ = ["TrialEntitlement", "TrialIdentity"]
