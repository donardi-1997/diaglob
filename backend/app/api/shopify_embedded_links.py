"""Explicit Shopify Admin subject linking; no Cognito login in iframe.

Only an existing DIAGLOB member can issue a one-time code via the normal
Cognito-authenticated portal. Only a fresh verified Shopify ID token may
redeem it. Shop/user scope is rechecked on every embedded API read.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership, Store
from ..services.shopify_embedded_identity import ShopifyIdTokenError, verify_shopify_id_token
from ..services.shopify_embedded_membership import (
    issue_link_code, redeem_link_code, revoke_member_links,
)
from .deps import get_current_membership
from .store_access import require_authorized_path_store

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


class EmbeddedLinkCode(BaseModel):
    code: str = Field(min_length=40, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/api/stores/{store_id}/shopify/embedded/link-code")
def create_embedded_link_code(
    store_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
) -> dict:
    if store.id != store_id:
        raise HTTPException(status_code=404, detail="Store not found")
    return issue_link_code(db, membership_id=membership.id, store_id=store.id)


@router.delete("/api/stores/{store_id}/shopify/embedded/link")
def unlink_embedded_user(
    store_id: int,
    membership: OrganizationMembership = Depends(get_current_membership),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
) -> dict:
    if store.id != store_id:
        raise HTTPException(status_code=404, detail="Store not found")
    return {"revoked": revoke_member_links(db, membership_id=membership.id, store_id=store.id)}


@router.post("/api/shopify/embedded/link")
def claim_embedded_link(
    payload: EmbeddedLinkCode,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Shopify ID token required")
    try:
        identity = verify_shopify_id_token(credentials.credentials)
    except ShopifyIdTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid Shopify session") from exc
    return redeem_link_code(db, identity=identity, code=payload.code)
