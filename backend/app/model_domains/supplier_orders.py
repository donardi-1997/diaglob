"""Supplier fulfillment order persistence models."""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class SupplierOrder(Base):
    __tablename__ = "supplier_orders"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "provider",
            "idempotency_key",
            name="uq_supplier_order_store_provider_idempotency",
        ),
        UniqueConstraint(
            "supplier_connection_id",
            "external_order_id",
            name="uq_supplier_order_connection_external",
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
    supplier_connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_connections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    provider_order_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    external_order_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    shipment_order_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    supplier_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    supplier_substatus: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )
    creation_status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    product_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    postage_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    order_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    actual_payment: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    items = relationship(
        "SupplierOrderItem",
        back_populates="supplier_order",
        cascade="all, delete-orphan",
    )
    supplier_connection = relationship("SupplierConnection")
    commerce_order = relationship("Order")


class SupplierOrderItem(Base):
    __tablename__ = "supplier_order_items"

    __table_args__ = (
        UniqueConstraint(
            "supplier_order_id",
            "order_item_id",
            name="uq_supplier_order_item_order_item",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_order_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    order_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("order_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_variant_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_line_item_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    supplier_order = relationship("SupplierOrder", back_populates="items")
    commerce_order_item = relationship("OrderItem")


__all__ = ["SupplierOrder", "SupplierOrderItem"]
