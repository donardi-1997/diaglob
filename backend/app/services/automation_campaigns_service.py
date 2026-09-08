"""Automation campaign business orchestration service.

Handles campaign CRUD, validation, compliance, audience management,
and run/recipient operations. Does NOT import FastAPI.
"""
import json
import logging
import re
from datetime import datetime

from sqlalchemy.orm import Session

from ..automation_campaigns import (
    audience_metrics,
    explain,
    json_load,
    validate_campaign,
    simulate_campaign,
)
from ..automation_execution_engine import initial_next_run, utcnow
from ..models import (
    AutomationAudienceMember,
    AutomationCampaign,
    AutomationDeliveryAttempt,
    AutomationRecipientExecution,
    AutomationRun,
    AutomationExecution,
    Automation,
    Customer,
    Store,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
)
from ..whatsapp_compliance import MESSAGE_MODES, TEMPLATE_VARIABLES

logger = logging.getLogger(__name__)


class CampaignNotFoundError(Exception):
    pass


class StoreNotFoundError(Exception):
    pass


class CampaignConflictError(Exception):
    pass


class CampaignValidationError(Exception):
    pass


class RecipientRetryError(Exception):
    pass


RECOVERABLE_SKIP_REASONS = {"template_required", "template_not_approved", "connection_inactive", "invalid_phone"}


def _campaign_store_or_404(db: Session, organization_id: int, store_id: int) -> Store:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")
    return store


def _campaign_or_404(db: Session, organization_id: int, store_id: int, campaign_id: int) -> AutomationCampaign:
    campaign = db.query(AutomationCampaign).filter(
        AutomationCampaign.id == campaign_id,
        AutomationCampaign.organization_id == organization_id,
        AutomationCampaign.store_id == store_id,
    ).first()
    if not campaign:
        raise CampaignNotFoundError("Automation campaign not found")
    return campaign


def _serialize_campaign(campaign: AutomationCampaign) -> dict:
    return {
        "id": campaign.id, "organization_id": campaign.organization_id,
        "store_id": campaign.store_id, "name": campaign.name,
        "automation_type": campaign.automation_type, "status": campaign.status,
        "audience_type": campaign.audience_type,
        "audience_filters": json_load(campaign.audience_filters),
        "member_count": sum(1 for member in campaign.members if member.included),
        "schedule_type": campaign.schedule_type,
        "schedule_config": json_load(campaign.schedule_config),
        "timezone": campaign.timezone, "send_window_start": campaign.send_window_start,
        "send_window_end": campaign.send_window_end, "cooldown_days": campaign.cooldown_days,
        "channel": campaign.channel, "message_template": campaign.message_template,
        "message_mode": campaign.message_mode, "whatsapp_template_id": campaign.whatsapp_template_id,
        "template_variables": campaign.template_variables,
        "created_at": campaign.created_at.isoformat() + "Z",
        "updated_at": campaign.updated_at.isoformat() + "Z",
    }


def _serialize_run(run: AutomationRun, campaign_name: str | None = None) -> dict:
    return {
        "id": run.id, "automation_id": run.automation_id,
        "campaign_name": campaign_name, "status": run.status,
        "matched_count": run.matched_count, "eligible_count": run.eligible_count,
        "sent_count": run.sent_count, "failed_count": run.failed_count,
        "excluded_count": run.excluded_count,
        "started_at": run.started_at.isoformat() + "Z" if run.started_at else None,
        "completed_at": run.completed_at.isoformat() + "Z" if run.completed_at else None,
        "scheduled_for": run.scheduled_for.isoformat() + "Z" if run.scheduled_for else None,
    }


def _fixed_audience_ids(db: Session, organization_id: int, store_id: int, data: dict) -> set:
    mode = data.get("selection_mode", "explicit")
    if mode not in {"explicit", "all_filtered"}:
        raise CampaignValidationError("Invalid selection_mode")
    selected = set(data.get("selected_customer_ids") or data.get("member_ids") or [])
    if mode == "all_filtered":
        selected = {item["id"] for item in audience_metrics(db, organization_id, store_id, "dynamic", data.get("audience_filters", {}))}
        selected -= set(data.get("excluded_customer_ids", []))
    available = {item["id"] for item in audience_metrics(db, organization_id, store_id, "dynamic", {})}
    if not selected.issubset(available):
        raise CampaignValidationError("Customer is outside store scope")
    return selected


def _replace_campaign_members(db: Session, campaign: AutomationCampaign, organization_id: int, store_id: int, data: dict) -> int:
    unique_ids = _fixed_audience_ids(db, organization_id, store_id, data) if campaign.audience_type == "fixed" else set()
    db.query(AutomationAudienceMember).filter(AutomationAudienceMember.automation_id == campaign.id).delete()
    ids = sorted(unique_ids)
    for offset in range(0, len(ids), 1000):
        db.bulk_insert_mappings(AutomationAudienceMember, [{"automation_id": campaign.id, "customer_id": customer_id, "included": True} for customer_id in ids[offset:offset + 1000]])
    return len(unique_ids)


def _validate_campaign_compliance(db: Session, data: dict, organization_id: int, store_id: int):
    if data["message_mode"] not in MESSAGE_MODES:
        raise CampaignValidationError("Invalid message_mode")
    mapping = data["template_variables"].get("body", [])
    if not isinstance(mapping, list) or not set(mapping).issubset(TEMPLATE_VARIABLES):
        raise CampaignValidationError("Invalid template variables")
    template = None
    if data["whatsapp_template_id"]:
        template = db.query(WhatsAppMessageTemplate).join(WhatsAppConnection).filter(
            WhatsAppMessageTemplate.id == data["whatsapp_template_id"],
            WhatsAppMessageTemplate.organization_id == organization_id,
            WhatsAppConnection.store_id == store_id,
            WhatsAppConnection.organization_id == organization_id,
        ).first()
        if not template:
            raise CampaignValidationError("Template is outside store scope")
        body_components = [item for item in template.components.get("items", []) if str(item.get("type", "")).lower() == "body"]
        body_text = next((item.get("text") for item in body_components if isinstance(item.get("text"), str)), None)
        if body_text is not None:
            expected_parameters = len(re.findall(r"{{\d+}}", body_text))
            if expected_parameters != len(mapping):
                raise CampaignValidationError("Template body parameter count does not match")
    if data["status"] == "active" and data["message_mode"] in {"template", "auto"}:
        if not template or template.status != "approved":
            raise CampaignValidationError("Active template delivery requires an approved template")
    return template


def create_campaign(
    db: Session,
    organization_id: int,
    store_id: int,
    user_id: int,
    data: dict,
) -> dict:
    store = _campaign_store_or_404(db, organization_id, store_id)
    data["timezone"] = data["timezone"] or store.timezone
    validate_campaign(data, store)
    _validate_campaign_compliance(db, data, organization_id, store_id)

    if data["status"] == "active":
        if not db.query(WhatsAppConnection).filter(
            WhatsAppConnection.organization_id == organization_id,
            WhatsAppConnection.store_id == store_id,
            WhatsAppConnection.status == "connected",
        ).first():
            raise CampaignValidationError("WhatsApp channel is not connected")

    if db.query(AutomationCampaign).filter(
        AutomationCampaign.organization_id == organization_id,
        AutomationCampaign.store_id == store_id,
        AutomationCampaign.name == data["name"],
    ).first():
        raise CampaignConflictError("Automation campaign name already exists")

    campaign = AutomationCampaign(
        organization_id=organization_id, store_id=store_id, created_by=user_id,
        **{key: data[key] for key in ("name", "automation_type", "status", "audience_type", "schedule_type", "timezone", "send_window_start", "send_window_end", "cooldown_days", "channel", "message_template", "message_mode", "whatsapp_template_id", "template_variables")},
        audience_filters=data["audience_filters"], schedule_config=data["schedule_config"],
    )

    if campaign.status == "active":
        campaign.next_run_at = initial_next_run(campaign)
        campaign.execution_enabled_at = datetime.utcnow()

    db.add(campaign)
    db.flush()

    member_count = _replace_campaign_members(db, campaign, organization_id, store_id, data)

    if data["status"] == "active" and data["audience_type"] == "fixed" and member_count == 0:
        raise CampaignValidationError("Active fixed campaign requires at least one customer")

    db.commit()
    db.refresh(campaign)
    return _serialize_campaign(campaign)


def list_campaigns(db: Session, organization_id: int, store_id: int) -> dict:
    _campaign_store_or_404(db, organization_id, store_id)
    items = db.query(AutomationCampaign).filter(
        AutomationCampaign.organization_id == organization_id,
        AutomationCampaign.store_id == store_id,
    ).order_by(AutomationCampaign.updated_at.desc()).all()
    return {"items": [_serialize_campaign(item) for item in items], "total": len(items)}


def get_campaign(db: Session, organization_id: int, store_id: int, campaign_id: int) -> dict:
    _campaign_store_or_404(db, organization_id, store_id)
    return _serialize_campaign(_campaign_or_404(db, organization_id, store_id, campaign_id))


def update_campaign(
    db: Session,
    organization_id: int,
    store_id: int,
    campaign_id: int,
    data: dict,
) -> dict:
    store = _campaign_store_or_404(db, organization_id, store_id)
    campaign = _campaign_or_404(db, organization_id, store_id, campaign_id)
    previous_status = campaign.status

    data["timezone"] = data["timezone"] or store.timezone
    validate_campaign(data, store)

    if previous_status == "active" and (
        campaign.audience_type != data["audience_type"]
        or campaign.audience_filters != data["audience_filters"]
        or data.get("member_ids")
        or data.get("selected_customer_ids")
        or data.get("selection_mode") == "all_filtered"
    ):
        raise CampaignValidationError("Pause an active campaign before changing its audience")

    _validate_campaign_compliance(db, data, organization_id, store_id)

    if data["status"] == "active":
        if not db.query(WhatsAppConnection).filter(
            WhatsAppConnection.organization_id == organization_id,
            WhatsAppConnection.store_id == store_id,
            WhatsAppConnection.status == "connected",
        ).first():
            raise CampaignValidationError("WhatsApp channel is not connected")

    for key in ("name", "automation_type", "status", "audience_type", "schedule_type", "timezone", "send_window_start", "send_window_end", "cooldown_days", "channel", "message_template", "message_mode", "whatsapp_template_id", "template_variables"):
        setattr(campaign, key, data[key])

    campaign.audience_filters = data["audience_filters"]
    campaign.schedule_config = data["schedule_config"]

    if campaign.status == "active":
        if campaign.execution_enabled_at is None:
            campaign.execution_enabled_at = datetime.utcnow()
        if campaign.schedule_type == "once" and campaign.last_run_at is not None:
            campaign.next_run_at = None
        elif previous_status != "active" or campaign.next_run_at is None:
            campaign.next_run_at = initial_next_run(campaign)
    elif campaign.status in {"paused", "archived"}:
        campaign.next_run_at = None

    member_count = _replace_campaign_members(db, campaign, organization_id, store_id, data)

    if data["status"] == "active" and data["audience_type"] == "fixed" and member_count == 0:
        raise CampaignValidationError("Active fixed campaign requires at least one customer")

    db.commit()
    db.refresh(campaign)
    return _serialize_campaign(campaign)


def duplicate_campaign(db: Session, organization_id: int, store_id: int, campaign_id: int, user_id: int) -> dict:
    _campaign_store_or_404(db, organization_id, store_id)
    source = _campaign_or_404(db, organization_id, store_id, campaign_id)

    copy = AutomationCampaign(
        organization_id=source.organization_id, store_id=source.store_id,
        name=f"{source.name} (copy)", automation_type=source.automation_type,
        status="draft", audience_type=source.audience_type,
        audience_filters=source.audience_filters, schedule_type=source.schedule_type,
        schedule_config=source.schedule_config, timezone=source.timezone,
        send_window_start=source.send_window_start, send_window_end=source.send_window_end,
        cooldown_days=source.cooldown_days, channel=source.channel,
        message_template=source.message_template, message_mode=source.message_mode,
        whatsapp_template_id=source.whatsapp_template_id, template_variables=source.template_variables,
        created_by=user_id,
    )
    db.add(copy)
    db.flush()
    _replace_campaign_members(db, copy, organization_id, store_id, {"member_ids": [member.customer_id for member in source.members if member.included]})
    db.commit()
    db.refresh(copy)
    return _serialize_campaign(copy)


def simulate_campaign_route(db: Session, organization_id: int, store_id: int, campaign_id: int) -> dict:
    _campaign_store_or_404(db, organization_id, store_id)
    campaign = _campaign_or_404(db, organization_id, store_id, campaign_id)
    store = _campaign_store_or_404(db, organization_id, store_id)
    return simulate_campaign(db, campaign, store)


def list_campaign_runs(db: Session, organization_id: int, store_id: int, campaign_id: int) -> dict:
    _campaign_store_or_404(db, organization_id, store_id)
    campaign = _campaign_or_404(db, organization_id, store_id, campaign_id)
    runs = db.query(AutomationRun).filter(AutomationRun.automation_id == campaign.id).order_by(AutomationRun.id.desc()).all()
    return {"items": [_serialize_run(run, campaign.name) for run in runs]}


def get_campaign_run(db: Session, organization_id: int, store_id: int, campaign_id: int, run_id: int) -> dict:
    _campaign_store_or_404(db, organization_id, store_id)
    campaign = _campaign_or_404(db, organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise CampaignNotFoundError("Run not found")
    terminal = {"sent", "failed", "skipped", "ambiguous"}
    total = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.run_id == run.id).count()
    terminal_count = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.run_id == run.id, AutomationRecipientExecution.status.in_(terminal)).count()
    pending = total - terminal_count
    return {**_serialize_run(run, campaign.name), "total_recipients": total, "pending_count": pending}


def list_run_recipients(
    db: Session, organization_id: int, store_id: int, campaign_id: int, run_id: int,
    status: str | None = None, reason: str | None = None, search: str | None = None,
    page: int = 1, page_size: int = 25,
) -> dict:
    _campaign_store_or_404(db, organization_id, store_id)
    campaign = _campaign_or_404(db, organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise CampaignNotFoundError("Run not found")

    query = db.query(AutomationRecipientExecution, Customer).join(
        Customer, AutomationRecipientExecution.customer_id == Customer.id
    ).filter(AutomationRecipientExecution.run_id == run.id)

    if status:
        query = query.filter(AutomationRecipientExecution.status == status)
    if reason:
        query = query.filter(AutomationRecipientExecution.exclusion_reason == reason)
    if search:
        term = f"%{search.lower()}%"
        query = query.filter((Customer.name.ilike(term)) | (Customer.phone.ilike(term)) | (Customer.email.ilike(term)))

    total = query.count()
    page_size = min(max(1, page_size), 100)
    page = max(1, page)
    total_pages = max(1, (total + page_size - 1) // page_size)
    rows = query.order_by(AutomationRecipientExecution.id).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for recipient, customer in rows:
        items.append({
            "id": recipient.id, "customer_id": recipient.customer_id,
            "customer_name": customer.name, "customer_phone": customer.phone,
            "status": recipient.status, "exclusion_reason": recipient.exclusion_reason,
            "attempt_count": recipient.attempt_count,
            "next_attempt_at": recipient.next_attempt_at.isoformat() + "Z" if recipient.next_attempt_at else None,
            "sent_at": recipient.sent_at.isoformat() + "Z" if recipient.sent_at else None,
            "provider_message_id": recipient.provider_message_id,
            "error_code": recipient.error_code, "error_message": recipient.error_message,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


def get_run_recipient(db: Session, organization_id: int, store_id: int, campaign_id: int, run_id: int, recipient_id: int) -> dict:
    _campaign_store_or_404(db, organization_id, store_id)
    campaign = _campaign_or_404(db, organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise CampaignNotFoundError("Run not found")

    recipient = db.query(AutomationRecipientExecution).filter(
        AutomationRecipientExecution.id == recipient_id,
        AutomationRecipientExecution.run_id == run.id,
    ).first()
    if not recipient:
        raise CampaignNotFoundError("Recipient not found")

    customer = db.get(Customer, recipient.customer_id)
    attempts = db.query(AutomationDeliveryAttempt).filter(
        AutomationDeliveryAttempt.recipient_execution_id == recipient.id
    ).order_by(AutomationDeliveryAttempt.attempt_number).all()

    return {
        "id": recipient.id, "run_id": recipient.run_id, "customer_id": recipient.customer_id,
        "customer_name": customer.name if customer else None, "customer_phone": customer.phone if customer else None,
        "status": recipient.status, "exclusion_reason": recipient.exclusion_reason,
        "rendered_message": recipient.rendered_message,
        "attempt_count": recipient.attempt_count,
        "next_attempt_at": recipient.next_attempt_at.isoformat() + "Z" if recipient.next_attempt_at else None,
        "sent_at": recipient.sent_at.isoformat() + "Z" if recipient.sent_at else None,
        "provider_message_id": recipient.provider_message_id,
        "error_code": recipient.error_code, "error_message": recipient.error_message,
        "template_data": recipient.template_data,
        "attempts": [{"id": a.id, "attempt_number": a.attempt_number, "status": a.status, "provider_message_id": a.provider_message_id, "error_code": a.error_code, "error_message": a.error_message, "started_at": a.started_at.isoformat() + "Z" if a.started_at else None, "finished_at": a.finished_at.isoformat() + "Z" if a.finished_at else None} for a in attempts],
    }


def retry_run_recipient(db: Session, organization_id: int, store_id: int, campaign_id: int, run_id: int, recipient_id: int) -> dict:
    from ..automation_execution_engine import utcnow
    from ..whatsapp_compliance import evaluate_whatsapp_delivery_eligibility

    _campaign_store_or_404(db, organization_id, store_id)
    campaign = _campaign_or_404(db, organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise CampaignNotFoundError("Run not found")

    recipient = db.query(AutomationRecipientExecution).filter(
        AutomationRecipientExecution.id == recipient_id,
        AutomationRecipientExecution.run_id == run.id,
    ).first()
    if not recipient:
        raise CampaignNotFoundError("Recipient not found")

    if recipient.status in {"queued", "processing", "sending", "retry_wait"}:
        raise RecipientRetryError("Recipient is already active")
    if recipient.status == "ambiguous":
        raise RecipientRetryError("Ambiguous recipients cannot be retried to prevent duplicates")
    if recipient.status == "sent":
        raise RecipientRetryError("Sent recipients do not need retry")
    if recipient.status == "skipped" and recipient.exclusion_reason not in RECOVERABLE_SKIP_REASONS:
        raise RecipientRetryError("This skip reason is not recoverable")

    customer = db.get(Customer, recipient.customer_id)
    if not customer or not customer.phone:
        raise RecipientRetryError("Customer phone is unavailable")

    connection = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.store_id == campaign.store_id,
        WhatsAppConnection.organization_id == campaign.organization_id,
        WhatsAppConnection.status == "connected",
    ).first()
    if not connection:
        raise RecipientRetryError("WhatsApp connection is inactive")

    now = utcnow()
    compliance = evaluate_whatsapp_delivery_eligibility(db, campaign, connection, recipient.customer_id, now)
    if not compliance["allowed"]:
        raise RecipientRetryError(f"Compliance check failed: {compliance['reason']}")

    recipient.status = "queued"
    recipient.error_code = None
    recipient.error_message = None
    recipient.next_attempt_at = now
    recipient.claimed_at = None
    recipient.lease_expires_at = None

    if run.status in {"completed", "partial", "failed"}:
        run.status = "pending"
        run.completed_at = None
        states = [r[0] for r in db.query(AutomationRecipientExecution.status).filter(AutomationRecipientExecution.run_id == run.id).all()]
        run.sent_count = states.count("sent")
        run.failed_count = states.count("failed") + states.count("ambiguous")
        run.excluded_count = states.count("skipped")

    db.commit()
    return {"ok": True, "recipient_id": recipient.id, "status": recipient.status}


def list_legacy_automations(db: Session, organization_id: int, store_id: int) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")

    automations = db.query(Automation).filter(
        Automation.organization_id == organization_id,
        (Automation.store_id == store_id) | (Automation.store_id.is_(None)),
    ).order_by(Automation.updated_at.desc()).all()

    items = []
    for a in automations:
        last_exec = db.query(AutomationExecution).filter(
            AutomationExecution.automation_id == a.id,
        ).order_by(AutomationExecution.id.desc()).first()

        items.append({
            "id": a.id, "organization_id": a.organization_id, "store_id": a.store_id,
            "name": a.name, "description": a.description, "active": a.active,
            "trigger_type": a.trigger_type,
            "conditions_json": json.loads(a.conditions_json) if a.conditions_json else [],
            "actions_json": json.loads(a.actions_json) if a.actions_json else [],
            "created_by": a.created_by,
            "created_at": a.created_at.isoformat() + "Z" if a.created_at else None,
            "updated_at": a.updated_at.isoformat() + "Z" if a.updated_at else None,
            "last_execution": (
                {"id": last_exec.id, "status": last_exec.status,
                 "started_at": last_exec.started_at.isoformat() + "Z" if last_exec.started_at else None,
                 "completed_at": last_exec.completed_at.isoformat() + "Z" if last_exec.completed_at else None}
                if last_exec else None
            ),
        })
    return {"items": items, "total": len(items)}


def get_legacy_automation(db: Session, organization_id: int, store_id: int, automation_id: int) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")

    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.organization_id == organization_id,
    ).first()
    if not automation:
        raise CampaignNotFoundError("Automation not found")

    return {
        "id": automation.id, "organization_id": automation.organization_id,
        "store_id": automation.store_id, "name": automation.name,
        "description": automation.description, "active": automation.active,
        "trigger_type": automation.trigger_type,
        "conditions_json": json.loads(automation.conditions_json) if automation.conditions_json else [],
        "actions_json": json.loads(automation.actions_json) if automation.actions_json else [],
        "created_by": automation.created_by,
        "created_at": automation.created_at.isoformat() + "Z" if automation.created_at else None,
        "updated_at": automation.updated_at.isoformat() + "Z" if automation.updated_at else None,
    }


def create_legacy_automation(db: Session, organization_id: int, store_id: int, user_id: int, data: dict) -> dict:
    from ..automations import VALID_TRIGGER_TYPES

    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")

    if data["trigger_type"] not in VALID_TRIGGER_TYPES:
        raise CampaignValidationError("Invalid trigger_type")

    existing = db.query(Automation).filter(
        Automation.organization_id == organization_id,
        Automation.store_id == store_id,
        Automation.name == data["name"],
    ).first()
    if existing:
        raise CampaignConflictError("Automation with this name already exists in this store")

    automation = Automation(
        organization_id=organization_id, store_id=store_id,
        name=data["name"], description=data.get("description"),
        active=data.get("active", True), trigger_type=data["trigger_type"],
        conditions_json=json.dumps(data.get("conditions_json", [])),
        actions_json=json.dumps(data.get("actions_json", [])),
        created_by=user_id,
    )
    db.add(automation)
    db.commit()
    db.refresh(automation)

    return {
        "id": automation.id, "organization_id": automation.organization_id,
        "store_id": automation.store_id, "name": automation.name,
        "description": automation.description, "active": automation.active,
        "trigger_type": automation.trigger_type,
        "conditions_json": json.loads(automation.conditions_json),
        "actions_json": json.loads(automation.actions_json),
        "created_by": automation.created_by,
        "created_at": automation.created_at.isoformat() + "Z" if automation.created_at else None,
        "updated_at": automation.updated_at.isoformat() + "Z" if automation.updated_at else None,
    }


def update_legacy_automation(db: Session, organization_id: int, store_id: int, automation_id: int, data: dict) -> dict:
    from ..automations import VALID_TRIGGER_TYPES

    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")

    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.organization_id == organization_id,
    ).first()
    if not automation:
        raise CampaignNotFoundError("Automation not found")

    if data.get("trigger_type") is not None and data["trigger_type"] not in VALID_TRIGGER_TYPES:
        raise CampaignValidationError("Invalid trigger_type")

    if data.get("name") is not None:
        automation.name = data["name"]
    if data.get("description") is not None:
        automation.description = data["description"]
    if data.get("store_id") is not None:
        automation.store_id = data["store_id"]
    if data.get("active") is not None:
        automation.active = data["active"]
    if data.get("trigger_type") is not None:
        automation.trigger_type = data["trigger_type"]
    if data.get("conditions_json") is not None:
        automation.conditions_json = json.dumps(data["conditions_json"])
    if data.get("actions_json") is not None:
        automation.actions_json = json.dumps(data["actions_json"])

    automation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(automation)

    return {
        "id": automation.id, "organization_id": automation.organization_id,
        "store_id": automation.store_id, "name": automation.name,
        "description": automation.description, "active": automation.active,
        "trigger_type": automation.trigger_type,
        "conditions_json": json.loads(automation.conditions_json),
        "actions_json": json.loads(automation.actions_json),
        "created_by": automation.created_by,
        "created_at": automation.created_at.isoformat() + "Z" if automation.created_at else None,
        "updated_at": automation.updated_at.isoformat() + "Z" if automation.updated_at else None,
    }


def delete_legacy_automation(db: Session, organization_id: int, store_id: int, automation_id: int) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")

    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.organization_id == organization_id,
    ).first()
    if not automation:
        raise CampaignNotFoundError("Automation not found")

    db.delete(automation)
    db.commit()
    return {"ok": True}


def toggle_legacy_automation(db: Session, organization_id: int, store_id: int, automation_id: int) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")

    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.organization_id == organization_id,
    ).first()
    if not automation:
        raise CampaignNotFoundError("Automation not found")

    automation.active = not automation.active
    automation.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(automation)

    return {
        "id": automation.id, "active": automation.active,
        "updated_at": automation.updated_at.isoformat() + "Z" if automation.updated_at else None,
    }


def run_legacy_automation(db: Session, organization_id: int, store_id: int, automation_id: int, event_type: str, payload: dict) -> dict:
    from ..automations import execute_automation

    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")

    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.organization_id == organization_id,
    ).first()
    if not automation:
        raise CampaignNotFoundError("Automation not found")

    execution = execute_automation(db=db, automation=automation, event_type=event_type, payload=payload)

    return {
        "id": execution.id, "automation_id": execution.automation_id,
        "status": execution.status, "event_type": execution.event_type,
        "input_json": json.loads(execution.input_json),
        "result_json": json.loads(execution.result_json),
        "error_message": execution.error_message,
        "started_at": execution.started_at.isoformat() + "Z" if execution.started_at else None,
        "completed_at": execution.completed_at.isoformat() + "Z" if execution.completed_at else None,
    }


def list_legacy_executions(db: Session, organization_id: int, store_id: int, automation_id: int) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")

    automation = db.query(Automation).filter(
        Automation.id == automation_id,
        Automation.organization_id == organization_id,
    ).first()
    if not automation:
        raise CampaignNotFoundError("Automation not found")

    executions = db.query(AutomationExecution).filter(
        AutomationExecution.automation_id == automation_id,
        AutomationExecution.organization_id == organization_id,
    ).order_by(AutomationExecution.id.desc()).all()

    items = []
    for e in executions:
        items.append({
            "id": e.id, "automation_id": e.automation_id, "automation_name": automation.name,
            "status": e.status, "event_type": e.event_type, "event_id": e.event_id,
            "input_json": json.loads(e.input_json), "result_json": json.loads(e.result_json),
            "error_message": e.error_message,
            "started_at": e.started_at.isoformat() + "Z" if e.started_at else None,
            "completed_at": e.completed_at.isoformat() + "Z" if e.completed_at else None,
        })
    return {"items": items, "total": len(items)}


def list_all_legacy_executions(db: Session, organization_id: int, store_id: int) -> dict:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise StoreNotFoundError("Store not found")

    executions = db.query(AutomationExecution).filter(
        AutomationExecution.organization_id == organization_id,
        AutomationExecution.store_id == store_id,
    ).order_by(AutomationExecution.id.desc()).limit(100).all()

    items = []
    for e in executions:
        auto = db.query(Automation).filter(Automation.id == e.automation_id).first()
        items.append({
            "id": e.id, "automation_id": e.automation_id,
            "automation_name": auto.name if auto else "Deleted",
            "status": e.status, "event_type": e.event_type, "event_id": e.event_id,
            "input_json": json.loads(e.input_json), "result_json": json.loads(e.result_json),
            "error_message": e.error_message,
            "started_at": e.started_at.isoformat() + "Z" if e.started_at else None,
            "completed_at": e.completed_at.isoformat() + "Z" if e.completed_at else None,
        })
    return {"items": items, "total": len(items)}
