"""Customer persistence models.

Physically extracted from the legacy ``app.models`` module. The table names,
columns, constraints, relationships, defaults, and shared SQLAlchemy metadata
are intentionally unchanged.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

# ============================================================
# CUSTOMER
# ============================================================

class Customer(Base):
    __tablename__ = "customers"

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

    phone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    email: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    country_code: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    organization = relationship(
        "Organization",
        back_populates="customers",
    )

    store_profiles = relationship(
        "CustomerStoreProfile",
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    conversations = relationship(
        "Conversation",
        back_populates="customer",
    )


# ============================================================
# CUSTOMER PER STORE
# ============================================================

class CustomerStoreProfile(Base):
    __tablename__ = "customer_store_profiles"

    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "store_id",
            name="uq_customer_store",
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

    customer_id: Mapped[int] = mapped_column(
        ForeignKey(
            "customers.id",
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

    external_customer_id: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    orders_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_spent: Mapped[float] = mapped_column(
        Numeric(18, 4),
        default=0,
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    last_order_ref: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    customer = relationship(
        "Customer",
        back_populates="store_profiles",
    )

    store = relationship(
        "Store",
        back_populates="customer_profiles",
    )

__all__ = ["Customer", "CustomerStoreProfile"]
