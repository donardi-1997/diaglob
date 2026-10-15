"""Merchant-authenticated access to encrypted *synthetic* GDPR artifacts.

No issuance from HTTP. Deliberately disabled for production databases.
Neither query strings nor URLs ever contain access tokens.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership, Store
from .deps import get_current_membership
from .store_access import require_authorized_path_store
from ..services.shopify_privacy_secure_delivery import (
    ShopifyPrivacySecureDeliveryError,
    redeem_synthetic_secure_delivery,
    revoke_synthetic_secure_delivery,
)

router = APIRouter()


def _map_delivery_error(exc: ShopifyPrivacySecureDeliveryError):
    if str(exc) == "LIVE_PRIVACY_DELIVERY_DISABLED":
        raise HTTPException(status_code=503, detail="PRIVACY_DELIVERY_NOT_ENABLED") from exc
    # Public error must not reveal case ownership, token validity or user IDs.
    raise HTTPException(status_code=404, detail="PRIVACY_DELIVERY_UNAVAILABLE") from exc


@router.get(
    "/api/stores/{store_id}/shopify/privacy/cases/{request_id}/delivery",
)
def download_shopify_synthetic_privacy_artifact(
    store_id: int,
    request_id: str,
    x_privacy_delivery_token: str | None = Header(
        None, alias="X-Privacy-Delivery-Token",
    ),
    membership: OrganizationMembership = Depends(get_current_membership),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
):
    """Require merchant Bearer authentication AND recipient-specific ticket."""
    try:
        result = redeem_synthetic_secure_delivery(
            db, request_id=request_id, organization_id=membership.organization_id,
            store_id=store.id, recipient_user_id=membership.user_id,
            token=x_privacy_delivery_token,
        )
    except ShopifyPrivacySecureDeliveryError as exc:
        _map_delivery_error(exc)
    return Response(
        content=result.ciphertext,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Synthetic-Privacy-Artifact": "true",
            "X-Artifact-SHA256": result.sha256,
            "Content-Disposition": 'attachment; filename="diaglob-privacy-test.enc"',
        },
    )


@router.post(
    "/api/stores/{store_id}/shopify/privacy/cases/{request_id}/delivery/revoke",
)
def revoke_shopify_synthetic_privacy_artifact(
    store_id: int,
    request_id: str,
    x_privacy_delivery_token: str | None = Header(
        None, alias="X-Privacy-Delivery-Token",
    ),
    membership: OrganizationMembership = Depends(get_current_membership),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
):
    try:
        success = revoke_synthetic_secure_delivery(
            db, request_id=request_id, organization_id=membership.organization_id,
            store_id=store.id, recipient_user_id=membership.user_id,
            token=x_privacy_delivery_token,
        )
    except ShopifyPrivacySecureDeliveryError as exc:
        _map_delivery_error(exc)
    if not success:
        raise HTTPException(status_code=404, detail="PRIVACY_DELIVERY_UNAVAILABLE")
    return {"revoked": True, "synthetic_only": True, "fulfillment_complete": False}
