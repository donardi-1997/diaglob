"""Operator-permitted execution of the known local Shopify privacy surfaces.

Not a global fulfillment engine: unknown/shared content and external processors
remain outstanding. No execution is possible from a boolean or submitted hash.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import Base
from ..model_domains.conversational_checkout import ConversationalCheckout
from ..models import (
    Conversation, Customer, CustomerStoreProfile, Message, Order, OrderItem,
    MembershipStore, Organization, OrganizationMembership, ShopifyPrivacyAuditEvent,
    ShopifyPrivacyDeliveryArtifact, ShopifyPrivacyRequest, ShopifyPrivacySuppression, Store, User,
)
from .shopify_privacy_execution_authorization import (
    ShopifyPrivacyExecutionError, require_execution_policy, verify_execution_permit,
)
from .shopify_privacy_local_processor import (
    ShopifyLocalPrivacyError, _canonical_order_ids, _receipt, _selectors, build_local_redaction_manifest,
)
from .shopify_privacy_lock import lock_shopify_privacy_scope
from .shopify_privacy_restore import (
    checkpoint_for_suppression_rows, create_shopify_suppression_checkpoint,
)
from .shopify_privacy_suppression import (
    _digest, _domain_fingerprint, _key_fingerprint, _secret, _tombstone_specs,
)


def require_privacy_owner(db: Session, *, organization_id: int, store_id: int, user_id: int) -> None:
    owner = db.query(OrganizationMembership.id).join(
        User, User.id == OrganizationMembership.user_id,
    ).join(Organization, Organization.id == OrganizationMembership.organization_id).filter(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.user_id == user_id,
        OrganizationMembership.role == "owner", OrganizationMembership.active.is_(True),
        User.active.is_(True), Organization.active.is_(True),
        or_(OrganizationMembership.all_stores.is_(True), db.query(MembershipStore.membership_id).filter(
            MembershipStore.membership_id == OrganizationMembership.id,
            MembershipStore.store_id == store_id,
        ).exists()),
    ).first()
    store = db.query(Store.id).filter(
        Store.id == store_id, Store.organization_id == organization_id,
        Store.deleted.is_(False), Store.active.is_(True),
    ).first()
    if owner is None or store is None:
        raise ShopifyPrivacyExecutionError("PRIVACY_OWNER_ACCESS_REQUIRED")


def owned_privacy_receipt(db: Session, *, request_id: str, organization_id: int, store_id: int):
    if not isinstance(request_id, str) or len(request_id) != 64 or any(c not in "0123456789abcdef" for c in request_id):
        raise ShopifyPrivacyExecutionError("PRIVACY_CASE_UNAVAILABLE")
    receipt = db.query(ShopifyPrivacyRequest).filter(
        ShopifyPrivacyRequest.request_id == request_id,
        ShopifyPrivacyRequest.organization_id == organization_id,
        ShopifyPrivacyRequest.store_id == store_id,
    ).with_for_update().first()
    if receipt is None:
        raise ShopifyPrivacyExecutionError("PRIVACY_CASE_UNAVAILABLE")
    if receipt.completed_at is not None or receipt.status == "completed":
        raise ShopifyPrivacyExecutionError("HISTORICAL_COMPLETION_REQUIRES_REVIEW")
    signed = db.query(ShopifyPrivacyAuditEvent.id).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "received",
        ShopifyPrivacyAuditEvent.actor_type == "shopify_hmac_verified",
    ).first()
    if signed is None:
        raise ShopifyPrivacyExecutionError("SIGNED_INTAKE_REQUIRED")
    return receipt


def local_privacy_targets(db: Session, receipt: ShopifyPrivacyRequest) -> dict[str, list[int]]:
    """Read only IDs. The existing manifest checks subject/order provenance."""
    try:
        _receipt(db, receipt.request_id)
        if receipt.topic in {"customers/redact", "shop/redact"}:
            build_local_redaction_manifest(db, request_id=receipt.request_id)
        org, store = receipt.organization_id, receipt.store_id
        profile = db.query(CustomerStoreProfile).filter(
            CustomerStoreProfile.organization_id == org, CustomerStoreProfile.store_id == store,
        )
        if receipt.topic != "shop/redact":
            external_id = str(_selectors(receipt)["customer"]["id"]).strip()
            profile = profile.filter(CustomerStoreProfile.external_customer_id == external_id)
        profiles = profile.with_entities(CustomerStoreProfile.id, CustomerStoreProfile.customer_id).limit(251).all()
        customers = {row.customer_id for row in profiles}
        if len(profiles) > 250 or (receipt.topic != "shop/redact" and len(profiles) != 1):
            raise ShopifyPrivacyExecutionError("PRIVACY_SCOPE_LIMIT_OR_AMBIGUITY")
        if customers != {row[0] for row in db.query(Customer.id).filter(
            Customer.organization_id == org, Customer.id.in_(customers),
        ).all()}:
            raise ShopifyPrivacyExecutionError("PRIVACY_CUSTOMER_TENANCY_MISMATCH")
        targets = {"customer_store_profiles": [row.id for row in profiles]}
        for model in (Order, Conversation, ConversationalCheckout):
            if db.query(model.id).outerjoin(Customer, Customer.id == model.customer_id).filter(
                model.organization_id == org, model.store_id == store,
                model.customer_id.is_not(None),
                or_(Customer.id.is_(None), Customer.organization_id != org),
            ).first() is not None:
                raise ShopifyPrivacyExecutionError("PRIVACY_CUSTOMER_TENANCY_MISMATCH")
            query = db.query(model.id).filter(model.organization_id == org, model.store_id == store)
            if receipt.topic != "shop/redact":
                query = query.filter(model.customer_id.in_(customers))
            if model is Order and receipt.topic != "shop/redact":
                selectors = _selectors(receipt)
                requested = _canonical_order_ids(selectors.get(
                    "orders_to_redact" if receipt.topic == "customers/redact" else "orders_requested",
                ))
                if requested is not None:
                    aliases = set(requested)
                    aliases |= {f"gid://shopify/Order/{x}" for x in aliases}
                    query = query.filter(Order.shopify_order_id.in_(aliases))
            targets[model.__tablename__] = [row[0] for row in query.order_by(model.id).limit(251).all()]
        targets["order_items"] = [row[0] for row in db.query(OrderItem.id).filter(
            OrderItem.order_id.in_(targets["orders"]),
            OrderItem.organization_id == org, OrderItem.store_id == store,
        ).limit(251).all()]
        targets["messages"] = [row[0] for row in db.query(Message.id).filter(
            Message.conversation_id.in_(targets["conversations"]),
        ).limit(251).all()]
        if any(len(ids) > 250 for ids in targets.values()):
            raise ShopifyPrivacyExecutionError("PRIVACY_SCOPE_LIMIT_OR_AMBIGUITY")
        # A checkout must inherit the same scoped parent, not merely claim it.
        if db.query(ConversationalCheckout.id).filter(
            ConversationalCheckout.id.in_(targets[ConversationalCheckout.__tablename__]),
            ~ConversationalCheckout.conversation_id.in_(targets["conversations"]),
        ).first() is not None:
            raise ShopifyPrivacyExecutionError("PRIVACY_CHECKOUT_PARENT_MISMATCH")
        return targets
    except (ShopifyLocalPrivacyError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ShopifyPrivacyExecutionError):
            raise
        raise ShopifyPrivacyExecutionError("PRIVACY_SCOPE_UNVERIFIED") from exc


def scope_digest(receipt: ShopifyPrivacyRequest, targets: dict) -> str:
    payload = [receipt.request_id, receipt.topic, receipt.organization_id, receipt.store_id,
               hashlib.sha256(receipt.selector_encrypted.encode()).hexdigest(),
               {name: sorted(ids) for name, ids in sorted(targets.items())}]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def planned_suppressions(db: Session, receipt: ShopifyPrivacyRequest):
    key = _secret()
    rows = db.query(ShopifyPrivacySuppression).all()
    planned = [SimpleNamespace(**{name: getattr(row, name) for name in (
        "organization_id", "store_id", "request_id", "kind", "selector_digest",
        "key_fingerprint", "domain_fingerprint", "status",
    )}) for row in rows]
    existing = {(r.organization_id, r.store_id, r.kind, r.selector_digest): r for r in planned}
    fingerprint = _domain_fingerprint(key, receipt.organization_id, receipt.store_id, receipt.shop_domain)
    additions = []
    for kind, value in _tombstone_specs(receipt):
        digest = _digest(key=key, organization_id=receipt.organization_id, store_id=receipt.store_id,
                         domain=receipt.shop_domain, kind=kind, identity=value)
        index = (receipt.organization_id, receipt.store_id, kind, digest)
        previous = existing.get(index)
        if previous is not None:
            if previous.domain_fingerprint != fingerprint or previous.key_fingerprint != _key_fingerprint(key):
                raise ShopifyPrivacyExecutionError("PRIVACY_SUPPRESSION_IDENTITY_MISMATCH")
            previous.status = "active"
        else:
            previous = SimpleNamespace(organization_id=receipt.organization_id, store_id=receipt.store_id,
                request_id=receipt.request_id, kind=kind, selector_digest=digest,
                key_fingerprint=_key_fingerprint(key), domain_fingerprint=fingerprint, status="active")
            planned.append(previous)
        additions.append(previous)
    return additions, checkpoint_for_suppression_rows(planned, key=key)


def preview_local_privacy_execution(db: Session, *, request_id: str, organization_id: int, store_id: int, user_id: int) -> dict:
    require_privacy_owner(db, organization_id=organization_id, store_id=store_id, user_id=user_id)
    receipt = owned_privacy_receipt(db, request_id=request_id, organization_id=organization_id, store_id=store_id)
    targets = local_privacy_targets(db, receipt)
    result = {"request_id": request_id, "scope_sha256": scope_digest(receipt, targets),
              "source_counts": {name: len(ids) for name, ids in targets.items()},
              "fulfillment_complete": False, "external_processors_verified": False}
    if receipt.topic in {"customers/redact", "shop/redact"}:
        _, result["planned_restore_checkpoint"] = planned_suppressions(db, receipt)
    return result


def execute_local_privacy_redaction(db: Session, *, request_id: str, organization_id: int,
                                    store_id: int, user_id: int, permit_token: str) -> dict:
    require_privacy_owner(db, organization_id=organization_id, store_id=store_id, user_id=user_id)
    require_execution_policy()
    lock_shopify_privacy_scope(db, organization_id, store_id)
    receipt = owned_privacy_receipt(db, request_id=request_id, organization_id=organization_id, store_id=store_id)
    # Retrying a completed LOCAL step does not re-resolve a deliberately erased
    # customer profile or claim that other surfaces have been fulfilled.
    audit = db.query(ShopifyPrivacyAuditEvent).filter(
        ShopifyPrivacyAuditEvent.request_id == request_id,
        ShopifyPrivacyAuditEvent.event_type == "local_redaction_executed",
        ShopifyPrivacyAuditEvent.actor_type == "independently_permitted_worker",
    ).first()
    if audit is not None:
        verify_execution_permit(permit_token, operation="local_redaction", request_id=request_id,
            organization_id=organization_id, store_id=store_id, scope_sha256=audit.reason_code)
        return {"local_redaction_executed": True, "idempotent": True, "fulfillment_complete": False}
    if receipt.topic not in {"customers/redact", "shop/redact"}:
        raise ShopifyPrivacyExecutionError("REDACTION_TOPIC_REQUIRED")
    targets = local_privacy_targets(db, receipt)
    digest = scope_digest(receipt, targets)
    permit = verify_execution_permit(permit_token, operation="local_redaction", request_id=request_id,
        organization_id=organization_id, store_id=store_id, scope_sha256=digest)
    additions, checkpoint = planned_suppressions(db, receipt)
    if (
        permit.restore_checkpoint_hmac != checkpoint["checkpoint_hmac"]
        or permit.restore_min_records != checkpoint["total_records"]
        or os.getenv("SHOPIFY_PRIVACY_RESTORE_CHECKPOINT_HMAC") != permit.restore_checkpoint_hmac
        or os.getenv("SHOPIFY_PRIVACY_RESTORE_MIN_RECORDS") != str(permit.restore_min_records)
    ):
        raise ShopifyPrivacyExecutionError("INDEPENDENT_RESTORE_CHECKPOINT_REQUIRED")
    try:
        # Invalidate temporary snapshots for this store too. They can contain
        # pre-redaction subject data; fresh exports need a fresh scoped permit.
        db.query(ShopifyPrivacyDeliveryArtifact).filter(
            ShopifyPrivacyDeliveryArtifact.organization_id == organization_id,
            ShopifyPrivacyDeliveryArtifact.store_id == store_id,
            ShopifyPrivacyDeliveryArtifact.synthetic_only.is_(False),
            ShopifyPrivacyDeliveryArtifact.ciphertext_encrypted.is_not(None),
        ).update({"ciphertext_encrypted": None, "revoked_at": datetime.utcnow()}, synchronize_session=False)
        customer_ids = {row[0] for row in db.query(CustomerStoreProfile.customer_id).filter(
            CustomerStoreProfile.id.in_(targets["customer_store_profiles"]),
        ).all()}
        anonymous = None
        if targets["conversations"] or targets[ConversationalCheckout.__tablename__]:
            anonymous = Customer(organization_id=organization_id, name="Redacted Shopify customer", phone="")
            db.add(anonymous)
            db.flush()
        for model, changes in (
            (Order, {"customer_id": None, "note": None, "shipping_address": None, "invoice_url": None,
                     "external_last_error": None, "shopify_order_id": None, "shopify_draft_order_id": None,
                     "external_order_id": None, "idempotency_key": None}),
            (OrderItem, {"title": "[redacted]", "sku": None, "shopify_line_item_id": None, "shopify_variant_id": None}),
            (Conversation, {"customer_id": anonymous.id if anonymous else None, "preview": "", "tags": "", "unread": 0, "mode": "manual"}),
            (Message, {"text": "[redacted]", "external_message_id": None}),
        ):
            if targets[model.__tablename__]:
                db.query(model).filter(model.id.in_(targets[model.__tablename__])).update(changes, synchronize_session=False)
        for row in db.query(Order).filter(Order.id.in_(targets["orders"])):
            row.order_number = f"redacted-{row.id}"
        for row in db.query(ConversationalCheckout).filter(ConversationalCheckout.id.in_(targets[ConversationalCheckout.__tablename__])):
            for field in ("customer_name", "phone", "address_raw", "address_line", "address_complement",
                          "neighborhood", "city", "region", "postal_code", "delivery_reference", "failure_reason"):
                setattr(row, field, None if row.__table__.c[field].nullable else "")
            row.customer_id = anonymous.id
            row.status = "cancelled"
            row.address_confirmed = False
            row.customer_confirmed = False
            row.address_confirmed_at = None
            row.customer_confirmed_at = None
            row.product_title = None
            row.variant_title = None
            row.address_confidence_score = 0
            row.address_validation_status = "pending"
        db.query(CustomerStoreProfile).filter(CustomerStoreProfile.id.in_(targets["customer_store_profiles"])).delete(synchronize_session=False)
        db.flush()
        shared = 0
        for customer_id in customer_ids:
            # Negative integrity check only. Never read another tenant's data.
            referenced = any(db.execute(select(table.c.customer_id).where(
                table.c.customer_id == customer_id,
            ).limit(1)).first() is not None for table in Base.metadata.tables.values() if "customer_id" in table.c)
            if referenced:
                shared += 1
            else:
                db.query(Customer).filter(Customer.id == customer_id, Customer.organization_id == organization_id).update(
                    {"name": "Redacted Shopify customer", "phone": "", "email": None, "country_code": None},
                    synchronize_session=False,
                )
        for item in additions:
            row = db.query(ShopifyPrivacySuppression).filter(
                ShopifyPrivacySuppression.organization_id == organization_id,
                ShopifyPrivacySuppression.store_id == store_id,
                ShopifyPrivacySuppression.kind == item.kind,
                ShopifyPrivacySuppression.selector_digest == item.selector_digest,
            ).first()
            if row is None:
                row = ShopifyPrivacySuppression(**vars(item), created_at=datetime.utcnow())
                db.add(row)
            row.status = "active"
            row.activated_at = datetime.utcnow()
        db.flush()
        if create_shopify_suppression_checkpoint(db)["checkpoint_hmac"] != permit.restore_checkpoint_hmac:
            raise ShopifyPrivacyExecutionError("PRIVACY_SUPPRESSION_PLAN_CHANGED")
        db.add(ShopifyPrivacyAuditEvent(request_id=request_id, event_type="local_redaction_executed",
            from_status=receipt.status, to_status=receipt.status, reason_code=digest,
            actor_type="independently_permitted_worker", created_at=datetime.utcnow()))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"local_redaction_executed": True, "idempotent": False,
            "shared_customer_records_preserved": shared, "fulfillment_complete": False,
            "external_processors_verified": False, "backup_erasure_verified": False}
