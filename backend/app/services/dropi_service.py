"""Dropi connection business orchestration service.

Handles connection lifecycle, token encryption, and webhook token generation.
Does NOT import FastAPI.
"""
import logging
import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from ..dropi_security import encrypt_dropi_secret
from ..models import DropiConnection, Store

logger = logging.getLogger(__name__)


class DropiNotFoundError(Exception):
    pass


class DropiConnectionError(Exception):
    pass


def _require_store(db: Session, organization_id: int, store_id: int) -> Store:
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id == organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )
    if not store:
        raise DropiNotFoundError("Store not found")
    return store


def get_connection(db: Session, organization_id: int, store_id: int) -> dict:
    store = _require_store(db, organization_id, store_id)

    connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.store_id == store.id,
            DropiConnection.organization_id == organization_id,
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "external_store_id": None,
            "api_url": None,
            "webhook_url": None,
            "connected_at": None,
            "last_sync_at": None,
            "last_error": None,
        }

    return {
        "connected": connection.status == "connected",
        "status": connection.status,
        "external_store_id": connection.external_store_id,
        "api_url": connection.api_url,
        "webhook_url": (
            "https://api.diaglob.tech"
            "/api/webhooks/dropi/"
            f"{connection.webhook_token}"
        ),
        "connected_at": (
            connection.connected_at.isoformat() + "Z"
            if connection.connected_at
            else None
        ),
        "last_sync_at": (
            connection.last_sync_at.isoformat() + "Z"
            if connection.last_sync_at
            else None
        ),
        "last_error": connection.last_error,
    }


def connect(db: Session, organization_id: int, store_id: int, api_token: str) -> dict:
    store = _require_store(db, organization_id, store_id)

    if not store.active:
        raise DropiConnectionError("STORE_NOT_ACTIVE")

    existing_connection = (
        db.query(DropiConnection)
        .filter(DropiConnection.store_id == store.id)
        .first()
    )
    if existing_connection:
        raise DropiConnectionError("DROPPI_ALREADY_CONNECTED")

    api_token = (api_token or "").strip()
    if not api_token:
        raise DropiConnectionError("DROPPI_TOKEN_REQUIRED")

    try:
        encrypted_token = encrypt_dropi_secret(api_token)
    except (RuntimeError, ValueError) as exc:
        raise DropiConnectionError("DROPPI_ENCRYPTION_NOT_CONFIGURED") from exc

    now = datetime.utcnow()

    connection = DropiConnection(
        organization_id=organization_id,
        store_id=store.id,
        api_token_encrypted=encrypted_token,
        webhook_token=secrets.token_urlsafe(32),
        status="connected",
        connected_at=now,
        last_sync_at=None,
        last_error=None,
        created_at=now,
        updated_at=now,
    )

    db.add(connection)

    try:
        db.commit()
        db.refresh(connection)
    except Exception:
        db.rollback()
        raise DropiConnectionError("DROPPI_CONNECTION_SAVE_FAILED")

    return {
        "ok": True,
        "connected": True,
        "store_id": store.id,
        "status": connection.status,
        "webhook_url": (
            "https://api.diaglob.tech"
            "/api/webhooks/dropi/"
            f"{connection.webhook_token}"
        ),
    }


def disconnect(db: Session, organization_id: int, store_id: int) -> dict:
    store = _require_store(db, organization_id, store_id)

    connection = (
        db.query(DropiConnection)
        .filter(
            DropiConnection.store_id == store.id,
            DropiConnection.organization_id == organization_id,
        )
        .first()
    )
    if not connection:
        raise DropiNotFoundError("DROPPI_NOT_CONNECTED")

    db.delete(connection)
    db.commit()

    return {"ok": True, "connected": False, "store_id": store.id}
