"""Sales attribution domain models.

Keeps order-closing attribution separate from the legacy Order model so the
commerce schema can evolve without adding more fields to app.models.
"""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class OrderSalesAttribution(Base):
    """Records the actor that closed/created a sale when Diaglob knows it.

    No row means the order is intentionally unattributed. This is important
    for imported provider orders where Diaglob has no trustworthy evidence of
    who closed the sale.
    """

    __tablename__ = "order_sales_attributions"

    __table_args__ = (
        UniqueConstraint("order_id", name="uq_order_sales_attribution_order"),
        CheckConstraint(
            "actor_type IN ('human', 'ai')",
            name="ck_order_sales_attribution_actor_type",
        ),
        CheckConstraint(
            "(actor_type = 'human' AND human_user_id IS NOT NULL AND ai_agent_id IS NULL) "
            "OR (actor_type = 'ai' AND ai_agent_id IS NOT NULL AND human_user_id IS NULL)",
            name="ck_order_sales_attribution_actor_identity",
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
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
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
