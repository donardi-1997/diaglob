"""Store-scoped, keyed Shopify privacy tombstones and replay prevention.

Prepared tombstones have NO effect until explicitly activated. Production
activation intentionally does not exist pending approved retention/erasure
policy. SQLite synthetic activation is test-only. Identifiers never persist as plaintext or unkeyed digests. Keyed digests
remain pseudonymous personal data requiring controlled retention and access.
No routine can mark GDPR complete.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ShopifyPrivacyAuditEvent, ShopifyPrivacyRequest, ShopifyPrivacySuppression, Store
from ..shopify_oauth import normalize_shop_domain
from ..shopify_security import decrypt_shopify_secret

_VALID_RECEIPT = re.compile(r"^[0-9a-f]{64}$")
_VALID_RESOURCE = re.compile(r"^(?:gid://shopify/(Customer|Order)/)?([0-9]{1,30})$")


class ShopifySuppressionError(ValueError):
    """PII-free error codes for a blocked or unresolved suppression operation."""


def _secret() -> bytes:
    value = os.getenv("SHOPIFY_PRIVACY_SUPPRESSION_KEY", "")
    if len(value.encode("utf-8")) < 32:
        raise ShopifySuppressionError("SUPPRESSION_KEY_UNAVAILABLE")
    return value.encode("utf-8")


def _key_fingerprint(key: bytes) -> str:
    return hmac.new(key, b"diaglob.shopify.suppression.key-identity.v1",
                    hashlib.sha256).hexdigest()


def _domain_fingerprint(key: bytes, organization_id: int,
                        store_id: int, domain: str) -> str:
    material = json.dumps(
        ["diaglob.shopify.suppression.shop-identity.v1",
         organization_id, store_id, domain], separators=(",", ":"),
    )
    return hmac.new(key, material.encode("utf-8"), hashlib.sha256).hexdigest()


def _require_fingerprint(rows, fingerprint: str) -> None:
    if any(not hmac.compare_digest(x.key_fingerprint, fingerprint) for x in rows):
        raise ShopifySuppressionError("SUPPRESSION_KEY_MISMATCH")


def _numeric_id(value: object, kind: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ShopifySuppressionError("INVALID_SHOPIFY_RESOURCE_ID")
    match = _VALID_RESOURCE.fullmatch(str(value))
    if not match or (match.group(1) is not None and match.group(1).lower() != kind):
        raise ShopifySuppressionError("INVALID_SHOPIFY_RESOURCE_ID")
    return str(int(match.group(2)))


def _email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    if len(normalized) > 320 or "@" not in normalized or not normalized:
        return None
    return normalized


def _phone(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    digits = "".join(ch for ch in value if ch.isascii() and ch.isdigit())
    return digits if 7 <= len(digits) <= 20 else None


def _digest(*, key: bytes, organization_id: int, store_id: int,
            domain: str, kind: str, identity: str) -> str:
    # Structured canonical context: no collisions across shops or ID types.
    context = json.dumps(
        ["diaglob.shopify.privacy.suppression.v1",
         organization_id, store_id, domain, kind, identity],
        separators=(",", ":"),
    )
    return hmac.new(key, context.encode("utf-8"), hashlib.sha256).hexdigest()


def _verified_receipt(db: Session, request_id: str):
    if not isinstance(request_id, str) or not _VALID_RECEIPT.fullmatch(request_id):
        raise ShopifySuppressionError("INVALID_REQUEST_ID")
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
    ).first()
    if receipt is None:
        raise ShopifySuppressionError("REQUEST_NOT_FOUND")
    if receipt.topic not in ("customers/redact", "shop/redact"):
        raise ShopifySuppressionError("REDACTION_TOPIC_REQUIRED")
    signed = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first()
    if signed is None:
        raise ShopifySuppressionError("SIGNED_INTAKE_REQUIRED")
    if not receipt.organization_id or not receipt.store_id:
        raise ShopifySuppressionError("SHOP_UNRESOLVED")
    store = db.query(Store).filter(
        Store.id == receipt.store_id,
        Store.organization_id == receipt.organization_id,
    ).first()
    if store is None or not store.shopify_domain:
        raise ShopifySuppressionError("SHOP_UNRESOLVED")
    try:
        domain = normalize_shop_domain(receipt.shop_domain)
        if normalize_shop_domain(store.shopify_domain) != domain:
            raise ShopifySuppressionError("SHOP_IDENTITY_MISMATCH")
    except (ValueError, AttributeError, TypeError) as exc:
        raise ShopifySuppressionError("SHOP_IDENTITY_MISMATCH") from exc
    return receipt, domain


def _tombstone_specs(receipt: ShopifyPrivacyRequest):
    if receipt.topic == "shop/redact":
        return [("shop", "all")]
    try:
        selectors = json.loads(decrypt_shopify_secret(receipt.selector_encrypted))
    except (RuntimeError, ValueError, TypeError) as exc:
        raise ShopifySuppressionError("SELECTORS_UNAVAILABLE") from exc
    if not isinstance(selectors, dict) or not isinstance(selectors.get("customer"), dict):
        raise ShopifySuppressionError("EXACT_CUSTOMER_REQUIRED")
    subject = selectors["customer"].get("id")
    if subject is None:
        raise ShopifySuppressionError("EXACT_CUSTOMER_REQUIRED")
    specs = [("customer", _numeric_id(subject, "customer"))]
    subject_email = _email(selectors["customer"].get("email"))
    subject_phone = _phone(selectors["customer"].get("phone"))
    if subject_email:
        specs.append(("email", subject_email))
    if subject_phone:
        specs.append(("phone", subject_phone))
    order_ids = selectors.get("orders_to_redact")
    if order_ids is not None:
        if not isinstance(order_ids, list) or len(order_ids) > 500:
            raise ShopifySuppressionError("INVALID_ORDER_SELECTORS")
        specs.extend(("order", _numeric_id(value, "order")) for value in order_ids)
    return sorted(set(specs))


def prepare_shopify_privacy_suppressions(db: Session, *, request_id: str) -> dict:
    """Stage keyed hashes from exact, signed selectors without activating them."""
    receipt, domain = _verified_receipt(db, request_id)
    key = _secret()
    specs = _tombstone_specs(receipt)
    digests = [
        (kind, _digest(
            key=key, organization_id=receipt.organization_id,
            store_id=receipt.store_id, domain=domain, kind=kind, identity=identity,
        ))
        for kind, identity in specs
    ]
    existing = db.query(ShopifyPrivacySuppression).filter(
        ShopifyPrivacySuppression.organization_id == receipt.organization_id,
        ShopifyPrivacySuppression.store_id == receipt.store_id,
    ).all()
    fingerprint = _key_fingerprint(key)
    domain_fingerprint = _domain_fingerprint(
        key, receipt.organization_id, receipt.store_id, domain,
    )
    _require_fingerprint(existing, fingerprint)
    if any(not hmac.compare_digest(row.domain_fingerprint, domain_fingerprint)
           for row in existing):
        raise ShopifySuppressionError("SUPPRESSION_SHOP_IDENTITY_MISMATCH")
    index = {(r.kind, r.selector_digest): r for r in existing}
    new_rows = []
    for kind, digest in digests:
        if (kind, digest) not in index:
            new_rows.append(ShopifyPrivacySuppression(
                request_id=request_id, organization_id=receipt.organization_id,
                store_id=receipt.store_id, kind=kind, selector_digest=digest,
                status="staged", key_fingerprint=fingerprint,
                domain_fingerprint=domain_fingerprint,
                created_at=datetime.utcnow(),
            ))
    if new_rows:
        db.add_all(new_rows)
        db.add(ShopifyPrivacyAuditEvent(
            request_id=request_id, event_type="suppression_staged",
            from_status=receipt.status, to_status=receipt.status,
            reason_code="hashed_selectors_prepared",
            actor_type="internal_privacy_processor", created_at=datetime.utcnow(),
        ))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            # Concurrent reviews must be explicitly reconciled, not silently
            # mark the subject suppressed or authorize processing.
            raise ShopifySuppressionError("SUPPRESSION_STAGE_CONFLICT")
    return {
        "request_id": request_id,
        "expected_selectors": len(digests),
        "newly_staged": len(new_rows),
        "already_present": len(digests) - len(new_rows),
        "activated": False,
        "fulfillment_complete": False,
    }


def inspect_shopify_privacy_suppressions(db: Session, *, request_id: str) -> dict:
    receipt, _ = _verified_receipt(db, request_id)
    rows = db.query(ShopifyPrivacySuppression).filter(
        ShopifyPrivacySuppression.request_id == request_id,
        ShopifyPrivacySuppression.organization_id == receipt.organization_id,
        ShopifyPrivacySuppression.store_id == receipt.store_id,
    ).all()
    return {
        "request_id": request_id,
        "staged": sum(x.status == "staged" for x in rows),
        "active": sum(x.status == "active" for x in rows),
        "live_activation_authorized": False,
        "fulfillment_complete": False,
    }


def activate_synthetic_privacy_suppressions(db: Session, *, request_id: str) -> int:
    """Test-only activation for replay/integration verification on SQLite."""
    if (os.getenv("DIAGLOB_SHOPIFY_PRIVACY_SYNTHETIC_TESTS") != "1"
            or not os.getenv("PYTEST_CURRENT_TEST")
            or db.get_bind().dialect.name != "sqlite"):
        raise ShopifySuppressionError("SYNTHETIC_TEST_ONLY")
    receipt, _ = _verified_receipt(db, request_id)
    rows = db.query(ShopifyPrivacySuppression).filter(
        ShopifyPrivacySuppression.request_id == request_id,
        ShopifyPrivacySuppression.organization_id == receipt.organization_id,
        ShopifyPrivacySuppression.store_id == receipt.store_id,
    ).all()
    if not rows:
        raise ShopifySuppressionError("SUPPRESSIONS_NOT_STAGED")
    changed = 0
    for row in rows:
        if row.status == "staged":
            row.status = "active"
            row.activated_at = datetime.utcnow()
            changed += 1
    if changed:
        db.add(ShopifyPrivacyAuditEvent(
            request_id=request_id, event_type="suppression_test_activated",
            from_status=receipt.status, to_status=receipt.status,
            reason_code="synthetic_replay_guard_test",
            actor_type="synthetic_privacy_test", created_at=datetime.utcnow(),
        ))
        db.commit()
    return changed


def evaluate_shopify_privacy_suppression(
    db: Session, *, organization_id: int, store_id: int, shop_domain: str,
    customer_id: object, order_id: object,
    customer_email: object = None, customer_phone: object = None,
) -> tuple[str | None, bool]:
    """Return (suppression reason, contact-fallback forbidden).

    Active tombstones force a stable key to be present. Without a usable
    customer ID when a customer tombstone exists, fail closed rather than
    recovering customer identity from email or phone. This gate is read-only.
    """
    rows = db.query(ShopifyPrivacySuppression).filter(
        ShopifyPrivacySuppression.organization_id == organization_id,
        ShopifyPrivacySuppression.store_id == store_id,
        ShopifyPrivacySuppression.status == "active",
    ).all()
    if not rows:
        return None, False
    try:
        domain = normalize_shop_domain(shop_domain)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ShopifySuppressionError("SHOP_IDENTITY_MISMATCH") from exc
    # A reused local store ID or changed domain may never bypass a tombstone.
    store = db.query(Store).filter(
        Store.id == store_id, Store.organization_id == organization_id,
    ).first()
    if store is None or not store.shopify_domain:
        raise ShopifySuppressionError("SHOP_IDENTITY_MISMATCH")
    try:
        if normalize_shop_domain(store.shopify_domain) != domain:
            raise ShopifySuppressionError("SHOP_IDENTITY_MISMATCH")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ShopifySuppressionError("SHOP_IDENTITY_MISMATCH") from exc
    # A missing key must never allow a signed suppression to be bypassed.
    key = _secret()
    _require_fingerprint(rows, _key_fingerprint(key))
    expected_domain = _domain_fingerprint(key, organization_id, store_id, domain)
    if any(not hmac.compare_digest(row.domain_fingerprint, expected_domain)
           for row in rows):
        raise ShopifySuppressionError("SUPPRESSION_SHOP_IDENTITY_MISMATCH")
    active = {(x.kind, x.selector_digest) for x in rows}
    if ("shop", _digest(key=key, organization_id=organization_id,
                        store_id=store_id, domain=domain,
                        kind="shop", identity="all")) in active:
        return "shop", True

    if order_id is None:
        # An order event without an ID cannot be trusted for further writes.
        return "order_unresolved", True
    try:
        order_value = _numeric_id(order_id, "order")
    except ShopifySuppressionError:
        return "order_unresolved", True
    order_hash = _digest(key=key, organization_id=organization_id,
                         store_id=store_id, domain=domain,
                         kind="order", identity=order_value)
    if ("order", order_hash) in active:
        return "order", True
    for kind, raw_value, canonicalizer in (
        ("email", customer_email, _email),
        ("phone", customer_phone, _phone),
    ):
        identifier = canonicalizer(raw_value)
        if identifier is not None:
            selector_hash = _digest(
                key=key, organization_id=organization_id,
                store_id=store_id, domain=domain, kind=kind,
                identity=identifier,
            )
            if (kind, selector_hash) in active:
                return kind, True
    customer_blocks = any(x.kind in ("customer", "email", "phone") for x in rows)
    if customer_blocks and customer_id is None:
        return "customer_unresolved", True
    if customer_id is not None:
        try:
            customer_value = _numeric_id(customer_id, "customer")
        except ShopifySuppressionError:
            return "customer_unresolved", True
        customer_hash = _digest(
            key=key, organization_id=organization_id,
            store_id=store_id, domain=domain,
            kind="customer", identity=customer_value,
        )
        if ("customer", customer_hash) in active:
            return "customer", True
    return None, True
