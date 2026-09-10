"""Shared customer-risk report domain models.

The tables store deterministic keyed fingerprints rather than raw customer
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


class CustomerRiskReportEvent(Base):
    """Immutable audit event for report lifecycle and moderation actions."""

    __tablename__ = "customer_risk_report_events"

    __table_args__ = (
        CheckConstraint(
            "actor_role IN ('reporter', 'platform_admin', 'system')",
            name="ck_customer_risk_report_event_actor_role",
        ),
        CheckConstraint(
            "action IN ("
            "'report_submitted', 'report_updated', 'report_withdrawn', "
            "'moderation_confirmed', 'moderation_dismissed', "
            "'moderation_disputed', 'moderation_reset_pending'"
            ")",
            name="ck_customer_risk_report_event_action",
        ),
        Index(
            "ix_customer_risk_report_events_org_created",
            "organization_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("customer_risk_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_role: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )


class CustomerRiskDispute(Base):
    """Subject-level appeal submitted without revealing source-report identity."""

    __tablename__ = "customer_risk_disputes"

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'accepted', 'rejected', 'withdrawn')",
            name="ck_customer_risk_dispute_status",
        ),
        CheckConstraint(
            "phone_fingerprint IS NOT NULL OR email_fingerprint IS NOT NULL",
            name="ck_customer_risk_dispute_identifier",
        ),
        Index(
            "ix_customer_risk_disputes_phone_status",
            "phone_fingerprint",
            "status",
        ),
        Index(
            "ix_customer_risk_disputes_email_status",
            "email_fingerprint",
            "status",
        ),
        Index(
            "ix_customer_risk_disputes_org_customer_status",
            "requester_organization_id",
            "local_customer_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requester_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    requester_user_id: Mapped[int | None] = mapped_column(
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
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="open",
        nullable=False,
        index=True,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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


class CustomerRiskDisputeEvent(Base):
    """Immutable audit event for appeal lifecycle."""

    __tablename__ = "customer_risk_dispute_events"

    __table_args__ = (
        CheckConstraint(
            "actor_role IN ('requester', 'platform_admin', 'system')",
            name="ck_customer_risk_dispute_event_actor_role",
        ),
        CheckConstraint(
            "action IN ("
            "'dispute_submitted', 'dispute_updated', 'dispute_withdrawn', "
            "'dispute_accepted', 'dispute_rejected'"
            ")",
            name="ck_customer_risk_dispute_event_action",
        ),
        Index(
            "ix_customer_risk_dispute_events_org_created",
            "organization_id",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dispute_id: Mapped[int] = mapped_column(
        ForeignKey("customer_risk_disputes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_role: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
