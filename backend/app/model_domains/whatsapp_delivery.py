"""Durable delivery/read receipts for automated WhatsApp messages.

This sidecar keeps provider callbacks separate from execution state: sending
is immutable, while Meta may deliver callbacks repeatedly and out of order.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class WhatsAppAutomationDelivery(Base):
    __tablename__ = "whatsapp_automation_deliveries"
    __table_args__ = (
        UniqueConstraint("organization_id", "store_id", "provider_message_id", name="uq_whatsapp_automation_delivery_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    provider_message_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    campaign_recipient_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_recipient_executions.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    flow_node_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("automation_node_executions.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="sent", nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
