"""Persistent conversational checkout state for COD sales.

The checkout is deliberately separate from the legacy Conversation and Order
models. It keeps raw customer input, normalized delivery data, explicit address
confirmation and final order confirmation auditable without expanding
``app.models``.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


CHECKOUT_STATUSES = (
    "collecting_variant",
    "collecting_quantity",
    "collecting_name",
    "collecting_phone",
    "collecting_city",
    "collecting_address",
    "collecting_neighborhood",
    "collecting_address_complement",
    "awaiting_address_confirmation",
    "collecting_delivery_reference",
    "awaiting_order_confirmation",
    "creating_order",
    "order_created",
    "cancelled",
    "failed",
    "expired",
)


class ConversationalCheckout(Base):
    """One persistent checkout attempt started from a conversation."""

    __tablename__ = "conversational_checkouts"

    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'collecting_variant','collecting_quantity','collecting_name',"
            "'collecting_phone','collecting_city','collecting_address',"
            "'collecting_neighborhood','collecting_address_complement',"
            "'awaiting_address_confirmation','collecting_delivery_reference',"
            "'awaiting_order_confirmation','creating_order','order_created',"
            "'cancelled','failed','expired'"
            ")",
            name="ck_conversational_checkout_status",
        ),
        CheckConstraint(
            "payment_method = 'cash_on_delivery'",
            name="ck_conversational_checkout_payment_method",
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
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    product_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    variant_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    subtotal: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    shipping_amount: Mapped[float] = mapped_column(
        Numeric(18, 4), default=0, nullable=False
    )
    total: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_method: Mapped[str] = mapped_column(
        String(30), default="cash_on_delivery", nullable=False
    )

    customer_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    address_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    address_line: Mapped[str | None] = mapped_column(String(300), nullable=True)
    address_complement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    region: Mapped[str | None] = mapped_column(String(150), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    delivery_reference: Mapped[str | None] = mapped_column(Text, nullable=True)

    address_confidence_score: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    address_validation_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    address_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    address_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    customer_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    customer_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    created_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
