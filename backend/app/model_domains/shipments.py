"""Shipment and tracking persistence models."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Shipment(Base):
    __tablename__ = "shipments"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "provider",
            "tracking_number",
            name="uq_shipment_store_provider_tracking",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    supplier_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    tracking_number: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    logistic_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tracking_provider: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    tracking_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin_country_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    destination_country_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    last_mile_carrier: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    last_mile_tracking_number: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    normalized_status: Mapped[str] = mapped_column(
        String(40),
        default="PENDING",
        nullable=False,
        index=True,
    )
    provider_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
    )
    provider_status_label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    delivery_days: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delivery_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    events = relationship(
        "TrackingEvent",
        back_populates="shipment",
        cascade="all, delete-orphan",
        order_by="TrackingEvent.event_at",
    )
    supplier_order = relationship("SupplierOrder")
    commerce_order = relationship("Order")


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    __table_args__ = (
        UniqueConstraint(
            "shipment_id",
            "provider_event_key",
            name="uq_tracking_event_shipment_provider_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    normalized_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    shipment = relationship("Shipment", back_populates="events")


class CJWebhookReceipt(Base):
    __tablename__ = "cj_webhook_receipts"

    __table_args__ = (
        UniqueConstraint(
            "supplier_connection_id",
            "message_id",
            name="uq_cj_webhook_connection_message",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_connection_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(30),
        default="received",
        nullable=False,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


__all__ = ["Shipment", "TrackingEvent", "CJWebhookReceipt"]
