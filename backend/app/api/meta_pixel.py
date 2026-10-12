"""Tenant-scoped Meta Pixel settings. Tracking is NOT activated in this phase.

A store Pixel ID is different from a connected Meta Ads account and from the
Diaglob acquisition Pixel. Never send browser events or Meta credentials here.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import MetaPixelConfiguration, OrganizationMembership, Store
from ..shopify_client import ShopifyAPIError
from ..services import meta_pixel_provisioning
from .deps import require_permission
from .store_access import require_authorized_path_store


router = APIRouter()
ExistingTracking = Literal["unknown", "none", "shopify_meta", "manual_pixel"]


class MetaPixelSettings(BaseModel):
    pixel_id: str = Field(min_length=8, max_length=30, pattern=r"^[0-9]{8,30}$")
    existing_tracking: ExistingTracking = "unknown"


def _format_settings(row: MetaPixelConfiguration | None, store_id: int) -> dict:
    if row is None:
        return {
            "store_id": store_id,
            "configured": False,
            "pixel_id": None,
            "existing_tracking": "unknown",
            "enabled": False,
            "status": "not_configured",
            "extension_installed": False,
            "duplicate_tracking_risk": "unknown",
        }
    return {
        "store_id": store_id,
        "configured": True,
        "pixel_id": row.pixel_id,
        "existing_tracking": row.existing_tracking,
        # Shopify may be provisioned while browser/server event collection stays OFF.
        "enabled": False,
        "status": "provisioned" if row.web_pixel_gid else "awaiting_extension",
        "extension_installed": bool(row.web_pixel_gid),
        "duplicate_tracking_risk": (
            "high" if row.existing_tracking in {"shopify_meta", "manual_pixel"}
            else "unknown" if row.existing_tracking == "unknown" else "none_reported"
        ),
    }


def _load_config(db: Session, store: Store):
    return db.query(MetaPixelConfiguration).filter(
        MetaPixelConfiguration.organization_id == store.organization_id,
        MetaPixelConfiguration.store_id == store.id,
    ).first()


@router.get("/api/stores/{store_id}/meta-pixel")
def get_meta_pixel(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.read")),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
):
    return _format_settings(_load_config(db, store), store.id)


@router.put("/api/stores/{store_id}/meta-pixel")
def set_meta_pixel(
    store_id: int,
    payload: MetaPixelSettings,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
):
    if not store.active:
        raise HTTPException(status_code=409, detail="STORE_INACTIVE")
    row = _load_config(db, store)
    if row is None:
        row = MetaPixelConfiguration(
            organization_id=store.organization_id,
            store_id=store.id,
            pixel_id=payload.pixel_id,
            existing_tracking=payload.existing_tracking,
            enabled=False,
            status="awaiting_extension",
        )
        db.add(row)
    else:
        if row.web_pixel_gid:
            raise HTTPException(status_code=409, detail="REMOVE_PROVISIONED_PIXEL_FIRST")
        row.pixel_id = payload.pixel_id
        row.existing_tracking = payload.existing_tracking
        row.enabled = False
        row.status = "awaiting_extension"
    db.commit()
    return _format_settings(row, store.id)


@router.delete("/api/stores/{store_id}/meta-pixel")
def delete_meta_pixel(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
):
    row = _load_config(db, store)
    if row is not None:
        if row.web_pixel_gid:
            raise HTTPException(status_code=409, detail="REMOVE_PROVISIONED_PIXEL_FIRST")
        db.delete(row)
        db.commit()
    return _format_settings(None, store.id)



@router.get("/api/stores/{store_id}/meta-pixel/readiness")
def meta_pixel_readiness(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.read")),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
):
    """No Shopify request; indicates why provisioning is blocked."""
    return meta_pixel_provisioning.readiness(db, store)


@router.post("/api/stores/{store_id}/meta-pixel/provision")
def provision_meta_pixel(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
):
    """Create INACTIVE app-pixel settings; never send merchant events."""
    try:
        return meta_pixel_provisioning.provision(db, store)
    except meta_pixel_provisioning.PixelProvisioningError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    except ShopifyAPIError as exc:
        raise HTTPException(status_code=503, detail="SHOPIFY_WEB_PIXEL_PROVIDER_UNAVAILABLE") from exc


@router.post("/api/stores/{store_id}/meta-pixel/unprovision")
def unprovision_meta_pixel(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    store: Store = Depends(require_authorized_path_store),
    db: Session = Depends(get_db),
):
    try:
        return meta_pixel_provisioning.remove_remote(db, store)
    except meta_pixel_provisioning.PixelProvisioningError as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
