"""Automations HTTP router."""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..automations import (
    execute_automation,
    emit_event,
    safe_emit_event,
    VALID_TRIGGER_TYPES,
)
from ..automation_campaigns import (
    audience_metrics,
    explain,
    json_load,
    render_template,
    simulate_campaign,
    validate_campaign,
)
from ..automation_execution_engine import initial_next_run, utcnow
from ..automation_flow_graph import validate_graph
from ..automation_flow_engine import materialize_flow_trigger, utcnow as _utcnow
from ..automation_flow_helpers import (
    serialize_flow as _sf,
    serialize_version as _sv,
    serialize_run as _sr,
    serialize_recipient as _srec,
)
from ..analytics import (
    get_automations_analytics,
    get_date_range,
)
from ..db import get_db
from ..models import (
    Automation,
    AutomationAudienceMember,
    AutomationCampaign,
    AutomationDeliveryAttempt,
    AutomationExecution,
    AutomationFlow,
    AutomationFlowRecipientExecution,
    AutomationFlowRun,
    AutomationFlowVersion,
    AutomationNodeExecution,
    AutomationRateLimit,
    AutomationRecipientExecution,
    AutomationRun,
    Customer,
    CustomerStoreProfile,
    Organization,
    OrganizationMembership,
    Store,
    WhatsAppConnection,
    WhatsAppMessageTemplate,
)
from ..whatsapp_compliance import MESSAGE_MODES, TEMPLATE_VARIABLES
from .deps import get_current_membership, get_store_scope, require_permission

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================
# DTOs
# ============================================================


class AutomationCreate(BaseModel):
    name: str
    description: str | None = None
    store_id: int | None = None
    active: bool = True
    trigger_type: str = "manual"
    conditions_json: list[dict] = []
    actions_json: list[dict] = []


class AutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    store_id: int | None = None
    active: bool | None = None
    trigger_type: str | None = None
    conditions_json: list[dict] | None = None
    actions_json: list[dict] | None = None


class AutomationRunRequest(BaseModel):
    event_type: str = "manual"
    payload: dict = {}


class AutomationCampaignPayload(BaseModel):
    name: str
    automation_type: str = "custom"
    status: str = "draft"
    audience_type: str = "dynamic"
    audience_filters: dict = {}
    member_ids: list[int] = []
    selection_mode: str = "explicit"
    selected_customer_ids: list[int] = []
    excluded_customer_ids: list[int] = []
    schedule_type: str = "once"
    schedule_config: dict = {}
    timezone: str | None = None
    send_window_start: str | None = None
    send_window_end: str | None = None
    cooldown_days: int = 0
    channel: str = "whatsapp"
    message_template: str = ""
    message_mode: str = "free_form"
    whatsapp_template_id: int | None = None
    template_variables: dict = {}


class AudiencePreviewRequest(BaseModel):
    audience_type: str = "dynamic"
    audience_filters: dict = {}
    member_ids: list[int] = []
    selection_mode: str = "explicit"
    selected_customer_ids: list[int] = []
    excluded_customer_ids: list[int] = []


class _FlowCreate(BaseModel):
    name: str
    description: str | None = None
    graph: dict = {}


class _FlowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph: dict | None = None


class _FlowVersionPublish(BaseModel):
    graph: dict


class _FlowRunCreate(BaseModel):
    customer_ids: list[int]
    trigger_key: str | None = None


# ============================================================
# HELPERS
# ============================================================


def _campaign_store_or_404(db, organization_id, store_id):
    store = db.query(Store).filter(Store.id == store_id, Store.organization_id == organization_id, Store.deleted.is_(False)).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store


def _serialize_campaign(campaign):
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


def _campaign_or_404(db, organization_id, store_id, campaign_id):
    campaign = db.query(AutomationCampaign).filter(
        AutomationCampaign.id == campaign_id,
        AutomationCampaign.organization_id == organization_id,
        AutomationCampaign.store_id == store_id,
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Automation campaign not found")
    return campaign


def _fixed_audience_ids(db, organization_id, store_id, data):
    mode = data.get("selection_mode", "explicit")
    if mode not in {"explicit", "all_filtered"}:
        raise HTTPException(400, "Invalid selection_mode")
    selected = set(data.get("selected_customer_ids") or data.get("member_ids") or [])
    if mode == "all_filtered":
        selected = {item["id"] for item in audience_metrics(db, organization_id, store_id, "dynamic", data.get("audience_filters", {}))}
        selected -= set(data.get("excluded_customer_ids", []))
    # Fixed audiences are store-scoped. Do not silently accept an org customer
    # that has no profile in the campaign's store.
    available = {item["id"] for item in audience_metrics(db, organization_id, store_id, "dynamic", {})}
    if not selected.issubset(available):
        raise HTTPException(status_code=400, detail="Customer is outside store scope")
    return selected


def _replace_campaign_members(db, campaign, organization_id, store_id, data):
    unique_ids = _fixed_audience_ids(db, organization_id, store_id, data) if campaign.audience_type == "fixed" else set()
    db.query(AutomationAudienceMember).filter(AutomationAudienceMember.automation_id == campaign.id).delete()
    ids = sorted(unique_ids)
    for offset in range(0, len(ids), 1000):
        db.bulk_insert_mappings(AutomationAudienceMember, [{"automation_id": campaign.id, "customer_id": customer_id, "included": True} for customer_id in ids[offset:offset + 1000]])
    return len(unique_ids)


def _validate_campaign_compliance(db, data, organization_id, store_id):
    if data["message_mode"] not in MESSAGE_MODES:
        raise HTTPException(400, "Invalid message_mode")
    mapping = data["template_variables"].get("body", [])
    if not isinstance(mapping, list) or not set(mapping).issubset(TEMPLATE_VARIABLES):
        raise HTTPException(400, "Invalid template variables")
    template = None
    if data["whatsapp_template_id"]:
        template = db.query(WhatsAppMessageTemplate).join(WhatsAppConnection).filter(
            WhatsAppMessageTemplate.id == data["whatsapp_template_id"],
            WhatsAppMessageTemplate.organization_id == organization_id,
            WhatsAppConnection.store_id == store_id,
            WhatsAppConnection.organization_id == organization_id,
        ).first()
        if not template:
            raise HTTPException(400, "Template is outside store scope")
        body_components = [item for item in template.components.get("items", []) if str(item.get("type", "")).lower() == "body"]
        body_text = next((item.get("text") for item in body_components if isinstance(item.get("text"), str)), None)
        if body_text is not None:
            expected_parameters = len(re.findall(r"{{\d+}}", body_text))
            if expected_parameters != len(mapping):
                raise HTTPException(400, "Template body parameter count does not match")
    if data["status"] == "active" and data["message_mode"] in {"template", "auto"}:
        if not template or template.status != "approved":
            raise HTTPException(400, "Active template delivery requires an approved template")
    return template


def _serialize_run(run, campaign_name=None):
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


RECOVERABLE_SKIP_REASONS = {"template_required", "template_not_approved", "connection_inactive", "invalid_phone"}


def _flow_version_or_404(db: Session, flow: AutomationFlow, version_id: int) -> AutomationFlowVersion:
    version = db.query(AutomationFlowVersion).filter(
        AutomationFlowVersion.id == version_id,
        AutomationFlowVersion.flow_id == flow.id,
        AutomationFlowVersion.organization_id == flow.organization_id,
    ).first()
    if not version:
        raise HTTPException(404, detail="Version not found")
    return version


# ============================================================
# ROUTES — Campaign helpers + audience + CRUD + runs + recipients
# ============================================================


@router.post("/api/stores/{store_id}/automation-campaigns/audience/preview")
def preview_automation_audience(
    store_id: int,
    payload: AudiencePreviewRequest,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    if payload.audience_type not in {"dynamic", "fixed"}:
        raise HTTPException(400, "Invalid audience_type")
    data = payload.model_dump()
    member_ids = _fixed_audience_ids(db, membership.organization_id, store_id, data) if payload.audience_type == "fixed" else data["member_ids"]
    metrics = audience_metrics(db, membership.organization_id, store_id, payload.audience_type, payload.audience_filters, list(member_ids))
    segment_distribution, country_distribution = {}, {}
    for item in metrics:
        segment_distribution[item.get("primary_segment") or "unknown"] = segment_distribution.get(item.get("primary_segment") or "unknown", 0) + 1
        country_distribution[item.get("country_code") or "unknown"] = country_distribution.get(item.get("country_code") or "unknown", 0) + 1
    return {"eligible_count": len(metrics), "sample": [explain(item) for item in metrics[:20]], "segment_distribution": segment_distribution, "country_distribution": country_distribution}


@router.get("/api/stores/{store_id}/automation-campaigns/audience/customers")
def list_automation_audience_customers(
    store_id: int,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    segment: str | None = None,
    priority: str | None = None,
    health: str | None = None,
    country: str | None = None,
    needs_attention: bool | None = None,
    has_orders: bool | None = None,
    sort: str = "priority_desc",
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    from ..customers.intelligence import get_customer_list
    _campaign_store_or_404(db, membership.organization_id, store_id)
    result = get_customer_list(db, membership.organization_id, store_id, segment=segment, search=search, has_orders=has_orders, page=max(1, page), page_size=min(max(1, page_size), 100), sort=sort, priority=priority, health=health, needs_attention=needs_attention, country=country)
    fields = ("id", "name", "phone", "email", "country_code", "primary_segment", "priority", "customer_score", "customer_health", "last_interaction_at", "successful_order_count", "spend_by_currency", "needs_attention")
    return {**result, "items": [{("customer_id" if key == "id" else key): item.get(key) for key in fields} for item in result["items"]]}


@router.post("/api/stores/{store_id}/automation-campaigns")
def create_automation_campaign(
    store_id: int,
    payload: AutomationCampaignPayload,
    membership: OrganizationMembership = Depends(require_permission("automations.write")),
    db: Session = Depends(get_db),
):
    store = _campaign_store_or_404(db, membership.organization_id, store_id)
    data = payload.model_dump()
    data["timezone"] = data["timezone"] or store.timezone
    validate_campaign(data, store)
    _validate_campaign_compliance(db, data, membership.organization_id, store_id)
    if data["status"] == "active" and not db.query(WhatsAppConnection).filter(WhatsAppConnection.organization_id == membership.organization_id, WhatsAppConnection.store_id == store_id, WhatsAppConnection.status == "connected").first():
        raise HTTPException(400, "WhatsApp channel is not connected")
    if db.query(AutomationCampaign).filter(AutomationCampaign.organization_id == membership.organization_id, AutomationCampaign.store_id == store_id, AutomationCampaign.name == payload.name).first():
        raise HTTPException(409, "Automation campaign name already exists")
    campaign = AutomationCampaign(
        organization_id=membership.organization_id, store_id=store_id, created_by=membership.user_id,
        **{key: data[key] for key in ("name", "automation_type", "status", "audience_type", "schedule_type", "timezone", "send_window_start", "send_window_end", "cooldown_days", "channel", "message_template", "message_mode", "whatsapp_template_id", "template_variables")},
        audience_filters=data["audience_filters"], schedule_config=data["schedule_config"],
    )
    if campaign.status == "active":
        campaign.next_run_at = initial_next_run(campaign)
        campaign.execution_enabled_at = datetime.utcnow()
    db.add(campaign); db.flush()
    member_count = _replace_campaign_members(db, campaign, membership.organization_id, store_id, data)
    if data["status"] == "active" and data["audience_type"] == "fixed" and member_count == 0:
        raise HTTPException(400, "Active fixed campaign requires at least one customer")
    db.commit(); db.refresh(campaign)
    return _serialize_campaign(campaign)


@router.get("/api/stores/{store_id}/automation-campaigns")
def list_automation_campaigns(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    items = db.query(AutomationCampaign).filter(AutomationCampaign.organization_id == membership.organization_id, AutomationCampaign.store_id == store_id).order_by(AutomationCampaign.updated_at.desc()).all()
    return {"items": [_serialize_campaign(item) for item in items], "total": len(items)}


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}")
def get_automation_campaign(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    return _serialize_campaign(_campaign_or_404(db, membership.organization_id, store_id, campaign_id))


@router.put("/api/stores/{store_id}/automation-campaigns/{campaign_id}")
def update_automation_campaign(campaign_id: int, store_id: int, payload: AutomationCampaignPayload, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    store = _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    previous_status = campaign.status
    data = payload.model_dump(); data["timezone"] = data["timezone"] or store.timezone
    validate_campaign(data, store)
    if previous_status == "active" and (campaign.audience_type != data["audience_type"] or campaign.audience_filters != data["audience_filters"] or data.get("member_ids") or data.get("selected_customer_ids") or data.get("selection_mode") == "all_filtered"):
        raise HTTPException(400, "Pause an active campaign before changing its audience")
    _validate_campaign_compliance(db, data, membership.organization_id, store_id)
    if data["status"] == "active" and not db.query(WhatsAppConnection).filter(WhatsAppConnection.organization_id == membership.organization_id, WhatsAppConnection.store_id == store_id, WhatsAppConnection.status == "connected").first():
        raise HTTPException(400, "WhatsApp channel is not connected")
    for key in ("name", "automation_type", "status", "audience_type", "schedule_type", "timezone", "send_window_start", "send_window_end", "cooldown_days", "channel", "message_template", "message_mode", "whatsapp_template_id", "template_variables"):
        setattr(campaign, key, data[key])
    campaign.audience_filters = data["audience_filters"]; campaign.schedule_config = data["schedule_config"]
    if campaign.status == "active":
        if campaign.execution_enabled_at is None:
            campaign.execution_enabled_at = datetime.utcnow()
        if campaign.schedule_type == "once" and campaign.last_run_at is not None:
            campaign.next_run_at = None
        elif previous_status != "active" or campaign.next_run_at is None:
            campaign.next_run_at = initial_next_run(campaign)
    elif campaign.status in {"paused", "archived"}:
        campaign.next_run_at = None
    member_count = _replace_campaign_members(db, campaign, membership.organization_id, store_id, data)
    if data["status"] == "active" and data["audience_type"] == "fixed" and member_count == 0:
        raise HTTPException(400, "Active fixed campaign requires at least one customer")
    db.commit(); db.refresh(campaign)
    return _serialize_campaign(campaign)


@router.post("/api/stores/{store_id}/automation-campaigns/{campaign_id}/simulate")
def simulate_automation_campaign(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    store = _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    return simulate_campaign(db, campaign, store)


@router.post("/api/stores/{store_id}/automation-campaigns/{campaign_id}/duplicate")
def duplicate_automation_campaign(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    source = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    copy = AutomationCampaign(organization_id=source.organization_id, store_id=source.store_id, name=f"{source.name} (copy)", automation_type=source.automation_type, status="draft", audience_type=source.audience_type, audience_filters=source.audience_filters, schedule_type=source.schedule_type, schedule_config=source.schedule_config, timezone=source.timezone, send_window_start=source.send_window_start, send_window_end=source.send_window_end, cooldown_days=source.cooldown_days, channel=source.channel, message_template=source.message_template, message_mode=source.message_mode, whatsapp_template_id=source.whatsapp_template_id, template_variables=source.template_variables, created_by=membership.user_id)
    db.add(copy); db.flush()
    _replace_campaign_members(db, copy, membership.organization_id, [member.customer_id for member in source.members if member.included])
    db.commit(); db.refresh(copy)
    return _serialize_campaign(copy)


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs")
def list_automation_campaign_runs(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    runs = db.query(AutomationRun).filter(AutomationRun.automation_id == campaign.id).order_by(AutomationRun.id.desc()).all()
    return {"items": [_serialize_run(run, campaign.name) for run in runs]}


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}")
def get_automation_run(run_id: int, campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    terminal = {"sent", "failed", "skipped", "ambiguous"}
    total = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.run_id == run.id).count()
    terminal_count = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.run_id == run.id, AutomationRecipientExecution.status.in_(terminal)).count()
    pending = total - terminal_count
    return {**_serialize_run(run, campaign.name), "total_recipients": total, "pending_count": pending}


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}/recipients")
def list_run_recipients(run_id: int, campaign_id: int, store_id: int, status: str | None = None, reason: str | None = None, search: str | None = None, page: int = 1, page_size: int = 25, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    from ..models import Customer
    query = db.query(AutomationRecipientExecution, Customer).join(Customer, AutomationRecipientExecution.customer_id == Customer.id).filter(AutomationRecipientExecution.run_id == run.id)
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


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}/recipients/{recipient_id}")
def get_run_recipient(recipient_id: int, run_id: int, campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    from ..models import Customer, AutomationDeliveryAttempt
    recipient = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.id == recipient_id, AutomationRecipientExecution.run_id == run.id).first()
    if not recipient:
        raise HTTPException(404, "Recipient not found")
    customer = db.get(Customer, recipient.customer_id)
    attempts = db.query(AutomationDeliveryAttempt).filter(AutomationDeliveryAttempt.recipient_execution_id == recipient.id).order_by(AutomationDeliveryAttempt.attempt_number).all()
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


@router.post("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}/recipients/{recipient_id}/retry")
def retry_run_recipient(recipient_id: int, run_id: int, campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    from ..automation_execution_engine import utcnow
    from ..models import Customer, WhatsAppConnection
    _campaign_store_or_404(db, membership.organization_id, store_id)
    campaign = _campaign_or_404(db, membership.organization_id, store_id, campaign_id)
    run = db.query(AutomationRun).filter(AutomationRun.id == run_id, AutomationRun.automation_id == campaign.id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    recipient = db.query(AutomationRecipientExecution).filter(AutomationRecipientExecution.id == recipient_id, AutomationRecipientExecution.run_id == run.id).first()
    if not recipient:
        raise HTTPException(404, "Recipient not found")
    if recipient.status in {"queued", "processing", "sending", "retry_wait"}:
        raise HTTPException(400, "Recipient is already active")
    if recipient.status == "ambiguous":
        raise HTTPException(400, "Ambiguous recipients cannot be retried to prevent duplicates")
    if recipient.status == "sent":
        raise HTTPException(400, "Sent recipients do not need retry")
    if recipient.status == "skipped" and recipient.exclusion_reason not in RECOVERABLE_SKIP_REASONS:
        raise HTTPException(400, "This skip reason is not recoverable")
    customer = db.get(Customer, recipient.customer_id)
    if not customer or not customer.phone:
        raise HTTPException(400, "Customer phone is unavailable")
    connection = db.query(WhatsAppConnection).filter(WhatsAppConnection.store_id == campaign.store_id, WhatsAppConnection.organization_id == campaign.organization_id, WhatsAppConnection.status == "connected").first()
    if not connection:
        raise HTTPException(400, "WhatsApp connection is inactive")
    from ..whatsapp_compliance import evaluate_whatsapp_delivery_eligibility
    now = utcnow()
    compliance = evaluate_whatsapp_delivery_eligibility(db, campaign, connection, recipient.customer_id, now)
    if not compliance["allowed"]:
        raise HTTPException(400, f"Compliance check failed: {compliance['reason']}")
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


# ============================================================
# ROUTES — Automation Flows V2.2
# ============================================================


@router.post("/api/stores/{store_id}/automation-flows")
def create_flow(store_id: int, payload: _FlowCreate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    _campaign_store_or_404(db, membership.organization_id, store_id)
    if payload.graph:
        errors = validate_graph(payload.graph)
        if errors:
            raise HTTPException(422, detail={"errors": errors})
    flow = AutomationFlow(
        organization_id=membership.organization_id, store_id=store_id,
        name=payload.name, description=payload.description,
        status="draft", created_by=membership.user_id,
    )
    db.add(flow)
    db.flush()
    if payload.graph:
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=membership.organization_id,
            version_number=1, graph=payload.graph,
        )
        db.add(ver)
        db.flush()
        flow.current_version_id = ver.id
    db.commit()
    return _sf(flow)


@router.get("/api/stores/{store_id}/automation-flows")
def list_flows(store_id: int, status: str | None = None, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    q = db.query(AutomationFlow).filter(
        AutomationFlow.organization_id == membership.organization_id,
        AutomationFlow.store_id == store_id,
    )
    if status:
        q = q.filter(AutomationFlow.status == status)
    return [_sf(f) for f in q.order_by(AutomationFlow.updated_at.desc()).all()]


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}")
def get_flow(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    result = _sf(flow)
    if flow.current_version_id:
        ver = _flow_version_or_404(db, flow, flow.current_version_id)
        result["current_version"] = _sv(ver)
    return result


@router.put("/api/stores/{store_id}/automation-flows/{flow_id}")
def update_flow(store_id: int, flow_id: int, payload: _FlowUpdate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    if flow.status == "active":
        raise HTTPException(409, detail="Cannot edit active flow; duplicate or archive first")
    if payload.name is not None:
        flow.name = payload.name
    if payload.description is not None:
        flow.description = payload.description
    if payload.graph is not None:
        errors = validate_graph(payload.graph)
        if errors:
            raise HTTPException(422, detail={"errors": errors})
        max_ver = db.query(AutomationFlowVersion.version_number).filter(
            AutomationFlowVersion.flow_id == flow.id
        ).order_by(AutomationFlowVersion.version_number.desc()).first()
        next_num = (max_ver[0] if max_ver else 0) + 1
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=membership.organization_id,
            version_number=next_num, graph=payload.graph,
        )
        db.add(ver)
        db.flush()
        flow.current_version_id = ver.id
    flow.updated_at = _utcnow()
    db.commit()
    return _sf(flow)


@router.delete("/api/stores/{store_id}/automation-flows/{flow_id}")
def archive_flow(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    flow.status = "archived"
    flow.updated_at = _utcnow()
    db.commit()
    return {"status": "archived", "id": flow.id}


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/versions")
def list_versions(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    versions = db.query(AutomationFlowVersion).filter(
        AutomationFlowVersion.flow_id == flow_id
    ).order_by(AutomationFlowVersion.version_number.desc()).all()
    return [_sv(v) for v in versions]


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/versions")
def create_version(store_id: int, flow_id: int, payload: _FlowVersionPublish, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    errors = validate_graph(payload.graph)
    if errors:
        raise HTTPException(422, detail={"errors": errors})
    max_ver = db.query(AutomationFlowVersion.version_number).filter(
        AutomationFlowVersion.flow_id == flow_id
    ).order_by(AutomationFlowVersion.version_number.desc()).first()
    next_num = (max_ver[0] if max_ver else 0) + 1
    ver = AutomationFlowVersion(
        flow_id=flow_id, organization_id=membership.organization_id,
        version_number=next_num, graph=payload.graph,
    )
    db.add(ver)
    db.flush()
    flow.current_version_id = ver.id
    flow.updated_at = _utcnow()
    db.commit()
    return _sv(ver)


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/versions/{version_id}/publish")
def publish_version(store_id: int, flow_id: int, version_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    ver = _flow_version_or_404(db, flow, version_id)
    if ver.published_at:
        raise HTTPException(409, detail="Version already published")
    ver.published_at = _utcnow()
    flow.updated_at = _utcnow()
    db.commit()
    return _sv(ver)


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/activate")
def activate_flow(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    if not flow.current_version_id:
        raise HTTPException(409, detail="No version to activate")
    ver = _flow_version_or_404(db, flow, flow.current_version_id)
    if not ver.published_at:
        raise HTTPException(409, detail="Version must be published before activation")
    ver.activated_at = _utcnow()
    flow.active_version_id = ver.id
    flow.status = "active"
    flow.updated_at = _utcnow()
    db.commit()
    return _sf(flow)


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/deactivate")
def deactivate_flow(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    flow.status = "draft"
    flow.updated_at = _utcnow()
    db.commit()
    return _sf(flow)


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/runs")
def trigger_flow_run(store_id: int, flow_id: int, payload: _FlowRunCreate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    if flow.status != "active" or not flow.active_version_id:
        raise HTTPException(409, detail="Flow must be active to trigger")
    customers = db.query(Customer).join(
        CustomerStoreProfile,
        CustomerStoreProfile.customer_id == Customer.id,
    ).filter(
        Customer.id.in_(payload.customer_ids),
        Customer.organization_id == membership.organization_id,
        CustomerStoreProfile.store_id == store_id,
    ).all()
    found_ids = {c.id for c in customers}
    missing = set(payload.customer_ids) - found_ids
    if missing:
        raise HTTPException(422, detail={"errors": [f"Customer {cid} not found" for cid in sorted(missing)]})
    run = materialize_flow_trigger(db, flow, payload.customer_ids, payload.trigger_key)
    if not run:
        raise HTTPException(409, detail="Trigger key already used or flow not materializable")
    return _sr(run)


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs")
def list_flow_runs(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    runs = db.query(AutomationFlowRun).filter(
        AutomationFlowRun.flow_id == flow_id
    ).order_by(AutomationFlowRun.created_at.desc()).all()
    return [_sr(r) for r in runs]


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}")
def get_flow_run(store_id: int, flow_id: int, run_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    run = db.get(AutomationFlowRun, run_id)
    if not run or run.flow_id != flow_id:
        raise HTTPException(404, detail="Run not found")
    recipients = db.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id
    ).all()
    result = _sr(run)
    result["recipients"] = [_srec(r) for r in recipients]
    return result


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}/recipients")
def list_flow_run_recipients(store_id: int,
    flow_id: int, run_id: int,
    status: str | None = None, search: str | None = None,
    page: int = 1, size: int = 50,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    run = db.get(AutomationFlowRun, run_id)
    if not run or run.flow_id != flow_id:
        raise HTTPException(404, detail="Run not found")
    q = db.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id,
    )
    if status:
        q = q.filter(AutomationFlowRecipientExecution.status == status)
    if search:
        q = q.join(Customer).filter(
            (Customer.name.ilike(f"%{search}%")) | (Customer.phone.ilike(f"%{search}%"))
        )
    total = q.count()
    items = q.order_by(AutomationFlowRecipientExecution.id).offset((page - 1) * size).limit(size).all()
    return {"items": [_srec(r) for r in items], "total": total, "page": page, "size": size, "pages": max(1, -(-total // size))}


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}/recipients/{recipient_id}")
def get_flow_recipient_detail(store_id: int, flow_id: int, run_id: int, recipient_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    recipient = db.get(AutomationFlowRecipientExecution, recipient_id)
    if not recipient or recipient.flow_run_id != run_id:
        raise HTTPException(404, detail="Recipient not found")
    node_execs = db.query(AutomationNodeExecution).filter(
        AutomationNodeExecution.flow_recipient_execution_id == recipient_id
    ).order_by(AutomationNodeExecution.started_at).all()
    result = _srec(recipient)
    result["node_executions"] = [
        {"id": ne.id, "node_id": ne.node_id, "node_type": ne.node_type,
         "status": ne.status, "outcome": ne.outcome,
         "provider_message_id": ne.provider_message_id,
         "error_code": ne.error_code, "error_message": ne.error_message,
         "metadata": ne.extra_data,
         "started_at": ne.started_at.isoformat() if ne.started_at else None,
         "completed_at": ne.completed_at.isoformat() if ne.completed_at else None}
        for ne in node_execs
    ]
    return result


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}/recipients/{recipient_id}/retry")
def retry_flow_recipient(store_id: int, flow_id: int, run_id: int, recipient_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != membership.organization_id or flow.store_id != store_id:
        raise HTTPException(404, detail="Flow not found")
    recipient = db.get(AutomationFlowRecipientExecution, recipient_id)
    if not recipient or recipient.flow_run_id != run_id:
        raise HTTPException(404, detail="Recipient not found")
    if recipient.status not in ("failed", "ambiguous", "completed"):
        raise HTTPException(409, detail=f"Cannot retry recipient in '{recipient.status}' status")
    now = _utcnow()
    recipient.status = "active"
    recipient.error_code = None
    recipient.error_message = None
    recipient.claim_token = None
    recipient.claim_expires_at = None
    recipient.next_action_at = now
    recipient.started_at = now
    recipient.completed_at = None
    run = db.get(AutomationFlowRun, run_id)
    statuses = [r[0] for r in db.query(AutomationFlowRecipientExecution.status).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id,
    ).all()]
    run.failed_recipients = sum(1 for s in statuses if s in ("failed", "ambiguous"))
    run.completed_recipients = sum(1 for s in statuses if s == "completed")
    if run.status == "completed":
        run.status = "pending"
        run.completed_at = None
    db.commit()
    return _srec(recipient)


@router.post("/api/stores/{store_id}/automation-flows/simulate")
def simulate_flow(store_id: int, payload: _FlowCreate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    graph = payload.graph
    if not graph:
        raise HTTPException(422, detail={"errors": ["Graph is required for simulation"]})
    errors = validate_graph(graph)
    if errors:
        return {"valid": False, "errors": errors, "warnings": []}
    warnings: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    message_nodes = [n for n in nodes if n.get("type") == "message"]
    wait_nodes = [n for n in nodes if n.get("type") == "wait"]
    condition_nodes = [n for n in nodes if n.get("type") == "condition"]
    end_nodes = [n for n in nodes if n.get("type") == "end"]
    if len(message_nodes) == 0:
        warnings.append("Flow has no message nodes")
    if len(wait_nodes) > 5:
        warnings.append(f"Flow has {len(wait_nodes)} wait nodes")
    return {
        "valid": True, "errors": [], "warnings": warnings,
        "summary": {
            "total_nodes": len(nodes), "message_nodes": len(message_nodes),
            "wait_nodes": len(wait_nodes), "condition_nodes": len(condition_nodes),
            "end_nodes": len(end_nodes),
        },
    }


# ============================================================
# ROUTES — Legacy Automations CRUD + Executions
# ============================================================


@router.get(
    "/api/stores/{store_id}/automations"
)
def list_automations(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.read"
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

    automations = (
        db.query(Automation)
        .filter(
            Automation.organization_id
            == membership.organization_id,
            (Automation.store_id == store_id)
            | (Automation.store_id.is_(None)),
        )
        .order_by(Automation.updated_at.desc())
        .all()
    )

    items = []

    for a in automations:
        last_exec = (
            db.query(AutomationExecution)
            .filter(
                AutomationExecution.automation_id
                == a.id,
            )
            .order_by(
                AutomationExecution.id.desc()
            )
            .first()
        )

        items.append(
            {
                "id": a.id,
                "organization_id": (
                    a.organization_id
                ),
                "store_id": a.store_id,
                "name": a.name,
                "description": a.description,
                "active": a.active,
                "trigger_type": a.trigger_type,
                "conditions_json": json.loads(
                    a.conditions_json
                )
                if a.conditions_json
                else [],
                "actions_json": json.loads(
                    a.actions_json
                )
                if a.actions_json
                else [],
                "created_by": a.created_by,
                "created_at": (
                    a.created_at.isoformat()
                    + "Z"
                    if a.created_at
                    else None
                ),
                "updated_at": (
                    a.updated_at.isoformat()
                    + "Z"
                    if a.updated_at
                    else None
                ),
                "last_execution": (
                    {
                        "id": last_exec.id,
                        "status": (
                            last_exec.status
                        ),
                        "started_at": (
                            last_exec.started_at.isoformat()
                            + "Z"
                            if last_exec.started_at
                            else None
                        ),
                        "completed_at": (
                            last_exec.completed_at.isoformat()
                            + "Z"
                            if last_exec.completed_at
                            else None
                        ),
                    }
                    if last_exec
                    else None
                ),
            }
        )

    return {
        "items": items,
        "total": len(items),
    }


@router.post(
    "/api/stores/{store_id}/automations"
)
def create_automation(
    store_id: int,
    payload: AutomationCreate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    if (
        payload.trigger_type
        not in VALID_TRIGGER_TYPES
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid trigger_type",
        )

    existing = (
        db.query(Automation)
        .filter(
            Automation.organization_id
            == membership.organization_id,
            Automation.store_id == store_id,
            Automation.name == payload.name,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Automation with this name "
            "already exists in this store",
        )

    automation = Automation(
        organization_id=(
            membership.organization_id
        ),
        store_id=store_id,
        name=payload.name,
        description=payload.description,
        active=payload.active,
        trigger_type=payload.trigger_type,
        conditions_json=json.dumps(
            payload.conditions_json
        ),
        actions_json=json.dumps(
            payload.actions_json
        ),
        created_by=membership.user_id,
    )

    db.add(automation)
    db.commit()
    db.refresh(automation)

    return {
        "id": automation.id,
        "organization_id": (
            automation.organization_id
        ),
        "store_id": automation.store_id,
        "name": automation.name,
        "description": automation.description,
        "active": automation.active,
        "trigger_type": automation.trigger_type,
        "conditions_json": json.loads(
            automation.conditions_json
        ),
        "actions_json": json.loads(
            automation.actions_json
        ),
        "created_by": automation.created_by,
        "created_at": (
            automation.created_at.isoformat()
            + "Z"
            if automation.created_at
            else None
        ),
        "updated_at": (
            automation.updated_at.isoformat()
            + "Z"
            if automation.updated_at
            else None
        ),
    }


@router.get(
    "/api/stores/{store_id}"
    "/automations/{automation_id}"
)
def get_automation(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.read"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    return {
        "id": automation.id,
        "organization_id": (
            automation.organization_id
        ),
        "store_id": automation.store_id,
        "name": automation.name,
        "description": automation.description,
        "active": automation.active,
        "trigger_type": automation.trigger_type,
        "conditions_json": json.loads(
            automation.conditions_json
        ),
        "actions_json": json.loads(
            automation.actions_json
        ),
        "created_by": automation.created_by,
        "created_at": (
            automation.created_at.isoformat()
            + "Z"
            if automation.created_at
            else None
        ),
        "updated_at": (
            automation.updated_at.isoformat()
            + "Z"
            if automation.updated_at
            else None
        ),
    }


@router.put(
    "/api/stores/{store_id}"
    "/automations/{automation_id}"
)
def update_automation(
    store_id: int,
    automation_id: int,
    payload: AutomationUpdate,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    if (
        payload.trigger_type is not None
        and payload.trigger_type
        not in VALID_TRIGGER_TYPES
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid trigger_type",
        )

    if payload.name is not None:
        automation.name = payload.name

    if payload.description is not None:
        automation.description = (
            payload.description
        )

    if payload.store_id is not None:
        automation.store_id = (
            payload.store_id
        )

    if payload.active is not None:
        automation.active = payload.active

    if payload.trigger_type is not None:
        automation.trigger_type = (
            payload.trigger_type
        )

    if payload.conditions_json is not None:
        automation.conditions_json = json.dumps(
            payload.conditions_json
        )

    if payload.actions_json is not None:
        automation.actions_json = json.dumps(
            payload.actions_json
        )

    automation.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(automation)

    return {
        "id": automation.id,
        "organization_id": (
            automation.organization_id
        ),
        "store_id": automation.store_id,
        "name": automation.name,
        "description": automation.description,
        "active": automation.active,
        "trigger_type": automation.trigger_type,
        "conditions_json": json.loads(
            automation.conditions_json
        ),
        "actions_json": json.loads(
            automation.actions_json
        ),
        "created_by": automation.created_by,
        "created_at": (
            automation.created_at.isoformat()
            + "Z"
            if automation.created_at
            else None
        ),
        "updated_at": (
            automation.updated_at.isoformat()
            + "Z"
            if automation.updated_at
            else None
        ),
    }


@router.delete(
    "/api/stores/{store_id}"
    "/automations/{automation_id}"
)
def delete_automation(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    db.delete(automation)
    db.commit()

    return {"ok": True}


@router.post(
    "/api/stores/{store_id}"
    "/automations/{automation_id}/toggle"
)
def toggle_automation(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    automation.active = not automation.active
    automation.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(automation)

    return {
        "id": automation.id,
        "active": automation.active,
        "updated_at": (
            automation.updated_at.isoformat()
            + "Z"
            if automation.updated_at
            else None
        ),
    }


@router.post(
    "/api/stores/{store_id}"
    "/automations/{automation_id}/run"
)
def run_automation(
    store_id: int,
    automation_id: int,
    payload: AutomationRunRequest,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.write"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    execution = execute_automation(
        db=db,
        automation=automation,
        event_type=payload.event_type,
        payload=payload.payload,
    )

    return {
        "id": execution.id,
        "automation_id": (
            execution.automation_id
        ),
        "status": execution.status,
        "event_type": execution.event_type,
        "input_json": json.loads(
            execution.input_json
        ),
        "result_json": json.loads(
            execution.result_json
        ),
        "error_message": (
            execution.error_message
        ),
        "started_at": (
            execution.started_at.isoformat()
            + "Z"
            if execution.started_at
            else None
        ),
        "completed_at": (
            execution.completed_at.isoformat()
            + "Z"
            if execution.completed_at
            else None
        ),
    }


@router.get(
    "/api/stores/{store_id}"
    "/automations/{automation_id}"
    "/executions"
)
def list_automation_executions(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.read"
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

    automation = (
        db.query(Automation)
        .filter(
            Automation.id == automation_id,
            Automation.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not automation:
        raise HTTPException(
            status_code=404,
            detail="Automation not found",
        )

    executions = (
        db.query(AutomationExecution)
        .filter(
            AutomationExecution.automation_id
            == automation_id,
            AutomationExecution.organization_id
            == membership.organization_id,
        )
        .order_by(
            AutomationExecution.id.desc()
        )
        .all()
    )

    items = []

    for e in executions:
        items.append(
            {
                "id": e.id,
                "automation_id": (
                    e.automation_id
                ),
                "automation_name": (
                    automation.name
                ),
                "status": e.status,
                "event_type": e.event_type,
                "event_id": e.event_id,
                "input_json": json.loads(
                    e.input_json
                ),
                "result_json": json.loads(
                    e.result_json
                ),
                "error_message": (
                    e.error_message
                ),
                "started_at": (
                    e.started_at.isoformat()
                    + "Z"
                    if e.started_at
                    else None
                ),
                "completed_at": (
                    e.completed_at.isoformat()
                    + "Z"
                    if e.completed_at
                    else None
                ),
            }
        )

    return {
        "items": items,
        "total": len(items),
    }


@router.get(
    "/api/stores/{store_id}"
    "/automation-executions"
)
def list_all_automation_executions(
    store_id: int,
    membership: OrganizationMembership = Depends(
        require_permission(
            "automations.read"
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

    executions = (
        db.query(AutomationExecution)
        .filter(
            AutomationExecution.organization_id
            == membership.organization_id,
            AutomationExecution.store_id
            == store_id,
        )
        .order_by(
            AutomationExecution.id.desc()
        )
        .limit(100)
        .all()
    )

    items = []

    for e in executions:
        auto = (
            db.query(Automation)
            .filter(
                Automation.id
                == e.automation_id,
            )
            .first()
        )

        items.append(
            {
                "id": e.id,
                "automation_id": (
                    e.automation_id
                ),
                "automation_name": (
                    auto.name
                    if auto
                    else "Deleted"
                ),
                "status": e.status,
                "event_type": e.event_type,
                "event_id": e.event_id,
                "input_json": json.loads(
                    e.input_json
                ),
                "result_json": json.loads(
                    e.result_json
                ),
                "error_message": (
                    e.error_message
                ),
                "started_at": (
                    e.started_at.isoformat()
                    + "Z"
                    if e.started_at
                    else None
                ),
                "completed_at": (
                    e.completed_at.isoformat()
                    + "Z"
                    if e.completed_at
                    else None
                ),
            }
        )

    return {
        "items": items,
        "total": len(items),
    }


# ============================================================
# ROUTES — Analytics
# ============================================================


@router.get(
    "/api/stores/{store_id}"
    "/analytics/automations"
)
def get_analytics_automations(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(
        require_permission(
            "analytics.read"
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

    d_from, d_to = get_date_range(
        date_from, date_to
    )

    return get_automations_analytics(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )
