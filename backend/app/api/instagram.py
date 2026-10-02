"""Instagram Messaging HTTP router."""

import hashlib
import hmac
import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership
from ..permissions import has_permission
from ..services.instagram_service import (
    InstagramConnectionError,
    InstagramNotConnectedError,
    InstagramNotFoundError,
    InstagramSendError,
    connect as svc_connect,
    disconnect as svc_disconnect,
    get_connection as svc_get_connection,
    send_message as svc_send_message,
    webhook_verify_token,
)
from ..services.instagram_webhooks import emit_webhook_events, process_webhook_payload
from ..services.whatsapp_webhooks import schedule_ai_replies
from .deps import require_permission

router = APIRouter()


class InstagramConnectRequest(BaseModel):
    instagram_account_id: str
    page_id: str | None = None
    access_token: str


class InstagramMessageCreate(BaseModel):
    text: str


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    app_secret = (
        os.getenv("INSTAGRAM_APP_SECRET")
        or os.getenv("META_APP_SECRET")
        or ""
    ).strip()
    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header[7:])


def _map_error(exc: Exception) -> None:
    if isinstance(exc, InstagramNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, InstagramNotConnectedError):
        raise HTTPException(
            status_code=409,
            detail={"code": str(exc), "message": "Instagram no está conectado para esta tienda."},
        )
    if isinstance(exc, InstagramSendError):
        code = str(exc)
        status = 502 if code == "INSTAGRAM_SEND_FAILED" else 400
        raise HTTPException(status_code=status, detail={"code": code, "message": code})
    if isinstance(exc, InstagramConnectionError):
        code = str(exc)
        messages = {
            "STORE_NOT_ACTIVE": "La tienda debe estar activa para conectar Instagram.",
            "INSTAGRAM_ALREADY_CONNECTED": "Esta tienda ya tiene Instagram conectado.",
            "INSTAGRAM_FIELDS_REQUIRED": "Instagram Account ID y Access Token son obligatorios.",
            "INSTAGRAM_ACCOUNT_IN_USE": "Esta cuenta de Instagram ya está conectada a otra tienda.",
            "INSTAGRAM_TOKEN_INVALID": "Meta rechazó la cuenta o el Access Token.",
            "INSTAGRAM_ENCRYPTION_FAILED": "No fue posible cifrar el token de Instagram.",
            "INSTAGRAM_SAVE_FAILED": "No fue posible guardar la conexión de Instagram.",
        }
        raise HTTPException(
            status_code=409,
            detail={"code": code, "message": messages.get(code, code)},
        )
    raise exc


@router.get("/api/stores/{store_id}/instagram")
def get_instagram_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.read")),
    db: Session = Depends(get_db),
):
    try:
        result = svc_get_connection(db, membership.organization_id, store_id)
    except InstagramNotFoundError as exc:
        _map_error(exc)
    result["verify_token"] = (
        webhook_verify_token()
        if has_permission(membership.role, "stores.write")
        else None
    )
    return result


@router.post("/api/stores/{store_id}/instagram/connect")
def connect_instagram(
    store_id: int,
    payload: InstagramConnectRequest,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        result = svc_connect(
            db,
            membership.organization_id,
            store_id,
            payload.instagram_account_id,
            payload.page_id,
            payload.access_token,
        )
    except (InstagramNotFoundError, InstagramConnectionError) as exc:
        _map_error(exc)
    result["verify_token"] = webhook_verify_token()
    return result


@router.delete("/api/stores/{store_id}/instagram/disconnect")
def disconnect_instagram(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_disconnect(db, membership.organization_id, store_id)
    except InstagramNotConnectedError as exc:
        _map_error(exc)


@router.get("/api/webhooks/instagram")
def verify_instagram_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    expected = webhook_verify_token()
    if (
        mode != "subscribe"
        or not expected
        or not token
        or not challenge
        or not hmac.compare_digest(token, expected)
    ):
        raise HTTPException(status_code=403, detail="Invalid verification request")
    return PlainTextResponse(content=challenge)


@router.post("/api/webhooks/instagram")
async def receive_instagram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    if not _verify_signature(
        raw_body,
        request.headers.get("X-Hub-Signature-256"),
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid Instagram webhook")

    result = process_webhook_payload(db, payload)
    emit_webhook_events(db, result["new_conversations"], result["new_messages"])
    schedule_ai_replies(db, result["inbound_conversation_ids"], background_tasks)
    return {"ok": True}


@router.post("/api/conversations/{conversation_id}/instagram/send")
def send_instagram_message(
    conversation_id: int,
    payload: InstagramMessageCreate,
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
        InstagramNotFoundError,
        InstagramNotConnectedError,
        InstagramSendError,
    ) as exc:
        _map_error(exc)
