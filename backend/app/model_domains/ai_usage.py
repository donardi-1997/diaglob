"""AI usage credit persistence models.

Purchased AI response packages live at organization scope. The grant keeps the
original purchased quantity and a mutable remaining balance while the provider
transaction id makes webhook fulfillment idempotent.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class AiUsageCreditGrant(Base):
    __tablename__ = "ai_usage_credit_grants"

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_transaction_id",
            name="uq_ai_credit_grant_provider_transaction",
        ),
        CheckConstraint(
            "responses_total > 0",
            name="ck_ai_credit_grant_total_positive",
        ),
        CheckConstraint(
            "responses_remaining >= 0 AND responses_remaining <= responses_total",
            name="ck_ai_credit_grant_remaining_bounds",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    package_key: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    responses_total: Mapped[int] = mapped_column(Integer, nullable=False)
    responses_remaining: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(
        String(30), default="paddle", nullable=False
    )
    provider_transaction_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )
    purchased_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    organization = relationship("Organization")
