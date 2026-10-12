"""Per-store Meta Pixel configuration, separate from Meta Ads account OAuth.

This is a configuration record, NOT proof of a live Shopify Web Pixel. No
customer/event data or Meta tokens are persisted in this table.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class MetaPixelConfiguration(Base):
    __tablename__ = "meta_pixel_configurations"
    __table_args__ = (
        UniqueConstraint("store_id", name="uq_meta_pixel_store"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )
    pixel_id: Mapped[str] = mapped_column(String(30), nullable=False)
    # Merchant declaration about other measurement code; not verification.
    existing_tracking: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown"
    )
    # Shopify app pixel provisioning is distinct from event transmission.\n    web_pixel_gid: Mapped[str | None] = mapped_column(String(128), nullable=True)\n    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)\n    # Activation is deliberately a future release gate: never activate here.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(35), nullable=False, default="awaiting_extension"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
