"""Shared customer-risk report domain models.

The table stores deterministic keyed fingerprints rather than raw customer
identifiers. Reporter-private notes/evidence are never part of cross-tenant
responses; consumers only receive aggregate risk signals.
"""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class CustomerRiskReport(Base):
    """A cautionary report submitted by one organization about a customer.

    Reports are signals, not findings of guilt. Cross-account matching happens
    through keyed phone/email fingerprints. ``notes`` and
    ``evidence_reference`` remain private to the reporting organization.
    """

    __tablename__ = "customer_risk_reports"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'disputed', 'dismissed')",
            name="ck_customer_risk_report_status",
        ),
        CheckConstraint(
            "reason IN ("
            "'suspected_fraud', "
            "'payment_abuse', "
            "'delivery_claim', "
            "'identity_mismatch', "
            "'abusive_behavior', "
            "'other'"
            ")",
            name="ck_customer_risk_report_reason",
        ),
        CheckConstraint(
            "phone_fingerprint IS NOT NULL OR email_fingerprint IS NOT NULL",
            name="ck_customer_risk_report_identifier",
        ),
        Index(
            "ix_customer_risk_reports_phone_status",
            "phone_fingerprint",
            "status",
        ),
        Index(
            "ix_customer_risk_reports_email_status",
            "email_fingerprint",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reporter_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reporter_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    local_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    phone_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    email_fingerprint: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
