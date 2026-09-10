"""Sales attribution domain models.

Keeps order-closing attribution separate from the legacy Order model so the
commerce schema can evolve without adding more fields to app.models.
"""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class OrderSalesAttribution(Base):
    """Records the actor that closed/created a sale when Diaglob knows it.

    No row means the order is intentionally unattributed. ``actor_label`` is a
    historical snapshot so reports keep the original closer name even when a
    user or AI agent is later removed.
    """

    __tablename__ = "order_sales_attributions"

    __table_args__ = (
        UniqueConstraint("order_id", name="uq_order_sales_attribution_order"),
        CheckConstraint(
            "actor_type IN ('human', 'ai')",
            name="ck_order_sales_attribution_actor_type",
        ),
        CheckConstraint(
            "NOT (human_user_id IS NOT NULL AND ai_agent_id IS NOT NULL)",
            name="ck_order_sales_attribution_single_identity",
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
    actor_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )
    actor_label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    human_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ai_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        default="diaglob_order_creation",
        nullable=False,
    )
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


class OrderSalesAttributionChange(Base):
    """Immutable audit entry for a manual attribution correction."""

    __tablename__ = "order_sales_attribution_changes"

    __table_args__ = (
        CheckConstraint(
            "action IN ('assign', 'reassign', 'clear')",
            name="ck_order_sales_attribution_change_action",
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
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    changed_by_label: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    previous_actor_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    previous_actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_actor_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
