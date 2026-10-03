"""Marketing acquisition models for Diaglob's own customer acquisition.

This domain is intentionally separate from merchant Meta Ads connections. It stores
only campaign attribution needed to understand how Diaglob registrations were
acquired; raw email, IP address, and user-agent values are never persisted here.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class MarketingRegistrationAttribution(Base):
    __tablename__ = "marketing_registration_attributions"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_marketing_registration_event_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    content: Mapped[str | None] = mapped_column(String(255), nullable=True)
    term: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fbclid: Mapped[str | None] = mapped_column(String(500), nullable=True)
    first_touch: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_touch: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    event_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    consented: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    meta_delivery_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )
    meta_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class MarketingFunnelEvent(Base):
    __tablename__ = "marketing_funnel_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_marketing_funnel_event_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_attribution_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(160), nullable=False)
    event_name: Mapped[str] = mapped_column(
        String(60), nullable=False, index=True
    )
    provider_event_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    medium: Mapped[str | None] = mapped_column(String(120), nullable=True)
    campaign: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    content: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    meta_delivery_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )
    meta_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


__all__ = ["MarketingFunnelEvent", "MarketingRegistrationAttribution"]
