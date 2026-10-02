"""Persistent mapping between commerce variants and supplier variants."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class SupplierVariantMapping(Base):
    __tablename__ = "supplier_variant_mappings"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "provider",
            "product_variant_id",
            name="uq_supplier_variant_mapping_store_provider_variant",
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
    product_variant_id: Mapped[int] = mapped_column(
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    external_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_variant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
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

    store = relationship("Store")
    organization = relationship("Organization")
    product_variant = relationship("ProductVariant")


__all__ = ["SupplierVariantMapping"]
