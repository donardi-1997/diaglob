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
from ..services.shopify_privacy_execution_authorization import ShopifyPrivacyExecutionError
from ..services import shopify_privacy_live_delivery as live_delivery
from ..services.shopify_privacy_local_execution import execute_local_privacy_redaction

router = APIRouter()


def _map_live_error(exc: ShopifyPrivacyExecutionError):
    code = str(exc)
    if code in {"LIVE_PRIVACY_PROCESSING_DISABLED", "PRIVACY_OPERATOR_POLICY_REQUIRED", "PRIVACY_POLICY_UNAVAILABLE"}:
        raise HTTPException(status_code=503, detail="PRIVACY_PROCESSING_NOT_ENABLED") from None
    if code == "PRIVACY_OWNER_ACCESS_REQUIRED":
        raise HTTPException(status_code=403, detail="PRIVACY_OWNER_ACCESS_REQUIRED") from None
    raise HTTPException(status_code=409, detail="PRIVACY_OPERATION_UNAVAILABLE") from None


@router.post("/api/stores/{store_id}/shopify/privacy/cases/{request_id}/local-export")
def prepare_permitted_local_export(
    store_id: int, request_id: str,
    x_privacy_execution_permit: str | None = Header(None, alias="X-Privacy-Execution-Permit"),
    membership: OrganizationMembership = Depends(get_current_membership),
    store: Store = Depends(require_authorized_path_store), db: Session = Depends(get_db),
):
    try:
        result = live_delivery.issue_local_privacy_delivery(db, request_id=request_id,
            organization_id=membership.organization_id, store_id=store.id,
            user_id=membership.user_id, permit_token=x_privacy_execution_permit)
    except ShopifyPrivacyExecutionError as exc:
        _map_live_error(exc)
    from fastapi.responses import JSONResponse
    return JSONResponse(result, headers={"Cache-Control": "no-store, private", "Pragma": "no-cache"})


@router.get("/api/stores/{store_id}/shopify/privacy/cases/{request_id}/local-export")
def download_permitted_local_export(
    store_id: int, request_id: str,
    x_privacy_delivery_token: str | None = Header(None, alias="X-Privacy-Delivery-Token"),
    membership: OrganizationMembership = Depends(get_current_membership),
    store: Store = Depends(require_authorized_path_store), db: Session = Depends(get_db),
):
    try:
        data = live_delivery.redeem_local_privacy_delivery(db, request_id=request_id,
            organization_id=membership.organization_id, store_id=store.id,
            user_id=membership.user_id, token=x_privacy_delivery_token)
    except ShopifyPrivacyExecutionError as exc:
        _map_live_error(exc)
    return Response(data, media_type="application/json", headers={
        "Cache-Control": "no-store, private", "Pragma": "no-cache", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff", "X-Partial-Privacy-Export": "true",
        "Content-Disposition": 'attachment; filename="diaglob-local-privacy-export.json"',
    })


@router.post("/api/stores/{store_id}/shopify/privacy/cases/{request_id}/local-redaction")
def execute_permitted_local_redaction(
    store_id: int, request_id: str,
    x_privacy_execution_permit: str | None = Header(None, alias="X-Privacy-Execution-Permit"),
    membership: OrganizationMembership = Depends(get_current_membership),
    store: Store = Depends(require_authorized_path_store), db: Session = Depends(get_db),
):
    try:
        return execute_local_privacy_redaction(db, request_id=request_id,
            organization_id=membership.organization_id, store_id=store.id,
            user_id=membership.user_id, permit_token=x_privacy_execution_permit)
    except ShopifyPrivacyExecutionError as exc:
        _map_live_error(exc)


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
