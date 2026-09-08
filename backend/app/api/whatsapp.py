"""WhatsApp HTTP router."""

import hashlib
import hmac
import json
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import OrganizationMembership, WhatsAppConnection
from ..permissions import has_permission
from .deps import get_current_membership, require_permission
from ..services.whatsapp_service import (
    WhatsAppConnectionError,
    WhatsAppNotConnectedError,
    WhatsAppNotFoundError,
    WhatsAppSendError,
    connect as svc_connect,
    disconnect as svc_disconnect,
    get_connection as svc_get_connection,
    list_templates as svc_list_templates,
    send_message as svc_send_message,
    sync_templates as svc_sync_templates,
)
from ..services.whatsapp_webhooks import (
    emit_webhook_events,
    process_webhook_payload,
    schedule_ai_replies,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================
# DTO
# ============================================================


class WhatsAppConnectRequest(BaseModel):
    phone_number_id: str
    business_account_id: str
    access_token: str


class MessageCreate(BaseModel):
    text: str
    sender: str = "human"


# ============================================================
# HELPERS
# ============================================================


def _verify_whatsapp_signature(
    raw_body: bytes,
    signature_header: str | None,
) -> bool:
    app_secret = os.getenv("WHATSAPP_APP_SECRET")

    if not app_secret:
        return False

    if not signature_header:
        return False

    expected_prefix = "sha256="

    if not signature_header.startswith(expected_prefix):
        return False

    expected_hex = signature_header[len(expected_prefix):]

    computed = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_hex)


# ============================================================
# ERROR MAPPING
# ============================================================


def _map_whatsapp_error(exc: Exception):
    if isinstance(exc, WhatsAppNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, WhatsAppNotConnectedError):
        raise HTTPException(status_code=409, detail={"code": str(exc), "message": "WhatsApp no está conectado para esta tienda."})
    if isinstance(exc, WhatsAppConnectionError):
        code = str(exc)
        messages = {
            "STORE_NOT_ACTIVE": "La tienda debe estar activa para conectar WhatsApp.",
            "WHATSAPP_ALREADY_CONNECTED": "Esta tienda ya tiene WhatsApp conectado.",
            "WHATSAPP_FIELDS_REQUIRED": "phone_number_id, business_account_id y access_token son obligatorios.",
            "WHATSAPP_PHONE_IN_USE": "Este número de teléfono ya está conectado.",
            "WHATSAPP_ENCRYPTION_FAILED": "No fue posible cifrar el token de WhatsApp.",
            "WHATSAPP_SAVE_FAILED": "No fue posible guardar la conexión con WhatsApp.",
        }
        msg = messages.get(code, str(exc))
        raise HTTPException(status_code=409, detail={"code": code, "message": msg})
    if isinstance(exc, WhatsAppSendError):
        code = str(exc)
        if code == "WHATSAPP_SEND_FAILED":
            raise HTTPException(status_code=502, detail={"code": code, "message": "No fue posible enviar el mensaje por WhatsApp."})
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


# ============================================================
# ROUTES
# ============================================================


@router.get("/api/stores/{store_id}/whatsapp/templates")
def list_store_whatsapp_templates(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    return svc_list_templates(db, membership.organization_id, store_id)


@router.post("/api/stores/{store_id}/whatsapp/templates/sync")
def sync_store_whatsapp_templates(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_sync_templates(db, membership.organization_id, store_id)
    except WhatsAppConnectionError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/stores/{store_id}/whatsapp")
def get_whatsapp_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.read")),
    db: Session = Depends(get_db),
):
    try:
        result = svc_get_connection(db, membership.organization_id, store_id)
    except WhatsAppNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Only expose verify_token to users with stores.write permission
    if not has_permission(membership.role, "stores.write"):
        result["verify_token"] = None

    return result


@router.post("/api/stores/{store_id}/whatsapp/connect")
def connect_whatsapp(
    store_id: int,
    payload: WhatsAppConnectRequest,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_connect(
            db,
            membership.organization_id,
            store_id,
            payload.phone_number_id,
            payload.business_account_id,
            payload.access_token,
        )
    except (WhatsAppNotFoundError, WhatsAppConnectionError) as exc:
        _map_whatsapp_error(exc)


@router.delete("/api/stores/{store_id}/whatsapp/disconnect")
def disconnect_whatsapp(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("stores.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_disconnect(db, membership.organization_id, store_id)
    except (WhatsAppNotFoundError, WhatsAppNotConnectedError) as exc:
        _map_whatsapp_error(exc)


@router.get("/api/webhooks/whatsapp")
def whatsapp_verify_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode != "subscribe" or not token or not challenge:
        raise HTTPException(status_code=400, detail="Invalid verification request")

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.verify_token == token,
            WhatsAppConnection.status == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(status_code=403, detail="Invalid verify token")

    return PlainTextResponse(content=challenge)


@router.post("/api/webhooks/whatsapp")
async def whatsapp_receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # CRITICAL: raw body → signature → JSON order preserved
    raw_body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256")

    if not _verify_whatsapp_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    result = process_webhook_payload(db, payload)

    emit_webhook_events(
        db,
        result["new_conversations"],
        result["new_messages"],
    )

    schedule_ai_replies(
        db,
        result["inbound_conversation_ids"],
        background_tasks,
    )

    return {"ok": True}


@router.post("/api/conversations/{conversation_id}/whatsapp/send")
def send_whatsapp_message(
    conversation_id: int,
    payload: MessageCreate,
    membership: OrganizationMembership = Depends(require_permission("conversations.write")),
    db: Session = Depends(get_db),
):
    try:
        return svc_send_message(db, membership.organization_id, conversation_id, payload.text)
    except (WhatsAppNotFoundError, WhatsAppNotConnectedError, WhatsAppSendError) as exc:
        _map_whatsapp_error(exc)
