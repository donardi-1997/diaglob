"""Staged Shopify Web Pixel provisioning. No merchant events or Meta CAPI.

Shopify generates the extension UID at CLI scaffolding, NOT Diaglob.
This service creates only an inert settings record in the EXISTING Shopify app.
Public setting sourceId is a routing ID, never a secret or trusted proof of sale.
"""
import json
import os
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import CommerceConnection, MetaPixelConfiguration, Store
from ..shopify_client import ShopifyGraphQLClient
from ..shopify_oauth import normalize_shop_domain
from ..shopify_security import decrypt_shopify_secret


WEB_PIXEL_CREATE = """
mutation DiaglobWebPixelCreate($webPixel: WebPixelInput!) {
  webPixelCreate(webPixel: $webPixel) {
    webPixel { id }
    userErrors { field message }
  }
}
"""
WEB_PIXEL_DELETE = """
mutation DiaglobWebPixelDelete($id: ID!) {
  webPixelDelete(id: $id) {
    deletedWebPixelId
    userErrors { field message }
  }
}
"""
NEEDED_SCOPES = frozenset({"write_pixels", "read_customer_events"})


class PixelProvisioningError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _store_connection(db: Session, store: Store):
    return db.query(CommerceConnection).filter(
        CommerceConnection.store_id == store.id,
        CommerceConnection.organization_id == store.organization_id,
        CommerceConnection.provider == "shopify",
        CommerceConnection.status == "connected",
    ).first()


def _readiness(db: Session, store: Store, config: MetaPixelConfiguration | None):
    blockers = []
    connection = _store_connection(db, store)
    if config is None:
        blockers.append("PIXEL_NOT_CONFIGURED")
    elif config.existing_tracking != "none":
        blockers.append("DUPLICATE_TRACKING_NOT_CLEARED")
    elif config.web_pixel_gid:
        blockers.append("PIXEL_ALREADY_PROVISIONED")
    if not store.active or store.deleted:
        blockers.append("STORE_INACTIVE")
    if connection is None:
        blockers.append("SHOPIFY_NOT_CONNECTED")
    else:
        granted = set((connection.scopes or "").split(","))
        if not NEEDED_SCOPES <= granted:
            blockers.append("SHOPIFY_PIXEL_SCOPES_MISSING")
        try:
            domain = normalize_shop_domain(connection.external_store_url)
            allowlisted = set(s.strip().lower() for s in
                              os.getenv("META_WEB_PIXEL_SHOP_ALLOWLIST", "").split(",") if s.strip())
            if domain not in allowlisted:
                blockers.append("SHOP_NOT_ALLOWLISTED")
        except (ValueError, AttributeError, TypeError):
            blockers.append("INVALID_SHOPIFY_DOMAIN")
    if os.getenv("META_WEB_PIXEL_SHOPIFY_PROVISION_ENABLED", "false").lower() != "true":
        blockers.append("FEATURE_DISABLED")
    if os.getenv("META_WEB_PIXEL_EXTENSION_DEPLOYED", "false").lower() != "true":
        blockers.append("EXTENSION_NOT_RELEASED")
    return {"can_provision": not blockers, "blockers": blockers, "events_active": False}


def readiness(db: Session, store: Store):
    row = db.query(MetaPixelConfiguration).filter(
        MetaPixelConfiguration.organization_id == store.organization_id,
        MetaPixelConfiguration.store_id == store.id,
    ).first()
    return _readiness(db, store, row)


def provision(db: Session, store: Store) -> dict:
    row = db.query(MetaPixelConfiguration).filter(
        MetaPixelConfiguration.organization_id == store.organization_id,
        MetaPixelConfiguration.store_id == store.id,
    ).with_for_update().first()
    state = _readiness(db, store, row)
    if not state["can_provision"]:
        raise PixelProvisioningError(state["blockers"][0])
    conn = _store_connection(db, store)
    # Before provisioning the extension, keep all event transmission OFF.
    source_id = str(uuid4())
    settings = {
        "pixelId": row.pixel_id,
        "collectorUrl": "https://api.diaglob.tech/api/web-pixels/collect",
        "sourceId": source_id,
        "trackingEnabled": "false",
    }
    client = ShopifyGraphQLClient(
        shop_domain=normalize_shop_domain(conn.external_store_url),
        access_token=decrypt_shopify_secret(conn.access_token_encrypted),
    )
    result = client.query(WEB_PIXEL_CREATE, {"webPixel": {"settings": json.dumps(settings)}})
    payload = result.get("webPixelCreate") or {}
    if payload.get("userErrors"):
        # Never leak customer or shop token strings from upstream.
        raise PixelProvisioningError("SHOPIFY_WEB_PIXEL_REJECTED")
    gid = (payload.get("webPixel") or {}).get("id")
    if not isinstance(gid, str) or not gid.startswith("gid://shopify/WebPixel/"):
        raise PixelProvisioningError("SHOPIFY_WEB_PIXEL_RESPONSE_INVALID")
    row.web_pixel_gid = gid
    row.source_id = source_id
    row.status = "provisioned"
    row.enabled = False
    db.commit()
    return {"provisioned": True, "events_active": False, "web_pixel_gid": gid}


def remove_remote(db: Session, store: Store):
    row = db.query(MetaPixelConfiguration).filter(
        MetaPixelConfiguration.organization_id == store.organization_id,
        MetaPixelConfiguration.store_id == store.id,
    ).with_for_update().first()
    if row is None or not row.web_pixel_gid:
        return {"provisioned": False, "events_active": False}
    connection = _store_connection(db, store)
    if connection is None:
        raise PixelProvisioningError("SHOPIFY_NOT_CONNECTED")
    granted = set((connection.scopes or "").split(","))
    if "write_pixels" not in granted:
        raise PixelProvisioningError("SHOPIFY_PIXEL_SCOPES_MISSING")
    # Removal from a merchant shop remains restricted to an explicit allowlist.
    allowlisted = {
        x.strip().lower()
        for x in os.getenv("META_WEB_PIXEL_SHOP_ALLOWLIST", "").split(",") if x.strip()
    }
    shop = normalize_shop_domain(connection.external_store_url)
    if shop not in allowlisted:
        raise PixelProvisioningError("SHOP_NOT_ALLOWLISTED")
    client = ShopifyGraphQLClient(
        shop_domain=shop,
        access_token=decrypt_shopify_secret(connection.access_token_encrypted),
    )
    result = client.query(WEB_PIXEL_DELETE, {"id": row.web_pixel_gid})
    payload = result.get("webPixelDelete") or {}
    if payload.get("userErrors") or payload.get("deletedWebPixelId") != row.web_pixel_gid:
        raise PixelProvisioningError("SHOPIFY_WEB_PIXEL_DELETE_FAILED")
    row.web_pixel_gid = None
    row.source_id = None
    row.status = "awaiting_extension"
    row.enabled = False
    db.commit()
    return {"provisioned": False, "events_active": False}
