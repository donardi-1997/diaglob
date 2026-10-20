"""Authenticated, durable *synthetic-only* Shopify privacy delivery.

This is the delivery transport contract; not a live customer export pipeline.
All sensitive bytes stay Fernet-encrypted at rest, a token is stored only as
SHA-256, and a conditional UPDATE makes redemption atomic across workers.
Production DBs remain unconditionally disabled pending independent
provenance, complete export and legal/processor approval.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from ..models import (
    MembershipStore, OrganizationMembership, ShopifyPrivacyAuditEvent,
    ShopifyPrivacyDeliveryArtifact, ShopifyPrivacyDeliveryAudit,
    ShopifyPrivacyRequest, ShopifyPrivacyShopIdentity, Store,
)
from ..shopify_oauth import normalize_shop_domain
from .shopify_privacy_synthetic_export import (
    EncryptedSyntheticExport, SyntheticPrivacyExportError,
    verify_encrypted_synthetic_export,
)

_REQUEST = re.compile(r"^[0-9a-f]{64}$")
_MAX_ARTIFACT = 1024 * 1024
_ALLOWED_ROLES = frozenset({"owner", "admin"})


class ShopifyPrivacySecureDeliveryError(ValueError):
    """Error codes only; never include bytes, recipient identity or secrets."""


@dataclass(frozen=True)
class SecureDeliveryTicket:
    token: str = field(repr=False)
    expires_in_seconds: int
    synthetic_only: bool = True
    fulfillment_complete: bool = False


@dataclass(frozen=True)
class SecureDeliveryDownload:
    ciphertext: bytes = field(repr=False)
    sha256: str
    synthetic_only: bool = True
    fulfillment_complete: bool = False


def _fixture_only(db: Session) -> None:
    bind = db.get_bind()
    if (
        os.getenv("SHOPIFY_PRIVACY_SYNTHETIC_HTTP_ENABLED") != "true"
        or bind is None
        or bind.dialect.name != "sqlite"
        or bind.url.database not in (None, ":memory:")
    ):
        raise ShopifyPrivacySecureDeliveryError("LIVE_PRIVACY_DELIVERY_DISABLED")


def _cipher() -> Fernet:
    try:
        key = os.getenv("SHOPIFY_PRIVACY_DELIVERY_KEY", "").encode("ascii")
        return Fernet(key)
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ShopifyPrivacySecureDeliveryError("PRIVACY_DELIVERY_KEY_UNAVAILABLE") from exc


def _receipt_and_recipient(
    db: Session, *, request_id: str, organization_id: int,
    store_id: int, recipient_user_id: int,
) -> None:
    if not isinstance(request_id, str) or not _REQUEST.fullmatch(request_id):
        raise ShopifyPrivacySecureDeliveryError("INVALID_PRIVACY_REQUEST_ID")
    if any(type(i) is not int or i <= 0 for i in (
        organization_id, store_id, recipient_user_id,
    )):
        raise ShopifyPrivacySecureDeliveryError("DELIVERY_CONTEXT_INVALID")
    membership = db.query(OrganizationMembership).filter(
        OrganizationMembership.user_id == recipient_user_id,
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.active.is_(True),
        OrganizationMembership.role.in_(_ALLOWED_ROLES),
    ).first()
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
        Store.active.is_(True),
    ).first()
    if membership is None or store is None:
        raise ShopifyPrivacySecureDeliveryError("DELIVERY_RECIPIENT_UNAUTHORIZED")
    if not membership.all_stores and db.query(MembershipStore.store_id).filter(
        MembershipStore.membership_id == membership.id,
        MembershipStore.store_id == store_id,
    ).first() is None:
        raise ShopifyPrivacySecureDeliveryError("DELIVERY_RECIPIENT_UNAUTHORIZED")

    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
        ShopifyPrivacyRequest.organization_id == organization_id,
        ShopifyPrivacyRequest.store_id == store_id,
        ShopifyPrivacyRequest.topic == "customers/data_request",
        ShopifyPrivacyRequest.status == "pending_policy_review",
        ShopifyPrivacyRequest.completed_at.is_(None),
    ).first()
    signed = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first()
    if receipt is None or signed is None:
        raise ShopifyPrivacySecureDeliveryError("SIGNED_DELIVERY_SCOPE_UNVERIFIED")

    # Numeric store IDs can survive a disconnect/relink. A historic signed
    # request must remain bound to the *same* Shopify domain and recorded shop
    # identity at issuance, redemption and revocation.
    try:
        domain = normalize_shop_domain(receipt.shop_domain)
        current_domain = normalize_shop_domain(store.shopify_domain)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ShopifyPrivacySecureDeliveryError(
            "SIGNED_DELIVERY_SCOPE_UNVERIFIED"
        ) from exc
    if not hmac.compare_digest(domain, current_domain):
        raise ShopifyPrivacySecureDeliveryError("SIGNED_DELIVERY_SCOPE_UNVERIFIED")

    identity = db.query(ShopifyPrivacyShopIdentity.id).filter(
        ShopifyPrivacyShopIdentity.shop_id == receipt.shop_id,
        ShopifyPrivacyShopIdentity.shop_domain == domain,
        ShopifyPrivacyShopIdentity.organization_id == organization_id,
        ShopifyPrivacyShopIdentity.store_id == store_id,
    ).first()
    if identity is None:
        raise ShopifyPrivacySecureDeliveryError("SIGNED_DELIVERY_SCOPE_UNVERIFIED")


def _token_hash(token: str) -> str:
    if not isinstance(token, str) or not 32 <= len(token) <= 128 or (
        not token.isascii()
    ):
        raise ShopifyPrivacySecureDeliveryError("PRIVACY_DELIVERY_UNAVAILABLE")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _audit(db: Session, request_id: str, event_type: str, actor: str) -> None:
    db.add(ShopifyPrivacyDeliveryAudit(
        request_id=request_id, event_type=event_type,
        actor_type=actor, created_at=datetime.utcnow(),
    ))


def issue_synthetic_secure_delivery(
    db: Session, *, request_id: str, organization_id: int,
    store_id: int, recipient_user_id: int, artifact: EncryptedSyntheticExport,
    ttl_seconds: int = 300, fixture_authorized: bool = False,
) -> SecureDeliveryTicket:
    """Stage encrypted fixture for ONE authenticated DIAGLOB merchant user.

    Caller must have an independently generated fixture; there is no HTTP
    issue endpoint and no issuance method for live customer datasets.
    """
    _fixture_only(db)
    if fixture_authorized is not True:
        raise ShopifyPrivacySecureDeliveryError("SYNTHETIC_ISSUANCE_NOT_AUTHORIZED")
    _receipt_and_recipient(
        db, request_id=request_id, organization_id=organization_id,
        store_id=store_id, recipient_user_id=recipient_user_id,
    )
    if type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 900:
        raise ShopifyPrivacySecureDeliveryError("DELIVERY_TTL_INVALID")
    # Never trust metadata alone: decrypt the fixture with the delivery key
    # and verify the embedded request ID and EVERY synthetic-only row. This
    # prevents cross-case export swapping and disguised real PII, even when
    # an otherwise valid ciphertext/hash pair is supplied.
    try:
        verify_encrypted_synthetic_export(
            artifact=artifact,
            encryption_key=os.getenv("SHOPIFY_PRIVACY_DELIVERY_KEY", "").encode("ascii"),
            expected_request_id=request_id,
        )
    except (SyntheticPrivacyExportError, UnicodeEncodeError) as exc:
        raise ShopifyPrivacySecureDeliveryError("UNTRUSTED_PRIVACY_ARTIFACT") from exc

    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    db.add(ShopifyPrivacyDeliveryArtifact(
        request_id=request_id, organization_id=organization_id,
        store_id=store_id, recipient_user_id=recipient_user_id,
        token_digest=_token_hash(token),
        artifact_sha256=artifact.sha256,
        ciphertext_encrypted=_cipher().encrypt(artifact.ciphertext).decode("ascii"),
        expires_at=now + timedelta(seconds=ttl_seconds), created_at=now,
        synthetic_only=True,
    ))
    _audit(db, request_id, "issued", "fixture_operator")
    db.commit()
    return SecureDeliveryTicket(token=token, expires_in_seconds=ttl_seconds)


def redeem_synthetic_secure_delivery(
    db: Session, *, request_id: str, organization_id: int,
    store_id: int, recipient_user_id: int, token: str,
) -> SecureDeliveryDownload:
    """Atomically consume ticket after rechecking current merchant access."""
    _fixture_only(db)
    _receipt_and_recipient(
        db, request_id=request_id, organization_id=organization_id,
        store_id=store_id, recipient_user_id=recipient_user_id,
    )
    digest = _token_hash(token)
    now = datetime.utcnow()
    claimed = db.execute(
        update(ShopifyPrivacyDeliveryArtifact).where(
            ShopifyPrivacyDeliveryArtifact.token_digest == digest,
            ShopifyPrivacyDeliveryArtifact.request_id == request_id,
            ShopifyPrivacyDeliveryArtifact.organization_id == organization_id,
            ShopifyPrivacyDeliveryArtifact.store_id == store_id,
            ShopifyPrivacyDeliveryArtifact.recipient_user_id == recipient_user_id,
            ShopifyPrivacyDeliveryArtifact.synthetic_only.is_(True),
            ShopifyPrivacyDeliveryArtifact.revoked_at.is_(None),
            ShopifyPrivacyDeliveryArtifact.redeemed_at.is_(None),
            ShopifyPrivacyDeliveryArtifact.ciphertext_encrypted.isnot(None),
            ShopifyPrivacyDeliveryArtifact.expires_at > now,
        ).values(redeemed_at=now),
    )
    if claimed.rowcount != 1:
        db.rollback()
        raise ShopifyPrivacySecureDeliveryError("PRIVACY_DELIVERY_UNAVAILABLE")
    row = db.query(ShopifyPrivacyDeliveryArtifact).filter(
        ShopifyPrivacyDeliveryArtifact.token_digest == digest,
    ).one()
    try:
        content = _cipher().decrypt(row.ciphertext_encrypted.encode("ascii"))
    except (InvalidToken, ValueError) as exc:
        db.rollback()
        raise ShopifyPrivacySecureDeliveryError("PRIVACY_DELIVERY_ARTIFACT_INVALID") from exc
    if (
        len(content) > _MAX_ARTIFACT
        or not hmac.compare_digest(hashlib.sha256(content).hexdigest(), row.artifact_sha256)
    ):
        db.rollback()
        raise ShopifyPrivacySecureDeliveryError("PRIVACY_DELIVERY_ARTIFACT_INVALID")
    # Re-verify the *inner* fixture envelope on every download. A valid
    # at-rest checksum or encryption layer alone is not evidence that stored
    # bytes are still request-bound and synthetic-only.
    try:
        encryption_key = os.getenv("SHOPIFY_PRIVACY_DELIVERY_KEY", "").encode("ascii")
        document = json.loads(Fernet(encryption_key).decrypt(content))
        if not isinstance(document, dict) or not isinstance(document.get("records"), list):
            raise ValueError("INVALID_SYNTHETIC_ENVELOPE")
        verify_encrypted_synthetic_export(
            artifact=EncryptedSyntheticExport(
                ciphertext=content, sha256=row.artifact_sha256,
                record_count=len(document["records"]), request_id=request_id,
            ),
            encryption_key=encryption_key, expected_request_id=request_id,
        )
    except (
        SyntheticPrivacyExportError, InvalidToken, ValueError, TypeError,
        UnicodeEncodeError,
    ) as exc:
        db.rollback()
        raise ShopifyPrivacySecureDeliveryError(
            "PRIVACY_DELIVERY_ARTIFACT_INVALID"
        ) from exc
    checksum = row.artifact_sha256
    row.ciphertext_encrypted = None
    _audit(db, request_id, "redeemed", "authenticated_merchant")
    db.commit()
    # Do not read expired ORM state after committing the one-time claim.
    return SecureDeliveryDownload(ciphertext=content, sha256=checksum)


def revoke_synthetic_secure_delivery(
    db: Session, *, request_id: str, organization_id: int,
    store_id: int, recipient_user_id: int, token: str,
) -> bool:
    """A different merchant/tenant cannot revoke someone else's artifact."""
    _fixture_only(db)
    _receipt_and_recipient(
        db, request_id=request_id, organization_id=organization_id,
        store_id=store_id, recipient_user_id=recipient_user_id,
    )
    digest = _token_hash(token)
    count = db.execute(
        update(ShopifyPrivacyDeliveryArtifact).where(
            ShopifyPrivacyDeliveryArtifact.token_digest == digest,
            ShopifyPrivacyDeliveryArtifact.request_id == request_id,
            ShopifyPrivacyDeliveryArtifact.organization_id == organization_id,
            ShopifyPrivacyDeliveryArtifact.store_id == store_id,
            ShopifyPrivacyDeliveryArtifact.recipient_user_id == recipient_user_id,
            ShopifyPrivacyDeliveryArtifact.redeemed_at.is_(None),
            ShopifyPrivacyDeliveryArtifact.revoked_at.is_(None),
        ).values(revoked_at=datetime.utcnow(), ciphertext_encrypted=None),
    ).rowcount
    if count == 1:
        _audit(db, request_id, "revoked", "authenticated_merchant")
    db.commit()
    return count == 1


def purge_expired_synthetic_deliveries(db: Session) -> int:
    """Idempotent ciphertext purge; must be run by an approved scheduler."""
    _fixture_only(db)
    now = datetime.utcnow()
    stale = db.query(ShopifyPrivacyDeliveryArtifact).filter(
        ShopifyPrivacyDeliveryArtifact.ciphertext_encrypted.isnot(None),
        or_(
            ShopifyPrivacyDeliveryArtifact.expires_at <= now,
            ShopifyPrivacyDeliveryArtifact.revoked_at.isnot(None),
            ShopifyPrivacyDeliveryArtifact.redeemed_at.isnot(None),
        ),
    ).all()
    for row in stale:
        row.ciphertext_encrypted = None
        _audit(db, row.request_id, "purged", "fixture_cleanup")
    db.commit()
    return len(stale)
