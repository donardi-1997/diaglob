"""Recipient-authenticated delivery of a real, explicitly PARTIAL local export.

Requires a permit signed outside the app. Unlike fixture transport, PostgreSQL
is supported; live execution remains disabled until operator policy adoption.
No delivery in this module can complete the overall Shopify privacy case.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyAuditEvent, ShopifyPrivacyDeliveryArtifact
from ..shopify_security import decrypt_shopify_secret
from .shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError, require_execution_policy, verify_execution_permit,
)
from .shopify_privacy_local_execution import (
    local_privacy_targets, owned_privacy_receipt, require_privacy_owner, scope_digest,
)
from .shopify_privacy_local_processor import ShopifyLocalPrivacyError, build_encrypted_local_customer_export
from .shopify_privacy_lock import lock_shopify_privacy_scope


def _cipher() -> Fernet:
    try:
        return Fernet(os.environ.get("SHOPIFY_PRIVACY_DELIVERY_KEY", "").encode("ascii"))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ShopifyPrivacyExecutionError("PRIVACY_DELIVERY_KEY_UNAVAILABLE") from exc


def issue_local_privacy_delivery(db: Session, *, request_id: str, organization_id: int,
                                 store_id: int, user_id: int, permit_token: str) -> dict:
    require_privacy_owner(db, organization_id=organization_id, store_id=store_id, user_id=user_id)
    policy = require_execution_policy()
    cipher = _cipher()
    lock_shopify_privacy_scope(db, organization_id, store_id)
    receipt = owned_privacy_receipt(db, request_id=request_id, organization_id=organization_id, store_id=store_id)
    if receipt.topic != "customers/data_request":
        raise ShopifyPrivacyExecutionError("DATA_REQUEST_TOPIC_REQUIRED")
    targets = local_privacy_targets(db, receipt)
    verify_execution_permit(permit_token, operation="local_export", request_id=request_id,
        organization_id=organization_id, store_id=store_id, scope_sha256=scope_digest(receipt, targets))
    try:
        export = build_encrypted_local_customer_export(db, request_id=request_id)
    except ShopifyLocalPrivacyError as exc:
        raise ShopifyPrivacyExecutionError("PRIVACY_SCOPE_UNVERIFIED") from exc
    if export.requested_orders_not_resolved:
        raise ShopifyPrivacyExecutionError("REQUESTED_ORDER_SCOPE_UNRESOLVED")
    plaintext = decrypt_shopify_secret(export.encrypted_payload).encode("utf-8")
    if len(plaintext) > policy["export_max_bytes"]:
        raise ShopifyPrivacyExecutionError("EXPORT_PAYLOAD_LIMIT")
    digest = hashlib.sha256(plaintext).hexdigest()
    envelope = json.dumps({"schema": "diaglob.shopify.recipient_local_export.v1",
        "request_id": request_id, "organization_id": organization_id, "store_id": store_id,
        "recipient_user_id": user_id, "payload": json.loads(plaintext)}, separators=(",", ":")).encode()
    token = secrets.token_urlsafe(48)
    now = datetime.utcnow()
    try:
        # Reissuance revokes the old recipient's active tickets, not other users.
        db.query(ShopifyPrivacyDeliveryArtifact).filter(
            ShopifyPrivacyDeliveryArtifact.request_id == request_id,
            ShopifyPrivacyDeliveryArtifact.organization_id == organization_id,
            ShopifyPrivacyDeliveryArtifact.store_id == store_id,
            ShopifyPrivacyDeliveryArtifact.recipient_user_id == user_id,
            ShopifyPrivacyDeliveryArtifact.synthetic_only.is_(False),
            ShopifyPrivacyDeliveryArtifact.redeemed_at.is_(None),
            ShopifyPrivacyDeliveryArtifact.revoked_at.is_(None),
        ).update({"revoked_at": now, "ciphertext_encrypted": None}, synchronize_session=False)
        db.add(ShopifyPrivacyDeliveryArtifact(request_id=request_id, organization_id=organization_id,
            store_id=store_id, recipient_user_id=user_id,
            token_digest=hashlib.sha256(token.encode()).hexdigest(), artifact_sha256=digest,
            ciphertext_encrypted=cipher.encrypt(envelope).decode("ascii"), synthetic_only=False,
            expires_at=now + timedelta(seconds=policy["export_ticket_ttl_seconds"]), created_at=now))
        db.add(ShopifyPrivacyAuditEvent(request_id=request_id, event_type="local_export_prepared",
            from_status=receipt.status, to_status=receipt.status, reason_code="partial_export_recipient_bound",
            actor_type="independently_permitted_worker", created_at=now))
        db.commit()
    except Exception:
        db.rollback()
        raise
    # Returned only by a merchant-owner authenticated POST, never logs or URL.
    return {"delivery_token": token, "expires_in_seconds": policy["export_ticket_ttl_seconds"],
            "partial_export": True, "fulfillment_complete": False}


def redeem_local_privacy_delivery(db: Session, *, request_id: str, organization_id: int,
                                  store_id: int, user_id: int, token: str | None) -> bytes:
    require_privacy_owner(db, organization_id=organization_id, store_id=store_id, user_id=user_id)
    require_execution_policy()
    lock_shopify_privacy_scope(db, organization_id, store_id)
    if not isinstance(token, str) or re.fullmatch(r"[A-Za-z0-9_-]{64}", token) is None:
        raise ShopifyPrivacyExecutionError("PRIVACY_DELIVERY_UNAVAILABLE")
    receipt = owned_privacy_receipt(db, request_id=request_id, organization_id=organization_id, store_id=store_id)
    if receipt.topic != "customers/data_request":
        raise ShopifyPrivacyExecutionError("PRIVACY_DELIVERY_UNAVAILABLE")
    # The customer/shop mapping must still be valid at download time too.
    local_privacy_targets(db, receipt)
    filters = (
        ShopifyPrivacyDeliveryArtifact.request_id == request_id,
        ShopifyPrivacyDeliveryArtifact.organization_id == organization_id,
        ShopifyPrivacyDeliveryArtifact.store_id == store_id,
        ShopifyPrivacyDeliveryArtifact.recipient_user_id == user_id,
        ShopifyPrivacyDeliveryArtifact.token_digest == hashlib.sha256(token.encode()).hexdigest(),
        ShopifyPrivacyDeliveryArtifact.synthetic_only.is_(False),
        ShopifyPrivacyDeliveryArtifact.redeemed_at.is_(None),
        ShopifyPrivacyDeliveryArtifact.revoked_at.is_(None),
        ShopifyPrivacyDeliveryArtifact.expires_at > datetime.utcnow(),
        ShopifyPrivacyDeliveryArtifact.ciphertext_encrypted.is_not(None),
    )
    artifact = db.query(ShopifyPrivacyDeliveryArtifact).filter(*filters).first()
    if artifact is None:
        raise ShopifyPrivacyExecutionError("PRIVACY_DELIVERY_UNAVAILABLE")
    try:
        envelope = json.loads(_cipher().decrypt(artifact.ciphertext_encrypted.encode("ascii")))
        if not isinstance(envelope, dict) or any(envelope.get(name) != expected for name, expected in (
            ("schema", "diaglob.shopify.recipient_local_export.v1"), ("request_id", request_id),
            ("organization_id", organization_id), ("store_id", store_id), ("recipient_user_id", user_id),
        )):
            raise ShopifyPrivacyExecutionError("PRIVACY_DELIVERY_UNAVAILABLE")
        payload = envelope.get("payload")
        plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (InvalidToken, ValueError, TypeError, UnicodeError) as exc:
        raise ShopifyPrivacyExecutionError("PRIVACY_DELIVERY_UNAVAILABLE") from exc
    if (
        not isinstance(payload, dict) or payload.get("request_id") != request_id
        or payload.get("schema") != "diaglob.shopify.local_customer_export.v1"
        or payload.get("complete") is not False
        or hashlib.sha256(plaintext).hexdigest() != artifact.artifact_sha256
    ):
        raise ShopifyPrivacyExecutionError("PRIVACY_DELIVERY_UNAVAILABLE")
    try:
        consumed = db.execute(update(ShopifyPrivacyDeliveryArtifact).where(*filters).values(
            redeemed_at=datetime.utcnow(), ciphertext_encrypted=None,
        ).execution_options(synchronize_session=False))
        if consumed.rowcount != 1:
            raise ShopifyPrivacyExecutionError("PRIVACY_DELIVERY_UNAVAILABLE")
        db.add(ShopifyPrivacyAuditEvent(request_id=request_id, event_type="local_export_downloaded",
            from_status=receipt.status, to_status=receipt.status, reason_code="partial_export_one_time_delivery",
            actor_type="authenticated_privacy_owner", created_at=datetime.utcnow()))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return plaintext


def purge_expired_local_privacy_deliveries(db: Session) -> int:
    require_execution_policy()
    result = db.execute(update(ShopifyPrivacyDeliveryArtifact).where(
        ShopifyPrivacyDeliveryArtifact.synthetic_only.is_(False),
        ShopifyPrivacyDeliveryArtifact.expires_at <= datetime.utcnow(),
        ShopifyPrivacyDeliveryArtifact.ciphertext_encrypted.is_not(None),
    ).values(ciphertext_encrypted=None, revoked_at=datetime.utcnow()))
    db.commit()
    return result.rowcount
