"""PII-free evidence that a Shopify managed subscription was checked.

Not an entitlement ledger: no billing rights, tokens, shop GIDs, plan handles,
raw Partner API payloads or merchant account identifiers are stored.
"""
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ShopifyBillingVerification(Base):
    __tablename__ = "shopify_billing_verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    connection_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Fixed operational codes, never a raw provider error or message.
    status: Mapped[str] = mapped_column(String(45), nullable=False)
    current_plan: Mapped[str] = mapped_column(String(30), nullable=False)
    target_plan: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_period_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Snapshot of the install epoch, to avoid authorizing a later reinstall
    # from a stale verification. This record is evidence, NOT authorization.
    installation_connected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )


class ShopifyPlanTransitionReview(Base):
    """An immutable, non-authorizing proposal awaiting a future approval policy.

    A uniqueness constraint prevents replay of a verification, while a partial
    unique index permits at most one pending review per organization. It never
    represents purchased access or a confirmed payment.
    """
    __tablename__ = "shopify_plan_transition_reviews"
    __table_args__ = (
        Index(
            "uq_shopify_pending_transition_org",
            "organization_id",
            unique=True,
            sqlite_where=text("status = 'pending_review'"),
            postgresql_where=text("status = 'pending_review'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    verification_id: Mapped[int] = mapped_column(
        Integer, nullable=False, unique=True, index=True
    )
    store_id: Mapped[int] = mapped_column(Integer, nullable=False)
    connection_id: Mapped[int] = mapped_column(Integer, nullable=False)
    installation_connected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
    baseline_plan: Mapped[str] = mapped_column(String(30), nullable=False)
    target_plan: Mapped[str] = mapped_column(String(30), nullable=False)
    target_period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending_review"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


__all__ = ["ShopifyBillingVerification", "ShopifyPlanTransitionReview"]
