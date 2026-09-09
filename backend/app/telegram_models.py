"""Telegram-specific persistence models.

Kept outside ``app.models`` to respect the repository architecture boundary
while still registering tables on the shared SQLAlchemy ``Base`` metadata.
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class TelegramConnection(Base):
    __tablename__ = "telegram_connections"

    __table_args__ = (
        UniqueConstraint("store_id", name="uq_telegram_connection_store"),
        UniqueConstraint("bot_id", name="uq_telegram_connection_bot_id"),
        UniqueConstraint("webhook_path_token", name="uq_telegram_webhook_path_token"),
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
    bot_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    bot_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bot_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bot_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_path_token: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="connected",
        index=True,
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
