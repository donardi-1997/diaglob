"""Shared authorization helpers for path-scoped store endpoints."""

from fastapi import HTTPException

from ..models import Store


def ensure_membership_store_access(membership, store: Store) -> Store:
    """Require access to a store when a membership is store-restricted."""
    if membership.all_stores:
        return store

    allowed_store_ids = {allowed.id for allowed in membership.stores}
    if store.id not in allowed_store_ids:
        raise HTTPException(status_code=403, detail="Store access denied")

    return store
