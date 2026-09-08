"""Automations HTTP router."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..analytics import get_automations_analytics, get_date_range
from ..db import get_db
from ..models import OrganizationMembership
from .deps import get_current_membership, require_permission
from ..services.automation_campaigns_service import (
    CampaignConflictError,
    CampaignNotFoundError,
    CampaignValidationError,
    RecipientRetryError,
    StoreNotFoundError,
    create_campaign,
    create_legacy_automation,
    delete_legacy_automation,
    duplicate_campaign,
    get_campaign,
    get_campaign_run,
    get_legacy_automation,
    get_run_recipient,
    list_campaign_runs,
    list_campaigns,
    list_legacy_automations,
    list_legacy_executions,
    list_all_legacy_executions,
    list_run_recipients,
    retry_run_recipient,
    run_legacy_automation,
    simulate_campaign_route,
    toggle_legacy_automation,
    update_campaign,
    update_legacy_automation,
)
from ..services.automation_flows_service import (
    FlowConflictError,
    FlowNotFoundError,
    FlowValidationError,
    activate_flow,
    archive_flow,
    create_flow,
    create_version,
    deactivate_flow,
    get_flow,
    get_flow_recipient_detail,
    get_flow_run,
    list_flow_run_recipients,
    list_flow_runs,
    list_flows,
    list_versions,
    publish_version,
    retry_flow_recipient,
    simulate_flow,
    trigger_flow_run,
    update_flow,
)

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
# ERROR MAPPING
# ============================================================


def _map_campaign_error(exc: Exception):
    if isinstance(exc, StoreNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, CampaignNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, CampaignConflictError):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, CampaignValidationError):
        raise HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RecipientRetryError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise exc


def _map_flow_error(exc: Exception):
    if isinstance(exc, FlowNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, FlowConflictError):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, FlowValidationError):
        raise HTTPException(status_code=422, detail={"errors": [str(exc)]})
    raise exc


# ============================================================
# ROUTES — Campaign audience + CRUD + runs + recipients
# ============================================================


@router.post("/api/stores/{store_id}/automation-campaigns/audience/preview")
def preview_automation_audience(
    store_id: int,
    payload: AudiencePreviewRequest,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    from ..automation_campaigns import audience_metrics, explain
    from ..services.automation_campaigns_service import _campaign_store_or_404, _fixed_audience_ids

    try:
        _campaign_store_or_404(db, membership.organization_id, store_id)
    except StoreNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

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
    from ..services.automation_campaigns_service import _campaign_store_or_404

    try:
        _campaign_store_or_404(db, membership.organization_id, store_id)
    except StoreNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

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
    try:
        return create_campaign(db, membership.organization_id, store_id, membership.user_id, payload.model_dump())
    except (StoreNotFoundError, CampaignNotFoundError, CampaignConflictError, CampaignValidationError) as exc:
        raise _map_campaign_error(exc)


@router.get("/api/stores/{store_id}/automation-campaigns")
def list_automation_campaigns(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    try:
        return list_campaigns(db, membership.organization_id, store_id)
    except StoreNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}")
def get_automation_campaign(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return get_campaign(db, membership.organization_id, store_id, campaign_id)
    except (StoreNotFoundError, CampaignNotFoundError) as exc:
        raise _map_campaign_error(exc)


@router.put("/api/stores/{store_id}/automation-campaigns/{campaign_id}")
def update_automation_campaign(campaign_id: int, store_id: int, payload: AutomationCampaignPayload, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return update_campaign(db, membership.organization_id, store_id, campaign_id, payload.model_dump())
    except (StoreNotFoundError, CampaignNotFoundError, CampaignConflictError, CampaignValidationError) as exc:
        raise _map_campaign_error(exc)


@router.post("/api/stores/{store_id}/automation-campaigns/{campaign_id}/simulate")
def simulate_automation_campaign(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return simulate_campaign_route(db, membership.organization_id, store_id, campaign_id)
    except (StoreNotFoundError, CampaignNotFoundError) as exc:
        raise _map_campaign_error(exc)


@router.post("/api/stores/{store_id}/automation-campaigns/{campaign_id}/duplicate")
def duplicate_automation_campaign(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return duplicate_campaign(db, membership.organization_id, store_id, campaign_id, membership.user_id)
    except (StoreNotFoundError, CampaignNotFoundError) as exc:
        raise _map_campaign_error(exc)


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs")
def list_automation_campaign_runs(campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return list_campaign_runs(db, membership.organization_id, store_id, campaign_id)
    except (StoreNotFoundError, CampaignNotFoundError) as exc:
        raise _map_campaign_error(exc)


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}")
def get_automation_run(run_id: int, campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return get_campaign_run(db, membership.organization_id, store_id, campaign_id, run_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}/recipients")
def list_run_recipients_route(run_id: int, campaign_id: int, store_id: int, status: str | None = None, reason: str | None = None, search: str | None = None, page: int = 1, page_size: int = 25, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return list_run_recipients(db, membership.organization_id, store_id, campaign_id, run_id, status, reason, search, page, page_size)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}/recipients/{recipient_id}")
def get_run_recipient_route(recipient_id: int, run_id: int, campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return get_run_recipient(db, membership.organization_id, store_id, campaign_id, run_id, recipient_id)
    except CampaignNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/stores/{store_id}/automation-campaigns/{campaign_id}/runs/{run_id}/recipients/{recipient_id}/retry")
def retry_run_recipient_route(recipient_id: int, run_id: int, campaign_id: int, store_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return retry_run_recipient(db, membership.organization_id, store_id, campaign_id, run_id, recipient_id)
    except (StoreNotFoundError, CampaignNotFoundError, RecipientRetryError) as exc:
        raise _map_campaign_error(exc)


# ============================================================
# ROUTES — Automation Flows V2.2
# ============================================================


@router.post("/api/stores/{store_id}/automation-flows")
def create_flow_route(store_id: int, payload: _FlowCreate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return create_flow(db, membership.organization_id, store_id, membership.user_id, payload.name, payload.description, payload.graph)
    except (FlowNotFoundError, FlowConflictError, FlowValidationError) as exc:
        raise _map_flow_error(exc)


@router.get("/api/stores/{store_id}/automation-flows")
def list_flows_route(store_id: int, status: str | None = None, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    return list_flows(db, membership.organization_id, store_id, status)


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}")
def get_flow_route(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return get_flow(db, membership.organization_id, store_id, flow_id)
    except FlowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/api/stores/{store_id}/automation-flows/{flow_id}")
def update_flow_route(store_id: int, flow_id: int, payload: _FlowUpdate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return update_flow(db, membership.organization_id, store_id, flow_id, payload.name, payload.description, payload.graph)
    except (FlowNotFoundError, FlowConflictError, FlowValidationError) as exc:
        raise _map_flow_error(exc)


@router.delete("/api/stores/{store_id}/automation-flows/{flow_id}")
def archive_flow_route(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return archive_flow(db, membership.organization_id, store_id, flow_id)
    except FlowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/versions")
def list_versions_route(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return list_versions(db, membership.organization_id, store_id, flow_id)
    except FlowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/versions")
def create_version_route(store_id: int, flow_id: int, payload: _FlowVersionPublish, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return create_version(db, membership.organization_id, store_id, flow_id, payload.graph)
    except (FlowNotFoundError, FlowValidationError) as exc:
        raise _map_flow_error(exc)


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/versions/{version_id}/publish")
def publish_version_route(store_id: int, flow_id: int, version_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return publish_version(db, membership.organization_id, store_id, flow_id, version_id)
    except (FlowNotFoundError, FlowConflictError) as exc:
        raise _map_flow_error(exc)


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/activate")
def activate_flow_route(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return activate_flow(db, membership.organization_id, store_id, flow_id)
    except (FlowNotFoundError, FlowConflictError) as exc:
        raise _map_flow_error(exc)


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/deactivate")
def deactivate_flow_route(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return deactivate_flow(db, membership.organization_id, store_id, flow_id)
    except FlowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/runs")
def trigger_flow_run_route(store_id: int, flow_id: int, payload: _FlowRunCreate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return trigger_flow_run(db, membership.organization_id, store_id, flow_id, payload.customer_ids, payload.trigger_key)
    except (FlowNotFoundError, FlowConflictError, FlowValidationError) as exc:
        raise _map_flow_error(exc)


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs")
def list_flow_runs_route(store_id: int, flow_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return list_flow_runs(db, membership.organization_id, store_id, flow_id)
    except FlowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}")
def get_flow_run_route(store_id: int, flow_id: int, run_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return get_flow_run(db, membership.organization_id, store_id, flow_id, run_id)
    except FlowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}/recipients")
def list_flow_run_recipients_route(store_id: int, flow_id: int, run_id: int, status: str | None = None, search: str | None = None, page: int = 1, size: int = 50, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return list_flow_run_recipients(db, membership.organization_id, store_id, flow_id, run_id, status, search, page, size)
    except FlowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}/recipients/{recipient_id}")
def get_flow_recipient_detail_route(store_id: int, flow_id: int, run_id: int, recipient_id: int, membership: OrganizationMembership = Depends(require_permission("automations.read")), db: Session = Depends(get_db)):
    try:
        return get_flow_recipient_detail(db, membership.organization_id, store_id, flow_id, run_id, recipient_id)
    except FlowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/stores/{store_id}/automation-flows/{flow_id}/runs/{run_id}/recipients/{recipient_id}/retry")
def retry_flow_recipient_route(store_id: int, flow_id: int, run_id: int, recipient_id: int, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return retry_flow_recipient(db, membership.organization_id, store_id, flow_id, run_id, recipient_id)
    except (FlowNotFoundError, FlowConflictError) as exc:
        raise _map_flow_error(exc)


@router.post("/api/stores/{store_id}/automation-flows/simulate")
def simulate_flow_route(store_id: int, payload: _FlowCreate, membership: OrganizationMembership = Depends(require_permission("automations.write")), db: Session = Depends(get_db)):
    try:
        return simulate_flow(db, membership.organization_id, store_id, payload.graph)
    except (FlowNotFoundError, FlowValidationError) as exc:
        raise _map_flow_error(exc)


# ============================================================
# ROUTES — Legacy Automations CRUD + Executions
# ============================================================


@router.get("/api/stores/{store_id}/automations")
def list_automations_route(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    try:
        return list_legacy_automations(db, membership.organization_id, store_id)
    except StoreNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/stores/{store_id}/automations")
def create_automation_route(
    store_id: int,
    payload: AutomationCreate,
    membership: OrganizationMembership = Depends(require_permission("automations.write")),
    db: Session = Depends(get_db),
):
    try:
        return create_legacy_automation(db, membership.organization_id, store_id, membership.user_id, payload.model_dump())
    except (StoreNotFoundError, CampaignValidationError, CampaignConflictError) as exc:
        raise _map_campaign_error(exc)


@router.get("/api/stores/{store_id}/automations/{automation_id}")
def get_automation_route(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    try:
        return get_legacy_automation(db, membership.organization_id, store_id, automation_id)
    except (StoreNotFoundError, CampaignNotFoundError) as exc:
        raise _map_campaign_error(exc)


@router.put("/api/stores/{store_id}/automations/{automation_id}")
def update_automation_route(
    store_id: int,
    automation_id: int,
    payload: AutomationUpdate,
    membership: OrganizationMembership = Depends(require_permission("automations.write")),
    db: Session = Depends(get_db),
):
    try:
        return update_legacy_automation(db, membership.organization_id, store_id, automation_id, payload.model_dump())
    except (StoreNotFoundError, CampaignNotFoundError, CampaignValidationError) as exc:
        raise _map_campaign_error(exc)


@router.delete("/api/stores/{store_id}/automations/{automation_id}")
def delete_automation_route(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.write")),
    db: Session = Depends(get_db),
):
    try:
        return delete_legacy_automation(db, membership.organization_id, store_id, automation_id)
    except (StoreNotFoundError, CampaignNotFoundError) as exc:
        raise _map_campaign_error(exc)


@router.post("/api/stores/{store_id}/automations/{automation_id}/toggle")
def toggle_automation_route(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.write")),
    db: Session = Depends(get_db),
):
    try:
        return toggle_legacy_automation(db, membership.organization_id, store_id, automation_id)
    except (StoreNotFoundError, CampaignNotFoundError) as exc:
        raise _map_campaign_error(exc)


@router.post("/api/stores/{store_id}/automations/{automation_id}/run")
def run_automation_route(
    store_id: int,
    automation_id: int,
    payload: AutomationRunRequest,
    membership: OrganizationMembership = Depends(require_permission("automations.write")),
    db: Session = Depends(get_db),
):
    try:
        return run_legacy_automation(db, membership.organization_id, store_id, automation_id, payload.event_type, payload.payload)
    except (StoreNotFoundError, CampaignNotFoundError) as exc:
        raise _map_campaign_error(exc)


@router.get("/api/stores/{store_id}/automations/{automation_id}/executions")
def list_automation_executions_route(
    store_id: int,
    automation_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    try:
        return list_legacy_executions(db, membership.organization_id, store_id, automation_id)
    except (StoreNotFoundError, CampaignNotFoundError) as exc:
        raise _map_campaign_error(exc)


@router.get("/api/stores/{store_id}/automation-executions")
def list_all_automation_executions_route(
    store_id: int,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    try:
        return list_all_legacy_executions(db, membership.organization_id, store_id)
    except StoreNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ============================================================
# ROUTES — Analytics
# ============================================================


@router.get("/api/stores/{store_id}/analytics/automations")
def get_analytics_automations(
    store_id: int,
    date_from: str | None = None,
    date_to: str | None = None,
    membership: OrganizationMembership = Depends(require_permission("analytics.read")),
    db: Session = Depends(get_db),
):
    from ..models import Store

    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == membership.organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")

    d_from, d_to = get_date_range(date_from, date_to)
    return get_automations_analytics(
        db=db,
        organization_id=membership.organization_id,
        store_id=store_id,
        date_from=d_from,
        date_to=d_to,
    )


# ============================================================
# ROUTES — Automation Templates
# ============================================================


@router.get("/api/stores/{store_id}/automation-templates")
def list_automation_templates(
    store_id: int,
    category: str | None = None,
    membership: OrganizationMembership = Depends(require_permission("automations.read")),
    db: Session = Depends(get_db),
):
    from ..automation_templates import (
        get_all_templates,
        get_categories,
        get_templates_by_category,
        validate_template_availability,
    )
    from ..models import WhatsAppConnection, CommerceConnection

    # Determine connected integrations
    connected = set()

    whatsapp = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id == store_id,
            WhatsAppConnection.organization_id == membership.organization_id,
            WhatsAppConnection.status == "connected",
        )
        .first()
    )
    if whatsapp:
        connected.add("whatsapp")

    commerce = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id == store_id,
            CommerceConnection.organization_id == membership.organization_id,
            CommerceConnection.status == "connected",
        )
        .first()
    )
    if commerce:
        connected.add("shopify")

    if category:
        templates = get_templates_by_category(category)
    else:
        templates = get_all_templates()

    # Add availability info to each template
    for tmpl in templates:
        avail = validate_template_availability(tmpl["id"], connected)
        tmpl["availability"] = avail

    return {
        "items": templates,
        "total": len(templates),
        "categories": get_categories(),
    }


class AutomationFromTemplateRequest(BaseModel):
    template_id: str


@router.post("/api/stores/{store_id}/automation-templates")
def create_automation_from_template(
    store_id: int,
    payload: AutomationFromTemplateRequest,
    membership: OrganizationMembership = Depends(require_permission("automations.write")),
    db: Session = Depends(get_db),
):
    from ..automation_templates import (
        template_to_automation_data,
        validate_template_availability,
    )
    from ..models import WhatsAppConnection, CommerceConnection
    from ..services.product_analytics import track_first_automation_created

    # Determine connected integrations
    connected = set()

    whatsapp = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.store_id == store_id,
            WhatsAppConnection.organization_id == membership.organization_id,
            WhatsAppConnection.status == "connected",
        )
        .first()
    )
    if whatsapp:
        connected.add("whatsapp")

    commerce = (
        db.query(CommerceConnection)
        .filter(
            CommerceConnection.store_id == store_id,
            CommerceConnection.organization_id == membership.organization_id,
            CommerceConnection.status == "connected",
        )
        .first()
    )
    if commerce:
        connected.add("shopify")

    # Validate template availability
    avail = validate_template_availability(payload.template_id, connected)
    if not avail["available"]:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "TEMPLATE_INTEGRATION_REQUIRED",
                "message": f"Missing integrations: {', '.join(avail['missing'])}",
                "missing": avail["missing"],
            },
        )

    # Get automation data from template
    auto_data = template_to_automation_data(payload.template_id, store_id)
    if auto_data is None:
        raise HTTPException(status_code=404, detail="Template not found")

    # Create automation
    try:
        result = create_legacy_automation(
            db,
            membership.organization_id,
            store_id,
            membership.user_id,
            auto_data,
        )
    except CampaignConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (CampaignValidationError, StoreNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Analytics: template created
    from ..services.product_analytics import capture
    capture(
        "automation_template_created",
        distinct_id=str(membership.user_id),
        properties={
            "organization_id": membership.organization_id,
            "store_id": store_id,
            "template_id": payload.template_id,
            "template_version": auto_data.get("template_version", 1),
        },
    )

    return result
