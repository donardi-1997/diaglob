"""PII-free evidence that a Shopify managed subscription was checked.

Not an entitlement ledger: no billing rights, tokens, shop GIDs, plan handles,
raw Partner API payloads or merchant account identifiers are stored.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
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


__all__ = ["ShopifyBillingVerification"]
