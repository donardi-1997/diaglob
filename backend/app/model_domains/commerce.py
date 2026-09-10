"""Commerce integration persistence models.

Physically extracted from the legacy ``app.models`` monolith while keeping
all tables registered on the shared SQLAlchemy ``Base`` metadata.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class CommerceConnection(Base):
    __tablename__ = "commerce_connections"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            name="uq_commerce_connection_store",
        ),
        UniqueConstraint(
            "provider",
            "external_store_url",
            name="uq_commerce_provider_store_url",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    organization_id: Mapped[int] = mapped_column(
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    provider: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    external_store_url: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    access_token_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    refresh_token_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    api_key_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    api_secret_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    access_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    scopes: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="connected",
        nullable=False,
        index=True,
    )

    connected_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    store = relationship(
        "Store",
    )

    organization = relationship(
        "Organization",
    )


__all__ = ["CommerceConnection"]
