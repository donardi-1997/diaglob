"""Durable intake of authenticated Shopify mandatory privacy requests.

No automatic destructive processing is enabled. Subject selectors are encrypted
at rest; identifiers, emails and order IDs must not appear in normal app logs.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
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



class ShopifyPrivacyShopIdentity(Base):
    """Minimal signed Shopify shop-to-tenant history, survives uninstall.

    No store FK by design: Shopify GDPR receipts can arrive after merchant
    uninstalls or deletes the local store. This record is not customer data
    processing authorization. The shop ID and domain are pseudonymous shop
    identifiers whose disposal remains subject to reviewed retention policy.
    """

    __tablename__ = "shopify_privacy_shop_identities"
    __table_args__ = (
        UniqueConstraint(
            "shop_id", "shop_domain",
            name="uq_shopify_privacy_shop_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    shop_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    provenance: Mapped[str] = mapped_column(String(40), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)




class ShopifyPrivacyDeliveryArtifact(Base):
    """Synthetic, encrypted, recipient-bound one-time delivery ticket.

    No personal data in searchable fields. The sole encrypted ciphertext
    column is purged on redemption, revocation or expiry. This model does not
    authorize any live customer export or actual Shopify fulfillment.
    """

    __tablename__ = "shopify_privacy_delivery_artifacts"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_shopify_privacy_delivery_token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    recipient_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ciphertext_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    synthetic_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )


class ShopifyPrivacyDeliveryAudit(Base):
    """PII-free audit of synthetic delivery; no token, body or recipient email."""

    __tablename__ = "shopify_privacy_delivery_audit"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ShopifyPrivacyAuditEvent(Base):
    """PII-free append-only evidence for authenticated privacy requests.

    No tenant FK: evidence survives storefront unlink/deletion. The request
    identifier is the deterministic receipt digest, not Shopify's customer ID.
    """

    __tablename__ = "shopify_privacy_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )



class ShopifyPrivacyWorkItem(Base):
    """PII-free data-source task belonging to one signed Shopify request.

    No foreign key to merchant/store rows: post-uninstall evidence must survive.
    Tasks never contain selectors, personal data, payloads or plaintext evidence.
    """

    __tablename__ = "shopify_privacy_work_items"
    __table_args__ = (
        UniqueConstraint("request_id", "area", name="uq_shopify_privacy_work_item_area"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    area: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="blocked")
    blocker_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )



class ShopifyPrivacySuppression(Base):
    """Durable pseudonymous, shop-bound HMAC tombstone (staged until approved).

    The server must preserve SHOPIFY_PRIVACY_SUPPRESSION_KEY across deploys,
    restores and encryption-key rotations. No raw email, phone, IDs or addresses
    are stored; no tenant foreign key means records survive shop unlink.
    """

    __tablename__ = "shopify_privacy_suppressions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "store_id", "kind", "selector_digest",
            name="uq_shopify_privacy_suppression_subject",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    store_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    selector_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    domain_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="staged", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)



class ShopifyPrivacyControlEvidence(Base):
    """Unverified artifact reference for an independent privacy control review.

    No raw evidence, legal conclusions, identifiers or personal data stored.
    """

    __tablename__ = "shopify_privacy_control_evidence"
    __table_args__ = (
        UniqueConstraint(
            "request_id", "control", "artifact_sha256",
            name="uq_shopify_privacy_control_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    control: Mapped[str] = mapped_column(String(80), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


__all__ = ["ShopifyPrivacyRequest", "ShopifyPrivacyShopIdentity", "ShopifyPrivacyDeliveryArtifact", "ShopifyPrivacyDeliveryAudit", "ShopifyPrivacyAuditEvent", "ShopifyPrivacyWorkItem", "ShopifyPrivacySuppression", "ShopifyPrivacyControlEvidence"]
