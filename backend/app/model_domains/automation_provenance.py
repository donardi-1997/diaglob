"""Minimal-attribution record for new legacy automation executions.

Existing executions are deliberately NOT backfilled from payload text or IDs.
The linked customer is a DIAGLOB local profile, NOT proof that Shopify's data
subject has been verified. No names, emails, phones or provider identifiers.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class AutomationExecutionProvenance(Base):
    __tablename__ = "automation_execution_provenance"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_automation_execution_provenance_execution"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[int] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    store_id: Mapped[int | None] = mapped_column(
        ForeignKey("stores.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    source_context: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_linkage: Mapped[str] = mapped_column(String(48), nullable=False)
    provenance_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow,
    )
