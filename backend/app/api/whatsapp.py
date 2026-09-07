"""WhatsApp HTTP router."""

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai_reply_service import generate_auto_reply, _detect_handoff
from ..automations import safe_emit_event
from ..db import get_db
from ..models import (
    Conversation,
    Customer,
    Message,
    OrganizationMembership,
    Store,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
)
from ..permissions import has_permission
from ..whatsapp_client import (
    list_whatsapp_templates,
    send_whatsapp_text_message,
)
from ..whatsapp_compliance import MESSAGE_MODES, TEMPLATE_VARIABLES
from ..whatsapp_security import (
    decrypt_whatsapp_secret,
    encrypt_whatsapp_secret,
)
from .deps import get_current_membership, require_permission

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


def _serialize_whatsapp_template(template):
    return {"id": template.id, "provider_template_name": template.provider_template_name, "language_code": template.language_code, "category": template.category, "status": template.status, "components": template.components, "updated_at": template.updated_at.isoformat() + "Z" if template.updated_at else None}


def _verify_whatsapp_signature(
    raw_body: bytes,
    signature_header: str | None,
) -> bool:
    app_secret = os.getenv(
        "WHATSAPP_APP_SECRET",
    )

    if not app_secret:
        return False

    if not signature_header:
        return False

    expected_prefix = "sha256="

    if not signature_header.startswith(
        expected_prefix
    ):
        return False

    expected_hex = signature_header[
        len(expected_prefix):
    ]

    computed = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(
        computed,
        expected_hex,
    )


# ============================================================
# ROUTES
# ============================================================


@router.get("/api/stores/{store_id}/whatsapp/templates")
def list_store_whatsapp_templates(store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    connection = db.query(WhatsAppConnection).filter(WhatsAppConnection.store_id == store_id, WhatsAppConnection.organization_id == membership.organization_id).first()
    if not connection:
        return {"items": []}
    templates = db.query(WhatsAppMessageTemplate).filter(WhatsAppMessageTemplate.organization_id == membership.organization_id, WhatsAppMessageTemplate.whatsapp_connection_id == connection.id).order_by(WhatsAppMessageTemplate.provider_template_name).all()
    return {"items": [_serialize_whatsapp_template(item) for item in templates]}


@router.post("/api/stores/{store_id}/whatsapp/templates/sync")
def sync_store_whatsapp_templates(store_id: int, membership: OrganizationMembership = Depends(require_permission("stores.write")), db: Session = Depends(get_db)):
    connection = db.query(WhatsAppConnection).filter(WhatsAppConnection.store_id == store_id, WhatsAppConnection.organization_id == membership.organization_id, WhatsAppConnection.status == "connected").first()
    if not connection:
        raise HTTPException(400, "WhatsApp connection is not connected")
    try:
        provider_templates = list_whatsapp_templates(connection.business_account_id, decrypt_whatsapp_secret(connection.access_token_encrypted))
    except Exception as exc:
        raise HTTPException(502, "Unable to sync WhatsApp templates") from exc
    for item in provider_templates:
        name, language = item.get("name"), item.get("language")
        if not name or not language:
            continue
        template = db.query(WhatsAppMessageTemplate).filter(WhatsAppMessageTemplate.whatsapp_connection_id == connection.id, WhatsAppMessageTemplate.provider_template_name == name, WhatsAppMessageTemplate.language_code == language).first()
        values = {"provider_template_id": item.get("id"), "category": item.get("category"), "status": str(item.get("status", "pending")).lower(), "components": {"items": item.get("components") or []}}
        if template:
            for key, value in values.items():
                setattr(template, key, value)
        else:
            db.add(WhatsAppMessageTemplate(organization_id=membership.organization_id, whatsapp_connection_id=connection.id, provider_template_name=name, language_code=language, **values))
    db.commit()
    return list_store_whatsapp_templates(store_id, membership, db)


@router.get(
    "/api/stores/{store_id}/whatsapp"
)
def get_whatsapp_connection(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.read"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id
            == store.id,
            WhatsAppConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not connection:
        return {
            "connected": False,
            "status": "disconnected",
            "phone_number_id": None,
            "business_account_id": None,
            "connected_at": None,
            "last_error": None,
        }

    result = {
        "connected":
            connection.status
            == "connected",
        "status":
            connection.status,
        "phone_number_id":
            connection.phone_number_id,
        "business_account_id":
            connection.business_account_id,
        "verify_token":
            None,
        "connected_at":
            (
                connection.connected_at.isoformat()
                + "Z"
                if connection.connected_at
                else None
            ),
        "last_error":
            connection.last_error,
    }

    if has_permission(
        membership.role,
        "stores.write",
    ):
        result["verify_token"] = (
            connection.verify_token
        )

    return result


@router.post(
    "/api/stores/{store_id}/whatsapp/connect"
)
def connect_whatsapp(
    store_id: int,
    payload: WhatsAppConnectRequest,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.write"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    if not store.active:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "STORE_NOT_ACTIVE",
                "message":
                    (
                        "La tienda debe estar "
                        "activa para conectar "
                        "WhatsApp."
                    ),
            },
        )

    existing = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id
            == store.id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "WHATSAPP_ALREADY_CONNECTED",
                "message":
                    (
                        "Esta tienda ya tiene "
                        "WhatsApp conectado."
                    ),
            },
        )

    phone_id = (
        payload.phone_number_id
        or ""
    ).strip()

    biz_id = (
        payload.business_account_id
        or ""
    ).strip()

    token = (
        payload.access_token
        or ""
    ).strip()

    if not (phone_id and biz_id and token):
        raise HTTPException(
            status_code=400,
            detail={
                "code":
                    "WHATSAPP_FIELDS_REQUIRED",
                "message":
                    (
                        "phone_number_id, "
                        "business_account_id "
                        "y access_token son "
                        "obligatorios."
                    ),
            },
        )

    conflicting = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.phone_number_id
            == phone_id,
        )
        .first()
    )

    if conflicting:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "WHATSAPP_PHONE_IN_USE",
                "message":
                    (
                        "Este número de teléfono "
                        "ya está conectado."
                    ),
            },
        )

    try:
        encrypted_token = (
            encrypt_whatsapp_secret(
                token
            )
        )

    except (
        RuntimeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code":
                    "WHATSAPP_ENCRYPTION_FAILED",
                "message":
                    (
                        "No fue posible cifrar "
                        "el token de WhatsApp."
                    ),
            },
        ) from exc

    now = datetime.utcnow()
    verify_token = secrets.token_urlsafe(48)

    connection = WhatsAppConnection(
        organization_id=
            membership.organization_id,
        store_id=
            store.id,
        phone_number_id=
            phone_id,
        business_account_id=
            biz_id,
        access_token_encrypted=
            encrypted_token,
        verify_token=
            verify_token,
        status=
            "connected",
        connected_at=
            now,
        last_error=
            None,
        created_at=
            now,
        updated_at=
            now,
    )

    db.add(connection)

    try:
        db.commit()
        db.refresh(connection)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "WHATSAPP_SAVE_FAILED",
                "message":
                    (
                        "No fue posible guardar "
                        "la conexión con WhatsApp."
                    ),
            },
        )

    return {
        "ok": True,
        "connected": True,
        "store_id": store.id,
        "status":
            connection.status,
        "phone_number_id":
            connection.phone_number_id,
        "verify_token":
            connection.verify_token,
    }


@router.delete(
    "/api/stores/{store_id}/whatsapp/disconnect"
)
def disconnect_whatsapp(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "stores.write"
        )
    ),
    db: Session = Depends(get_db),
):
    store = (
        db.query(Store)
        .filter(
            Store.id == store_id,
            Store.organization_id
            == membership.organization_id,
            Store.deleted.is_(False),
        )
        .first()
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail="Store not found",
        )

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id
            == store.id,
            WhatsAppConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=404,
            detail={
                "code":
                    "WHATSAPP_NOT_CONNECTED",
                "message":
                    (
                        "Esta tienda no tiene "
                        "WhatsApp conectado."
                    ),
            },
        )

    db.delete(connection)
    db.commit()

    return {
        "ok": True,
        "connected": False,
        "store_id": store.id,
    }


@router.get("/api/webhooks/whatsapp")
def whatsapp_verify_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    mode = request.query_params.get(
        "hub.mode"
    )
    token = request.query_params.get(
        "hub.verify_token"
    )
    challenge = request.query_params.get(
        "hub.challenge"
    )

    if (
        mode != "subscribe"
        or not token
        or not challenge
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid verification request",
        )

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.verify_token
            == token,
            WhatsAppConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=403,
            detail="Invalid verify token",
        )

    return PlainTextResponse(
        content=challenge
    )


@router.post("/api/webhooks/whatsapp")
async def whatsapp_receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    raw_body = await request.body()

    signature = (
        request.headers.get(
            "X-Hub-Signature-256"
        )
    )

    if not _verify_whatsapp_signature(
        raw_body,
        signature,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid signature",
        )

    try:
        payload = json.loads(raw_body)
    except (
        json.JSONDecodeError,
        ValueError,
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON",
        )

    entries = (
        payload.get("entry")
        or []
    )

    inbound_conversation_ids = []
    new_conversations = []  # track (conversation, connection)
    new_messages = []  # track (message, conversation, connection)

    for entry in entries:
        changes = (
            entry.get("changes")
            or []
        )

        for change in changes:
            if (
                change.get("field")
                != "messages"
            ):
                continue

            value = (
                change.get("value")
                or {}
            )

            phone_number_id = (
                value.get(
                    "metadata", {}
                ).get(
                    "phone_number_id"
                )
                or ""
            )

            if not phone_number_id:
                continue

            connection = (
                db.query(
                    WhatsAppConnection,
                )
                .filter(
                    WhatsAppConnection.phone_number_id
                    == phone_number_id,
                    WhatsAppConnection.status
                    == "connected",
                )
                .first()
            )

            if not connection:
                continue

            messages = (
                value.get("messages")
                or []
            )

            statuses = (
                value.get("statuses")
                or []
            )

            contacts = (
                value.get("contacts")
                or []
            )

            contact_map = {
                c.get("wa_id"): c
                for c in contacts
                if c.get("wa_id")
            }

            for msg in messages:
                wa_id = (
                    msg.get("from")
                    or ""
                )

                msg_id = (
                    msg.get("id")
                    or ""
                )

                msg_type = (
                    msg.get("type")
                    or ""
                )

                if (
                    not wa_id
                    or not msg_id
                ):
                    continue

                if (
                    msg_type != "text"
                ):
                    continue

                text_body = (
                    msg.get("text", {})
                    .get("body")
                    or ""
                )

                if not text_body:
                    continue

                customer = (
                    db.query(Customer)
                    .filter(
                        Customer.organization_id
                        == connection.organization_id,
                        Customer.phone
                        == wa_id,
                    )
                    .first()
                )

                if not customer:
                    contact = (
                        contact_map.get(
                            wa_id
                        )
                        or {}
                    )

                    profile = (
                        contact.get(
                            "profile"
                        )
                        or {}
                    )

                    name = (
                        profile.get("name")
                        or wa_id
                    )

                    customer = Customer(
                        organization_id=
                            connection.organization_id,
                        name=
                            name,
                        phone=
                            wa_id,
                    )

                    db.add(customer)
                    db.flush()

                conversation = (
                    db.query(Conversation)
                    .filter(
                        Conversation.organization_id
                        == connection.organization_id,
                        Conversation.store_id
                        == connection.store_id,
                        Conversation.customer_id
                        == customer.id,
                        Conversation.channel
                        == "WhatsApp",
                    )
                    .first()
                )

                if not conversation:
                    conversation = Conversation(
                        organization_id=
                            connection.organization_id,
                        store_id=
                            connection.store_id,
                        customer_id=
                            customer.id,
                        channel=
                            "WhatsApp",
                        preview=
                            text_body,
                        unread=
                            1,
                        mode=
                            "ai",
                        created_at=
                            datetime.utcnow(),
                        updated_at=
                            datetime.utcnow(),
                    )

                    db.add(conversation)
                    db.flush()

                    # Track new conversation for event emission
                    new_conversations.append((conversation, connection))

                existing_msg = (
                    db.query(Message)
                    .filter(
                        Message.conversation_id
                        == conversation.id,
                        Message.provider
                        == "whatsapp",
                        Message.external_message_id
                        == msg_id,
                    )
                    .first()
                )

                if not existing_msg:
                    message = Message(
                        conversation_id=
                            conversation.id,
                        sender=
                            "customer",
                        text=
                            text_body,
                        provider=
                            "whatsapp",
                        external_message_id=
                            msg_id,
                        delivery_status=
                            "delivered",
                        created_at=
                            datetime.utcnow(),
                    )

                    db.add(message)

                    # Track new message for event emission
                    new_messages.append((message, conversation, connection))

                    conversation.preview = (
                        text_body
                    )

                    conversation.unread += 1

                    conversation.updated_at = (
                        datetime.utcnow()
                    )

                    if (
                        conversation.id
                        not in inbound_conversation_ids
                    ):
                        inbound_conversation_ids.append(
                            conversation.id
                        )

            for status_event in statuses:
                ext_msg_id = (
                    status_event.get("id")
                    or ""
                )

                new_status = (
                    status_event.get("status")
                    or ""
                )

                if (
                    not ext_msg_id
                    or not new_status
                ):
                    continue

                valid_statuses = {
                    "sent",
                    "delivered",
                    "read",
                    "failed",
                }

                if (
                    new_status
                    not in valid_statuses
                ):
                    continue

                existing = (
                    db.query(Message)
                    .filter(
                        Message.provider
                        == "whatsapp",
                        Message.external_message_id
                        == ext_msg_id,
                    )
                    .first()
                )

                if existing:
                    existing.delivery_status = (
                        new_status
                    )

                    conversation = (
                        db.query(Conversation)
                        .filter(
                            Conversation.id
                            == existing.conversation_id,
                        )
                        .first()
                    )

                    if conversation:
                        conversation.updated_at = (
                            datetime.utcnow()
                        )

    db.commit()

    # Emit conversation.created events
    for conversation, connection in new_conversations:
        safe_emit_event(
            db=db,
            organization_id=conversation.organization_id,
            store_id=conversation.store_id,
            event_type="conversation.created",
            payload={
                "conversation": {
                    "id": conversation.id,
                    "store_id": conversation.store_id,
                    "organization_id": conversation.organization_id,
                    "channel": conversation.channel,
                    "mode": conversation.mode,
                }
            },
            event_id=f"conversation:{conversation.id}:created",
        )

    # Emit message.received events
    for message, conversation, connection in new_messages:
        safe_emit_event(
            db=db,
            organization_id=conversation.organization_id,
            store_id=conversation.store_id,
            event_type="message.received",
            payload={
                "message": {
                    "id": message.id,
                    "conversation_id": conversation.id,
                    "sender": message.sender,
                    "channel": "whatsapp",
                    "text": message.text,
                },
                "conversation": {
                    "id": conversation.id,
                    "store_id": conversation.store_id,
                    "organization_id": conversation.organization_id,
                },
            },
            event_id=f"whatsapp-message:{message.external_message_id}",
        )

    for cid in inbound_conversation_ids:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == cid)
            .first()
        )

        if not conv:
            continue

        if conv.mode != "ai":
            continue

        last_msg = (
            db.query(Message)
            .filter(
                Message.conversation_id == cid,
            )
            .order_by(Message.id.desc())
            .first()
        )

        if not last_msg:
            continue

        if _detect_handoff(last_msg.text):
            conv.mode = "human"
            conv.updated_at = datetime.utcnow()
            db.commit()
            continue

        background_tasks.add_task(
            generate_auto_reply,
            conversation_id=cid,
        )

    return {"ok": True}


@router.post(
    "/api/conversations/{conversation_id}"
    "/whatsapp/send"
)
def send_whatsapp_message(
    conversation_id: int,
    payload: MessageCreate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "conversations.write"
        )
    ),
    db: Session = Depends(get_db),
):
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id
            == conversation_id,
            Conversation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    connection = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id
            == conversation.store_id,
            WhatsAppConnection.organization_id
            == membership.organization_id,
            WhatsAppConnection.status
            == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=409,
            detail={
                "code":
                    "WHATSAPP_NOT_CONNECTED",
                "message":
                    (
                        "WhatsApp no está "
                        "conectado para esta "
                        "tienda."
                    ),
            },
        )

    customer = (
        db.query(Customer)
        .filter(
            Customer.id
            == conversation.customer_id,
        )
        .first()
    )

    if not customer:
        raise HTTPException(
            status_code=404,
            detail="Customer not found",
        )

    text = (
        payload.text
        or ""
    ).strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Message text is required",
        )

    try:
        token = (
            decrypt_whatsapp_secret(
                connection.access_token_encrypted
            )
        )

        result = (
            send_whatsapp_text_message(
                phone_number_id=
                    connection.phone_number_id,
                access_token=
                    token,
                to=
                    customer.phone,
                text=
                    text,
            )
        )

    except RuntimeError as exc:
        connection.last_error = (
            str(exc)
        )

        db.commit()

        raise HTTPException(
            status_code=502,
            detail={
                "code":
                    "WHATSAPP_SEND_FAILED",
                "message":
                    (
                        "No fue posible enviar "
                        "el mensaje por WhatsApp."
                    ),
            },
        ) from exc

    external_id = (
        result.get("message_id")
    )

    message = Message(
        conversation_id=
            conversation.id,
        sender=
            "human",
        text=
            text,
        provider=
            "whatsapp",
        external_message_id=
            external_id,
        delivery_status=
            "sent",
        created_at=
            datetime.utcnow(),
    )

    db.add(message)

    conversation.preview = text
    conversation.updated_at = (
        datetime.utcnow()
    )

    db.commit()

    return {
        "ok": True,
        "message_id":
            message.id,
    }
