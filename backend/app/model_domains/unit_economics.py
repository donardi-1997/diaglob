"""Persistence models for store-level Unit Economics assumptions."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class StoreUnitEconomicsConfig(Base):
    """One set of Unit Economics assumptions per store."""

    __tablename__ = "store_unit_economics_configs"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "organization_id",
            "store_id",
            name="uq_unit_economics_config_identity_scope",
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
        unique=True,
        index=True,
    )
    outbound_shipping_cost: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    return_logistics_cost: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    default_payment_fee_percent: Mapped[float | None] = mapped_column(
        Numeric(9, 4), nullable=True
    )
    default_payment_fee_fixed: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    default_cod_fee_percent: Mapped[float | None] = mapped_column(
        Numeric(9, 4), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    payment_method_rules = relationship(
        "PaymentMethodCostRule",
        back_populates="config",
        cascade="all, delete-orphan",
        order_by="PaymentMethodCostRule.id",
    )


class PaymentMethodCostRule(Base):
    """Payment-method-specific fee and COD overrides for a store."""

    __tablename__ = "payment_method_cost_rules"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "payment_method",
            name="uq_unit_economics_store_payment_method",
        ),
        ForeignKeyConstraint(
            ["unit_economics_config_id", "organization_id", "store_id"],
            [
                "store_unit_economics_configs.id",
                "store_unit_economics_configs.organization_id",
                "store_unit_economics_configs.store_id",
            ],
            name="fk_unit_economics_rule_parent_scope",
            ondelete="CASCADE",
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
    unit_economics_config_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    payment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    fee_percent: Mapped[float | None] = mapped_column(Numeric(9, 4), nullable=True)
    fee_fixed: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_cod: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cod_fee_percent: Mapped[float | None] = mapped_column(Numeric(9, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    config = relationship(
        "StoreUnitEconomicsConfig",
        back_populates="payment_method_rules",
    )
