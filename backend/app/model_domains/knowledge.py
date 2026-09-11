"""Knowledge-base persistence models.

These definitions are physically owned by the Knowledge domain while
``app.models`` keeps compatibility re-exports for existing callers. Table
names, columns, constraints, relationships, defaults, and shared SQLAlchemy
metadata are intentionally unchanged.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .tenancy import knowledge_base_stores


agent_knowledge_bases = Table(
    "agent_knowledge_bases",
    Base.metadata,
    Column(
        "agent_id",
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "knowledge_base_id",
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

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

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    scope: Mapped[str] = mapped_column(
        String(30),
        default="selected_stores",
        nullable=False,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    external_data_source_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    external_status: Mapped[str | None] = mapped_column(
        String(30),
        default="pending",
        server_default="pending",
        nullable=True,
    )

    external_last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    provisioning_stage: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    provisioning_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    provisioning_stage_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    organization = relationship(
        "Organization",
        back_populates="knowledge_bases",
    )

    stores = relationship(
        "Store",
        secondary=knowledge_base_stores,
        back_populates="knowledge_bases",
    )

    agents = relationship(
        "Agent",
        secondary=agent_knowledge_bases,
        back_populates="knowledge_bases",
    )


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

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

    knowledge_base_id: Mapped[int] = mapped_column(
        ForeignKey(
            "knowledge_bases.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    source_type: Mapped[str] = mapped_column(
        String(30),
        default="file",
        nullable=False,
    )

    content_type: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    s3_bucket: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    s3_key: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )

    size_bytes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="uploaded",
        nullable=False,
    )

    ingestion_job_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    external_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    sheet_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    sync_status: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    sync_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metadata_json: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    external_mime_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    external_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    parent_source_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "knowledge_sources.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    external_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    sync_generation: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    knowledge_base = relationship(
        "KnowledgeBase",
    )


__all__ = [
    "KnowledgeBase",
    "KnowledgeSource",
    "agent_knowledge_bases",
]
