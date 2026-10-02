"""Durable automatic supplier-fulfillment jobs."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class AutoFulfillmentJob(Base):
    __tablename__ = "auto_fulfillment_jobs"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "order_id",
            "provider",
            name="uq_auto_fulfillment_store_order_provider",
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
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    shipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(40),
        default="pending",
        nullable=False,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    origin_country_code: Mapped[str] = mapped_column(
        String(2),
        default="CN",
        nullable=False,
    )
    logistic_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    shopify_fulfillment_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
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

    order = relationship("Order")
    supplier_order = relationship("SupplierOrder")
    shipment = relationship("Shipment")


__all__ = ["AutoFulfillmentJob"]
