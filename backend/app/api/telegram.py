"""Telegram HTTP router."""

import hmac

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..services.telegram_service import (
    TelegramConnectionError,
    TelegramNotConnectedError,
    TelegramNotFoundError,
    TelegramSendError,
    connect as svc_connect,
    disconnect as svc_disconnect,
    get_connection as svc_get_connection,
    send_message as svc_send_message,
)
from ..services.telegram_webhooks import emit_webhook_events, process_webhook_payload
from ..services.whatsapp_webhooks import schedule_ai_replies
from ..telegram_models import TelegramConnection
from ..telegram_security import decrypt_telegram_secret
from .deps import require_permission

router = APIRouter()


class TelegramConnectRequest(BaseModel):
    bot_token: str


class TelegramMessageCreate(BaseModel):
    text: str


def _map_error(exc: Exception) -> None:
    if isinstance(exc, TelegramNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, TelegramNotConnectedError):
        raise HTTPException(
            status_code=409,
            detail={"code": str(exc), "message": "Telegram no está conectado para esta tienda."},
        )
    if isinstance(exc, TelegramSendError):
        code = str(exc)
        status = 502 if code == "TELEGRAM_SEND_FAILED" else 400
        raise HTTPException(status_code=status, detail={"code": code, "message": code})
    if isinstance(exc, TelegramConnectionError):
        code = str(exc)
        messages = {
            "STORE_NOT_ACTIVE": "La tienda debe estar activa para conectar Telegram.",
            "TELEGRAM_ALREADY_CONNECTED": "Esta tienda ya tiene Telegram conectado.",
            "TELEGRAM_TOKEN_REQUIRED": "El Bot Token es obligatorio.",
            "TELEGRAM_TOKEN_INVALID": "Telegram rechazó el Bot Token.",
            "TELEGRAM_BOT_IN_USE": "Este bot ya está conectado a otra tienda.",
            "TELEGRAM_ENCRYPTION_FAILED": "No fue posible cifrar las credenciales de Telegram.",
            "TELEGRAM_WEBHOOK_FAILED": "No fue posible registrar el webhook en Telegram.",
            "TELEGRAM_SAVE_FAILED": "No fue posible guardar la conexión de Telegram.",
            "TELEGRAM_DISCONNECT_FAILED": "No fue posible eliminar el webhook de Telegram.",
        }
        raise HTTPException(
            status_code=409,
            detail={"code": code, "message": messages.get(code, code)},
        )
    raise exc


@router.get("/api/stores/{store_id}/telegram")
def get_telegram_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.read")),
    db: Session = Depends(get_db),
):
    try:
        return svc_get_connection(db, membership.organization_id, store_id)
    except TelegramNotFoundError as exc:
        _map_error(exc)


@router.post("/api/stores/{store_id}/telegram/connect")
def connect_telegram(
    store_id: int,
    payload: TelegramConnectRequest,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_connect(db, membership.organization_id, store_id, payload.bot_token)
    except (TelegramNotFoundError, TelegramConnectionError) as exc:
        _map_error(exc)


@router.delete("/api/stores/{store_id}/telegram/disconnect")
def disconnect_telegram(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_disconnect(db, membership.organization_id, store_id)
    except (TelegramNotConnectedError, TelegramConnectionError) as exc:
        _map_error(exc)


@router.post("/api/conversations/{conversation_id}/telegram/send")
def send_telegram_message(
    conversation_id: int,
    payload: TelegramMessageCreate,
    membership: OrganizationMembership = Depends(require_permission("conversations.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_send_message(
            db,
            membership.organization_id,
            conversation_id,
            payload.text,
        )
    except (
        TelegramNotFoundError,
        TelegramNotConnectedError,
        TelegramSendError,
    ) as exc:
        _map_error(exc)


@router.post("/api/webhooks/telegram/{webhook_path_token}")
async def receive_telegram_webhook(
    webhook_path_token: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    connection = db.query(TelegramConnection).filter(
        TelegramConnection.webhook_path_token == webhook_path_token,
        TelegramConnection.status == "connected",
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Telegram webhook not found")

    supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
    try:
        expected_secret = decrypt_telegram_secret(connection.webhook_secret_encrypted)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Telegram webhook secret unavailable") from exc

    if not supplied_secret or not hmac.compare_digest(supplied_secret, expected_secret):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Telegram update")

    result = process_webhook_payload(db, connection, payload)
    emit_webhook_events(db, result["new_conversations"], result["new_messages"])
    schedule_ai_replies(db, result["inbound_conversation_ids"], background_tasks)
    return {"ok": True}
