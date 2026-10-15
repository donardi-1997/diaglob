"""One-time merchant-authorized links from Shopify ID-token subjects to DIAGLOB memberships.

Never treat an OAuth installation or a Shopify ID token alone as permission to
read an organization's data. A separate authorized DIAGLOB member must confirm
each Shopify user/installation pairing using a short-lived one-time code.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ShopifyEmbeddedLinkTicket(Base):
    __tablename__ = "shopify_embedded_link_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    shop_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    membership_id: Mapped[int] = mapped_column(ForeignKey("organization_memberships.id", ondelete="CASCADE"), nullable=False)
    connection_id: Mapped[int] = mapped_column(ForeignKey("commerce_connections.id", ondelete="CASCADE"), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ShopifyEmbeddedIdentityBinding(Base):
    __tablename__ = "shopify_embedded_identity_bindings"
    __table_args__ = (
        UniqueConstraint("shop_domain", "subject_digest", name="uq_shopify_embedded_subject_shop"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=False)
    membership_id: Mapped[int] = mapped_column(ForeignKey("organization_memberships.id", ondelete="CASCADE"), nullable=False)
    connection_id: Mapped[int] = mapped_column(ForeignKey("commerce_connections.id", ondelete="CASCADE"), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
