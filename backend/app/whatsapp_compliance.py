"""Conservative WhatsApp service-window and template eligibility checks."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Conversation, Message, WhatsAppConnection, WhatsAppMessageTemplate

SERVICE_WINDOW = timedelta(hours=24)
TEMPLATE_STATUSES = {"approved", "pending", "rejected", "disabled"}
MESSAGE_MODES = {"free_form", "template", "auto"}
TEMPLATE_VARIABLES = {"customer.name", "store.name", "customer.segment", "customer.health"}
# Event-driven flows carry order/shipment context, so their approved Meta
# templates may reference it. Contact details and street addresses are not
# exposed as template parameters.
FLOW_TEMPLATE_VARIABLES = frozenset(TEMPLATE_VARIABLES | {
    "order.number",
    "order.total",
    "order.currency",
    "order.items_summary",
    "order.payment_method",
    "order.payment_status",
    "order.fulfillment_status",
    "order.shipping.city",
    "shipment.carrier",
    "shipment.tracking_number",
    "shipment.last_mile_tracking_number",
    "shipment.status",
    "shipment.delivery_days",
    "shipment.tracking_url",
})
_BODY_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")


def get_whatsapp_service_window_status(db: Session, organization_id: int, store_id: int, customer_id: int, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    last_inbound = db.query(func.max(Message.created_at)).join(Conversation).filter(
        Conversation.organization_id == organization_id, Conversation.store_id == store_id,
        Conversation.customer_id == customer_id, Conversation.channel == "WhatsApp",
        Message.provider == "whatsapp", Message.sender == "customer",
    ).scalar()
    if not last_inbound:
        return {"inside_window": False, "last_inbound_at": None, "window_expires_at": None, "reason": "no_inbound_history"}
    expires = last_inbound + SERVICE_WINDOW
    return {"inside_window": now < expires, "last_inbound_at": last_inbound, "window_expires_at": expires, "reason": "inside_service_window" if now < expires else "outside_service_window"}


def get_last_whatsapp_inbound_by_customer(db: Session, organization_id: int, store_id: int, customer_ids: list[int]) -> dict[int, datetime]:
    """One grouped history query for a worker batch in a single store scope."""
    if not customer_ids:
        return {}
    rows = db.query(Conversation.customer_id, func.max(Message.created_at)).join(Message).filter(
        Conversation.organization_id == organization_id, Conversation.store_id == store_id,
        Conversation.customer_id.in_(customer_ids), Conversation.channel == "WhatsApp",
        Message.provider == "whatsapp", Message.sender == "customer",
    ).group_by(Conversation.customer_id).all()
    return {customer_id: timestamp for customer_id, timestamp in rows if timestamp}


def get_template(db: Session, campaign, connection: WhatsAppConnection):
    if not campaign.whatsapp_template_id:
        return None
    return db.query(WhatsAppMessageTemplate).filter(
        WhatsAppMessageTemplate.id == campaign.whatsapp_template_id,
        WhatsAppMessageTemplate.organization_id == campaign.organization_id,
        WhatsAppMessageTemplate.whatsapp_connection_id == connection.id,
    ).first()


def evaluate_whatsapp_delivery_eligibility(db: Session, campaign, connection: WhatsAppConnection, customer_id: int, now: datetime | None = None, last_inbound_at: datetime | None = None, inbound_known: bool = False) -> dict:
    if inbound_known:
        now = now or datetime.utcnow()
        expires = last_inbound_at + SERVICE_WINDOW if last_inbound_at else None
        window = {"inside_window": bool(expires and now < expires), "last_inbound_at": last_inbound_at, "window_expires_at": expires, "reason": "inside_service_window" if expires and now < expires else ("outside_service_window" if expires else "no_inbound_history")}
    else:
        window = get_whatsapp_service_window_status(db, campaign.organization_id, campaign.store_id, customer_id, now)
    template = get_template(db, campaign, connection)
    if campaign.message_mode == "free_form":
        return window | {"allowed": window["inside_window"], "mode": "free_form", "template": None, "reason": "inside_service_window" if window["inside_window"] else "outside_service_window"}
    if campaign.message_mode == "template":
        if not template:
            return window | {"allowed": False, "mode": "template", "template": None, "reason": "template_missing"}
        if template.status != "approved":
            return window | {"allowed": False, "mode": "template", "template": template, "reason": "template_not_approved"}
        return window | {"allowed": True, "mode": "template", "template": template, "reason": "template_approved"}
    if window["inside_window"]:
        return window | {"allowed": True, "mode": "free_form", "template": None, "reason": "inside_service_window"}
    if not template:
        return window | {"allowed": False, "mode": "template", "template": None, "reason": "template_required"}
    if template.status != "approved":
        return window | {"allowed": False, "mode": "template", "template": template, "reason": "template_not_approved"}
    return window | {"allowed": True, "mode": "template", "template": template, "reason": "template_approved"}


def template_body_parameter_count(template: WhatsAppMessageTemplate) -> int | None:
    """Number of distinct {{n}} placeholders in the synced Meta BODY, if known."""
    items = (template.components or {}).get("items") if isinstance(template.components, dict) else None
    if not isinstance(items, list):
        return None
    for component in items:
        if isinstance(component, dict) and str(component.get("type", "")).upper() == "BODY":
            return len(set(_BODY_PLACEHOLDER_RE.findall(str(component.get("text") or ""))))
    return None


def template_components(
    template: WhatsAppMessageTemplate,
    variables: dict,
    data: dict,
    allowed: frozenset[str] | set[str] = TEMPLATE_VARIABLES,
) -> list[dict]:
    mapping = (variables or {}).get("body", []) if isinstance(variables, dict) else []
    if not isinstance(mapping, list):
        raise ValueError("invalid_template_data")
    expected = template_body_parameter_count(template)
    # Meta permanently rejects a mismatched parameter count; skip instead.
    if expected is not None and expected != len(mapping):
        raise ValueError("invalid_template_data")
    parameters = []
    for source in mapping:
        value = data.get(source)
        if source not in allowed or value is None or value == "":
            raise ValueError("invalid_template_data")
        parameters.append({"type": "text", "text": str(value)})
    return [{"type": "body", "parameters": parameters}] if parameters else []
