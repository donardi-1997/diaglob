"""Shared authorization helpers for path-scoped store endpoints."""

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Conversation, OrganizationMembership
from .deps import get_current_membership

from ..models import Store


def ensure_membership_store_access(membership, store: Store) -> Store:
    """Require access to a store when a membership is store-restricted."""
    if membership.all_stores:
        return store

    allowed_store_ids = {allowed.id for allowed in membership.stores}
    if store.id not in allowed_store_ids:
        raise HTTPException(status_code=403, detail="Store access denied")

    return store



def require_authorized_path_store(
    store_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> Store:
    """Authorize every path-scoped store against tenant and membership.

    A same-organization store is not automatically visible to a member with
    restricted store assignments. Do not infer access from the store ID or
    solely from an organization-scoped service query.
    """
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if store is None:
        raise HTTPException(status_code=404, detail="Store not found")
    return ensure_membership_store_access(membership, store)


def require_authorized_path_conversation(
    conversation_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> Conversation:
    """Authorize conversation-addressed operations against their actual store."""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.organization_id == membership.organization_id,
    ).first()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    require_authorized_path_store(conversation.store_id, membership, db)
    return conversation
