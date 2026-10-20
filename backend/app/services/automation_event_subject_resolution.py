"""Resolve automation provenance from persisted commerce entities, not payloads.

A matching local store profile is NOT a verified Shopify privacy subject; it
only permits the provenance writer to note a *local* customer relationship.
Do not read free-form text, customer emails, phones or message bodies.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Conversation, Customer, CustomerStoreProfile, Order


def _valid_id(value: object) -> bool:
    return type(value) is int and value > 0


def _locally_linked_customer(
    db: Session, *, organization_id: int, store_id: int,
    customer_id: int | None, required_external_id: str | None = None,
) -> int | None:
    if not _valid_id(customer_id):
        return None
    q = (
        db.query(CustomerStoreProfile.id)
        .join(Customer, Customer.id == CustomerStoreProfile.customer_id)
        .filter(
            Customer.id == customer_id,
            Customer.organization_id == organization_id,
            CustomerStoreProfile.organization_id == organization_id,
            CustomerStoreProfile.store_id == store_id,
            CustomerStoreProfile.customer_id == customer_id,
            CustomerStoreProfile.external_customer_id.is_not(None),
            CustomerStoreProfile.external_customer_id != "",
        )
    )
    if required_external_id is not None:
        q = q.filter(
            CustomerStoreProfile.external_customer_id == required_external_id
        )
    # Ambiguous or missing local identity -> no customer assertion. A
    # Shopify external ID must also identify exactly one local profile in
    # this store: two local buyers with the same external ID are NOT safe.
    if len(q.limit(2).all()) != 1:
        return None
    if required_external_id is not None:
        claimants = db.query(CustomerStoreProfile.customer_id).filter(
            CustomerStoreProfile.organization_id == organization_id,
            CustomerStoreProfile.store_id == store_id,
            CustomerStoreProfile.external_customer_id == required_external_id,
        ).limit(2).all()
        if len(claimants) != 1 or claimants[0].customer_id != customer_id:
            return None
    return customer_id


def resolve_shopify_order_event_customer(
    db: Session, *, organization_id: int, store_id: int,
    order_id: int, external_shopify_customer_id: str | None,
) -> int | None:
    """Require exact persisted order + original Shopify customer ID.

    Called only from authenticated, signed Shopify order webhooks AFTER order
    commit. IDs from an event payload alone never establish the relationship.
    """
    if (
        not _valid_id(organization_id) or not _valid_id(store_id)
        or not _valid_id(order_id)
        or not isinstance(external_shopify_customer_id, str)
        or not external_shopify_customer_id.strip()
    ):
        return None
    external = external_shopify_customer_id.strip()
    row = db.query(Order.customer_id).filter(
        Order.id == order_id,
        Order.organization_id == organization_id,
        Order.store_id == store_id,
        Order.source == "shopify",
    ).first()
    if row is None:
        return None
    return _locally_linked_customer(
        db, organization_id=organization_id, store_id=store_id,
        customer_id=row.customer_id, required_external_id=external,
    )


def resolve_conversation_event_customer(
    db: Session, *, organization_id: int, store_id: int,
    conversation_id: int,
) -> int | None:
    """Resolve one persisted conversation scoped to org/store.

    WhatsApp, Telegram and Instagram sender identifiers are NOT Shopify IDs.
    A local profile may be recorded as unverified, never as Shopify-confirmed.
    """
    if (
        not _valid_id(organization_id) or not _valid_id(store_id)
        or not _valid_id(conversation_id)
    ):
        return None
    row = db.query(Conversation.customer_id).filter(
        Conversation.id == conversation_id,
        Conversation.organization_id == organization_id,
        Conversation.store_id == store_id,
    ).first()
    if row is None:
        return None
    return _locally_linked_customer(
        db, organization_id=organization_id, store_id=store_id,
        customer_id=row.customer_id,
    )
