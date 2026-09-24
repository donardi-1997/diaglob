"""Supplier connection lifecycle and CJ credential management."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..integrations.cj import client as cj_client
from ..integrations.cj.client import CJAuthError
from ..model_domains.supplier_integrations import SupplierConnection
from ..models import Store
from ..supplier_security import decrypt_supplier_secret, encrypt_supplier_secret

CJ_PROVIDER = "cj"
_TOKEN_REFRESH_MARGIN = timedelta(days=1)


class SupplierConnectionNotFound(Exception):
    pass


class SupplierConnectionError(Exception):
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
        raise SupplierConnectionNotFound("STORE_NOT_FOUND")
    return store


def _get_connection(
    db: Session,
    organization_id: int,
    store_id: int,
    provider: str = CJ_PROVIDER,
) -> SupplierConnection | None:
    return (
        db.query(SupplierConnection)
        .filter(
            SupplierConnection.organization_id == organization_id,
            SupplierConnection.store_id == store_id,
            SupplierConnection.provider == provider,
        )
        .first()
    )


def _encrypt(value: str) -> str:
    try:
        return encrypt_supplier_secret(value)
    except (RuntimeError, ValueError) as exc:
        raise SupplierConnectionError("SUPPLIER_ENCRYPTION_NOT_CONFIGURED") from exc


def _decrypt(value: str) -> str:
    try:
        return decrypt_supplier_secret(value)
    except (RuntimeError, ValueError) as exc:
        raise SupplierConnectionError("SUPPLIER_CREDENTIAL_DECRYPT_FAILED") from exc


def _apply_token_payload(
    connection: SupplierConnection,
    payload: dict,
) -> None:
    connection.access_token_encrypted = _encrypt(payload["accessToken"])
    connection.refresh_token_encrypted = _encrypt(payload["refreshToken"])
    connection.access_token_expires_at = cj_client.parse_cj_datetime(
        payload.get("accessTokenExpiryDate")
    )
    connection.refresh_token_expires_at = cj_client.parse_cj_datetime(
        payload.get("refreshTokenExpiryDate")
    )


def get_cj_status(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    _require_store(db, organization_id, store_id)
    connection = _get_connection(db, organization_id, store_id)

    if not connection:
        return {
            "provider": CJ_PROVIDER,
            "connected": False,
            "status": "disconnected",
            "external_account_id": None,
            "external_account_name": None,
            "access_token_expires_at": None,
            "refresh_token_expires_at": None,
            "connected_at": None,
            "last_sync_at": None,
            "last_error": None,
        }

    return {
        "provider": connection.provider,
        "connected": connection.status == "connected",
        "status": connection.status,
        "external_account_id": connection.external_account_id,
        "external_account_name": connection.external_account_name,
        "access_token_expires_at": (
            connection.access_token_expires_at.isoformat() + "Z"
            if connection.access_token_expires_at
            else None
        ),
        "refresh_token_expires_at": (
            connection.refresh_token_expires_at.isoformat() + "Z"
            if connection.refresh_token_expires_at
            else None
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


def connect_cj(
    db: Session,
    organization_id: int,
    store_id: int,
    api_key: str,
) -> dict:
    store = _require_store(db, organization_id, store_id)
    if not store.active:
        raise SupplierConnectionError("STORE_NOT_ACTIVE")

    api_key = (api_key or "").strip()
    if not api_key:
        raise SupplierConnectionError("CJ_API_KEY_REQUIRED")

    # Validate the credential with CJ before mutating local persistence.
    token_payload = cj_client.get_access_token(api_key)
    settings = cj_client.get_settings(token_payload["accessToken"])

    now = datetime.utcnow()
    connection = _get_connection(db, organization_id, store_id)
    if connection is None:
        connection = SupplierConnection(
            organization_id=organization_id,
            store_id=store_id,
            provider=CJ_PROVIDER,
            connected_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(connection)

    connection.external_account_id = str(
        settings.get("openId") or token_payload.get("openId") or ""
    ) or None
    connection.external_account_name = settings.get("openName")
    connection.api_key_encrypted = _encrypt(api_key)
    _apply_token_payload(connection, token_payload)
    connection.status = "connected"
    connection.last_error = None
    connection.updated_at = now

    try:
        db.commit()
        db.refresh(connection)
    except Exception as exc:
        db.rollback()
        raise SupplierConnectionError("SUPPLIER_CONNECTION_SAVE_FAILED") from exc

    return {
        "ok": True,
        "provider": CJ_PROVIDER,
        "connected": True,
        "store_id": store_id,
        "external_account_id": connection.external_account_id,
        "external_account_name": connection.external_account_name,
        "access_token_expires_at": (
            connection.access_token_expires_at.isoformat() + "Z"
            if connection.access_token_expires_at
            else None
        ),
    }


def disconnect_cj(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    _require_store(db, organization_id, store_id)
    connection = _get_connection(db, organization_id, store_id)
    if not connection:
        raise SupplierConnectionNotFound("CJ_NOT_CONNECTED")

    db.delete(connection)
    db.commit()
    return {"ok": True, "provider": CJ_PROVIDER, "connected": False, "store_id": store_id}


def get_valid_cj_access_token(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    now: datetime | None = None,
) -> str:
    _require_store(db, organization_id, store_id)
    connection = (
        db.query(SupplierConnection)
        .filter(
            SupplierConnection.organization_id == organization_id,
            SupplierConnection.store_id == store_id,
            SupplierConnection.provider == CJ_PROVIDER,
        )
        .with_for_update()
        .first()
    )
    if not connection:
        raise SupplierConnectionNotFound("CJ_NOT_CONNECTED")

    current = now or datetime.utcnow()
    access_token = _decrypt(connection.access_token_encrypted or "")

    if (
        connection.access_token_expires_at is None
        or connection.access_token_expires_at > current + _TOKEN_REFRESH_MARGIN
    ):
        return access_token

    token_payload = None
    refresh_usable = (
        bool(connection.refresh_token_encrypted)
        and (
            connection.refresh_token_expires_at is None
            or connection.refresh_token_expires_at > current
        )
    )

    if refresh_usable:
        try:
            refresh_token = _decrypt(connection.refresh_token_encrypted or "")
            token_payload = cj_client.refresh_access_token(refresh_token)
        except CJAuthError:
            token_payload = None

    if token_payload is None:
        api_key = _decrypt(connection.api_key_encrypted or "")
        token_payload = cj_client.get_access_token(api_key)

    _apply_token_payload(connection, token_payload)
    connection.status = "connected"
    connection.last_error = None
    connection.updated_at = current
    db.commit()

    return token_payload["accessToken"]


def test_cj_connection(
    db: Session,
    organization_id: int,
    store_id: int,
) -> dict:
    token = get_valid_cj_access_token(
        db,
        organization_id,
        store_id,
    )
    settings = cj_client.get_settings(token)

    connection = _get_connection(db, organization_id, store_id)
    if connection is None:
        raise SupplierConnectionNotFound("CJ_NOT_CONNECTED")

    connection.external_account_id = str(settings.get("openId") or "") or None
    connection.external_account_name = settings.get("openName")
    connection.status = "connected"
    connection.last_error = None
    connection.updated_at = datetime.utcnow()
    db.commit()

    setting = settings.get("setting") or {}
    return {
        "ok": True,
        "connected": True,
        "provider": CJ_PROVIDER,
        "external_account_id": connection.external_account_id,
        "external_account_name": connection.external_account_name,
        "account_email": settings.get("openEmail"),
        "root": settings.get("root"),
        "is_sandbox": bool(settings.get("isSandbox")),
        "qps_limit": setting.get("qpsLimit"),
    }
