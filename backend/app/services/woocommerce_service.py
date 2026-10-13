"""WooCommerce connection lifecycle for a Dropi-through-Dropify storefront.

Credentials are WooCommerce REST consumer key/secret, NOT the Dropi plugin
token. No Dropi order is created and the bridge never writes to WooCommerce.
"""
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..dropi_security import decrypt_dropi_secret, encrypt_dropi_secret
from ..integrations.woocommerce_bridge import (
    WooCommerceError,
    list_woocommerce,
    normalize_woocommerce_url,
    preview_woocommerce_orders,
    preview_woocommerce_products,
)
from ..models import CommerceConnection, Store
from .trial_service import TrialIdentityAlreadyUsed, activate_trial_for_verified_store


class WooConnectionError(Exception):
    pass


def _store(db: Session, organization_id: int, store_id: int) -> Store:
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
        raise WooConnectionError("WOO_STORE_NOT_FOUND")
    return store


def _connection(db: Session, organization_id: int, store_id: int) -> CommerceConnection:
    _store(db, organization_id, store_id)
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == store_id,
            CommerceConnection.provider == "woocommerce",
        )
        .first()
    )
    if not connection:
        raise WooConnectionError("WOO_NOT_CONNECTED")
    return connection


def status(db: Session, organization_id: int, store_id: int) -> dict:
    _store(db, organization_id, store_id)
    connection = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.organization_id == organization_id,
            CommerceConnection.store_id == store_id,
            CommerceConnection.provider == "woocommerce",
        )
        .first()
    )
    return {
        "provider": "woocommerce",
        "connected": bool(connection and connection.status == "connected"),
        "status": connection.status if connection else "disconnected",
        "external_store_url": connection.external_store_url if connection else None,
        "last_checked_at": connection.last_sync_at.isoformat() + "Z"
        if connection and connection.last_sync_at else None,
        "last_error": connection.last_error if connection else None,
        "dropi_bridge_status": "unverified",
        "next_step": "Instala Dropify en WooCommerce, agrega allí el token de Dropi y valida un pedido de prueba.",
    }


def connect(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    site_url: str,
    consumer_key: str,
    consumer_secret: str,
) -> dict:
    store = _store(db, organization_id, store_id)
    if not store.active:
        raise WooConnectionError("WOO_STORE_INACTIVE")
    normalized = normalize_woocommerce_url(site_url)
    consumer_key, consumer_secret = consumer_key.strip(), consumer_secret.strip()
    if not consumer_key or not consumer_secret:
        raise WooConnectionError("WOO_CREDENTIALS_REQUIRED")
    existing = db.query(CommerceConnection).filter(CommerceConnection.store_id == store_id).first()
    if existing and (existing.organization_id != organization_id or existing.provider != "woocommerce"):
        raise WooConnectionError("COMMERCE_ALREADY_CONNECTED")
    conflict = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.provider == "woocommerce",
            CommerceConnection.external_store_url == normalized,
        )
        .first()
    )
    if conflict and (not existing or conflict.id != existing.id):
        raise WooConnectionError("WOO_SITE_ALREADY_CONNECTED")

    # Verify against the documented API before persisting or claiming a trial.
    # No raw provider response, PII or supplied secret is persisted.
    list_woocommerce(normalized, consumer_key, consumer_secret, "products", limit=1)
    try:
        key_encrypted = encrypt_dropi_secret(consumer_key)
        secret_encrypted = encrypt_dropi_secret(consumer_secret)
    except (ValueError, RuntimeError) as exc:
        raise WooConnectionError("WOO_ENCRYPTION_NOT_CONFIGURED") from exc

    now = datetime.utcnow()
    if existing:
        connection = existing
    else:
        connection = CommerceConnection(
            organization_id=organization_id,
            store_id=store_id,
            provider="woocommerce",
            external_store_url=normalized,
        )
        db.add(connection)
    connection.external_store_url = normalized
    connection.api_key_encrypted = key_encrypted
    connection.api_secret_encrypted = secret_encrypted
    connection.status = "connected"
    connection.scopes = "read_only_sync"
    connection.last_sync_at = now
    connection.connected_at = now
    connection.updated_at = now
    connection.last_error = None

    try:
        activate_trial_for_verified_store(
            db,
            organization_id=organization_id,
            store_id=store_id,
            provider="woocommerce",
            external_identity=normalized,
        )
        db.commit()
    except TrialIdentityAlreadyUsed as exc:
        db.rollback()
        raise WooConnectionError("WOO_TRIAL_IDENTITY_ALREADY_USED") from exc
    except IntegrityError as exc:
        db.rollback()
        raise WooConnectionError("WOO_CONNECTION_CONFLICT") from exc
    db.refresh(connection)
    return status(db, organization_id, store_id)


def _credentials(connection: CommerceConnection) -> tuple[str, str]:
    if connection.status != "connected":
        raise WooConnectionError("WOO_NOT_CONNECTED")
    if not connection.api_key_encrypted or not connection.api_secret_encrypted:
        raise WooConnectionError("WOO_CREDENTIALS_MISSING")
    try:
        return (
            decrypt_dropi_secret(connection.api_key_encrypted),
            decrypt_dropi_secret(connection.api_secret_encrypted),
        )
    except (RuntimeError, ValueError) as exc:
        raise WooConnectionError("WOO_CREDENTIALS_UNAVAILABLE") from exc


def test(db: Session, organization_id: int, store_id: int) -> dict:
    connection = _connection(db, organization_id, store_id)
    key, secret = _credentials(connection)
    try:
        list_woocommerce(connection.external_store_url, key, secret, "products", limit=1)
    except WooCommerceError as exc:
        connection.last_error = str(exc)  # sanitized codes only
        connection.updated_at = datetime.utcnow()
        db.commit()
        raise
    connection.last_error = None
    connection.last_sync_at = datetime.utcnow()
    db.commit()
    return status(db, organization_id, store_id)


def preview(db: Session, organization_id: int, store_id: int, resource: str, limit: int) -> dict:
    connection = _connection(db, organization_id, store_id)
    key, secret = _credentials(connection)
    rows = list_woocommerce(connection.external_store_url, key, secret, resource, limit=limit)
    sanitized = (
        preview_woocommerce_products(rows)
        if resource == "products" else preview_woocommerce_orders(rows)
    )
    return {"provider": "woocommerce", "resource": resource, "items": sanitized, "total_returned": len(sanitized)}


def disconnect(db: Session, organization_id: int, store_id: int) -> dict:
    connection = _connection(db, organization_id, store_id)
    connection.api_key_encrypted = None
    connection.api_secret_encrypted = None
    connection.status = "disconnected"
    connection.last_error = None
    connection.updated_at = datetime.utcnow()
    db.commit()
    return status(db, organization_id, store_id)
