"""Durable intake of authenticated Shopify mandatory privacy requests.

No automatic destructive processing is enabled. Subject selectors are encrypted
at rest; identifiers, emails and order IDs must not appear in normal app logs.
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ShopifyPrivacyRequest(Base):
    __tablename__ = "shopify_privacy_requests"

    __table_args__ = (
        UniqueConstraint("request_id", name="uq_shopify_privacy_request_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    shop_id: Mapped[str] = mapped_column(String(80), nullable=False)
    shop_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # Nullable on purpose: callbacks can arrive after uninstall/deletion.
    # No foreign keys: the privacy receipt must outlive tenant/store deletion.
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    store_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Only the minimum Shopify-provided subject/order selectors are retained.
    # Encrypted using the existing SHOPIFY_TOKEN_ENCRYPTION_KEY.
    selector_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="pending_policy_review", index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


__all__ = ["ShopifyPrivacyRequest"]
