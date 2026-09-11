"""Conversation and messaging persistence models.

These definitions are physically owned by the Messaging domain while
``app.models`` keeps compatibility re-exports for existing callers. Table
names, columns, constraints, relationships, defaults, and shared SQLAlchemy
metadata are intentionally unchanged.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Conversation(Base):
    __tablename__ = "conversations"

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

    customer_id: Mapped[int] = mapped_column(
        ForeignKey(
            "customers.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "agents.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    channel: Mapped[str] = mapped_column(
        String(50),
        default="internal",
        nullable=False,
    )

    preview: Mapped[str] = mapped_column(
        Text,
        default="",
        nullable=False,
    )

    unread: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    mode: Mapped[str] = mapped_column(
        String(20),
        default="ai",
        nullable=False,
    )

    tags: Mapped[str] = mapped_column(
        Text,
        default="",
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

    organization = relationship(
        "Organization",
        back_populates="conversations",
    )

    store = relationship(
        "Store",
        back_populates="conversations",
    )

    customer = relationship(
        "Customer",
        back_populates="conversations",
    )

    assigned_agent = relationship(
        "Agent",
        back_populates="conversations",
    )

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "provider",
            "external_message_id",
            name="uq_message_provider_external",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "agents.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    sender: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(30),
        default="internal",
        nullable=False,
    )

    external_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    delivery_status: Mapped[str] = mapped_column(
        String(30),
        default="delivered",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    conversation = relationship(
        "Conversation",
        back_populates="messages",
    )

    agent = relationship(
        "Agent",
    )


class WhatsAppConnection(Base):
    __tablename__ = "whatsapp_connections"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            name="uq_whatsapp_connection_store",
        ),
        UniqueConstraint(
            "phone_number_id",
            name="uq_whatsapp_phone_number",
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
        unique=True,
        index=True,
    )

    phone_number_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    business_account_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    access_token_encrypted: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    verify_token: Mapped[str] = mapped_column(
        String(128),
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


class WhatsAppMessageTemplate(Base):
    __tablename__ = "whatsapp_message_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    whatsapp_connection_id: Mapped[int] = mapped_column(
        ForeignKey("whatsapp_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_template_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    provider_template_name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    language_code: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    components: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
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
    __table_args__ = (
        UniqueConstraint(
            "whatsapp_connection_id",
            "provider_template_name",
            "language_code",
            name="uq_whatsapp_template_connection_name_language",
        ),
    )


__all__ = [
    "Conversation",
    "Message",
    "WhatsAppConnection",
    "WhatsAppMessageTemplate",
]
