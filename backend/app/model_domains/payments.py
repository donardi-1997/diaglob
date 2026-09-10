"""Payment persistence models.

Physically extracted from the legacy ``app.models`` monolith while keeping
all tables registered on the shared SQLAlchemy ``Base`` metadata.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class PaymentConnection(Base):
    __tablename__ = "payment_connections"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "provider",
            name="uq_payment_connection_store_provider",
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
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30), default="disconnected", nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(
        String(20), default="sandbox", nullable=False
    )
    client_id_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    merchant_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    store = relationship("Store")
    organization = relationship("Organization")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "idempotency_key",
            name="uq_payment_txn_org_idempotency",
        ),
        Index(
            "ix_payment_txn_provider_txn_id",
            "provider",
            "provider_transaction_id",
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
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merchant_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False, index=True
    )
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    store = relationship("Store")
    organization = relationship("Organization")
    order = relationship("Order")
