"""Audience, schedule, template and dry-run support for Automations V2.1."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .customers.intelligence import get_customer_metrics
from .models import AutomationAudienceMember, AutomationCampaign, AutomationRecipientExecution, AutomationRun, Customer, Store, WhatsAppConnection
from .services.customer_classification_service import CLASSIFICATIONS, VALUE_TIERS, enrich_customer_metrics
from .whatsapp_compliance import evaluate_whatsapp_delivery_eligibility, get_last_whatsapp_inbound_by_customer

AUTOMATION_TYPES = {"recovery", "high_intent_followup", "inactive_reactivation", "vip_reactivation", "failed_order_recovery", "post_purchase_followup", "custom"}
STATUSES = {"draft", "active", "paused", "archived"}
SCHEDULE_TYPES = {"once", "daily", "weekly", "every_n_days"}
VARIABLES = {
    "customer.name",
    "store.name",
    "customer.segment",
    "customer.health",
    "customer.classification",
    "customer.value_tier",
}
FILTER_ENUMS = {
    "segment": {"new", "interested", "high_intent", "buyer", "repeat_buyer", "vip", "inactive"},
    "priority": {"high", "medium", "low"},
    "health": {"active", "at_risk", "inactive"},
    "flag": {"at_risk"},
    "classification": set(CLASSIFICATIONS),
    "value_tier": set(VALUE_TIERS),
}
_VARIABLE_RE = re.compile(r"{{\s*([\w.]+)\s*}}")


def validate_template(template: str) -> None:
    if not template.strip():
        raise HTTPException(400, "Message template is required")
    unknown = set(_VARIABLE_RE.findall(template)) - VARIABLES
    if unknown:
        raise HTTPException(400, "Unknown message variable")


def validate_campaign(data: dict[str, Any], store: Store) -> None:
    if data.get("automation_type", "custom") not in AUTOMATION_TYPES:
        raise HTTPException(400, "Invalid automation_type")
    if data.get("status", "draft") not in STATUSES:
        raise HTTPException(400, "Invalid status")
    if data.get("audience_type", "dynamic") not in {"dynamic", "fixed"}:
        raise HTTPException(400, "Invalid audience_type")
    if data.get("schedule_type", "once") not in SCHEDULE_TYPES:
        raise HTTPException(400, "Invalid schedule_type")
    if data.get("channel", "whatsapp") != "whatsapp":
        raise HTTPException(400, "Unsupported channel")
    timezone = data.get("timezone") or store.timezone
    try:
        ZoneInfo(timezone)
    except Exception as exc:
        raise HTTPException(400, "Invalid timezone") from exc
    for field, allowed in FILTER_ENUMS.items():
        values = data.get("audience_filters", {}).get(field, [])
        if values and (not isinstance(values, list) or not set(values).issubset(allowed)):
            raise HTTPException(400, f"Invalid audience filter: {field}")
    for field in ("send_window_start", "send_window_end"):
        value = data.get(field)
        if value and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise HTTPException(400, "Invalid send window")
    if data.get("send_window_start") and data.get("send_window_end") and data["send_window_start"] >= data["send_window_end"]:
        raise HTTPException(400, "Invalid send window")
    if int(data.get("cooldown_days", 0)) < 0:
        raise HTTPException(400, "Invalid cooldown")
    config = data.get("schedule_config", {})
    if data.get("schedule_type") == "once" and not config.get("starts_at"):
        raise HTTPException(400, "One-time schedule requires starts_at")
    if data.get("schedule_type") == "weekly" and not config.get("days_of_week"):
        raise HTTPException(400, "Weekly schedule requires days_of_week")
    if data.get("schedule_type") == "every_n_days" and int(config.get("interval_days", 0)) < 1:
        raise HTTPException(400, "Every-n-days schedule requires interval_days")
    validate_template(data.get("message_template", ""))


def audience_metrics(db: Session, org_id: int, store_id: int, audience_type: str, filters: dict[str, Any], member_ids: list[int] | None = None) -> list[dict[str, Any]]:
    metrics = get_customer_metrics(db, org_id, store_id)
    metrics = enrich_customer_metrics(db, org_id, store_id, metrics)
    if audience_type == "fixed":
        wanted = set(member_ids or [])
        return [item for item in metrics if item["id"] in wanted]
    for key, metric_key in (
        ("segment", "primary_segment"),
        ("priority", "priority"),
        ("health", "customer_health"),
        ("classification", "commercial_classification"),
        ("value_tier", "value_tier"),
    ):
        values = filters.get(key, [])
        if values:
            metrics = [item for item in metrics if item.get(metric_key) in values]
    flags = filters.get("flag", [])
    if flags:
        metrics = [item for item in metrics if set(flags).intersection(item.get("flags", []))]
    for key in ("needs_attention", "needs_followup"):
        if key in filters:
            metrics = [item for item in metrics if item.get(key) == filters[key]]
    countries = filters.get("country_codes", [])
    if countries:
        metrics = [item for item in metrics if item.get("country_code") in countries]
    if "has_orders" in filters:
        metrics = [item for item in metrics if (item.get("successful_order_count", 0) > 0) == filters["has_orders"]]
    search = str(filters.get("search", "")).strip().lower()
    if search:
        metrics = [item for item in metrics if search in (item.get("name") or "").lower() or search in (item.get("phone") or "").lower() or search in (item.get("email") or "").lower()]
    if filters.get("min_orders") is not None:
        metrics = [item for item in metrics if item.get("successful_order_count", 0) >= int(filters["min_orders"])]
    if filters.get("max_orders") is not None:
        metrics = [item for item in metrics if item.get("successful_order_count", 0) <= int(filters["max_orders"])]
    excluded = set(filters.get("exclude_customer_ids", []))
    return [item for item in metrics if item["id"] not in excluded]


def render_template(template: str, customer: dict[str, Any], store: Store) -> str | None:
    values = {
        "customer.name": customer.get("name"),
        "store.name": store.name,
        "customer.segment": customer.get("primary_segment"),
        "customer.health": customer.get("customer_health"),
        "customer.classification": customer.get("commercial_classification"),
        "customer.value_tier": customer.get("value_tier"),
    }
    if any(values[key] is None or values[key] == "" for key in _VARIABLE_RE.findall(template)):
        return None
    return _VARIABLE_RE.sub(lambda match: str(values[match.group(1)]), template)


def simulate_campaign(db: Session, campaign: AutomationCampaign, store: Store, persist: bool = True) -> dict[str, Any]:
    members = [member.customer_id for member in campaign.members if member.included]
    metrics = audience_metrics(db, campaign.organization_id, campaign.store_id, campaign.audience_type, json_load(campaign.audience_filters), members)
    cutoff = datetime.utcnow() - timedelta(days=campaign.cooldown_days)
    already_sent = set()
    if campaign.cooldown_days:
        rows = db.query(AutomationRecipientExecution.customer_id).join(AutomationRun).filter(AutomationRun.automation_id == campaign.id, AutomationRecipientExecution.status == "sent", AutomationRecipientExecution.sent_at >= cutoff).all()
        already_sent = {row[0] for row in rows}
    results, breakdown = [], {}
    connection = db.query(WhatsAppConnection).filter(WhatsAppConnection.organization_id == campaign.organization_id, WhatsAppConnection.store_id == campaign.store_id, WhatsAppConnection.status == "connected").first()
    inbound_by_customer = get_last_whatsapp_inbound_by_customer(db, campaign.organization_id, campaign.store_id, [customer["id"] for customer in metrics])
    for customer in metrics:
        reason = None
        message = None
        if not customer.get("phone"):
            reason = "no_phone"
        elif customer["id"] in already_sent:
            reason = "cooldown"
        else:
            message = render_template(campaign.message_template, customer, store)
            if message is None:
                reason = "invalid_template_data"
            elif connection:
                compliance = evaluate_whatsapp_delivery_eligibility(db, campaign, connection, customer["id"], last_inbound_at=inbound_by_customer.get(customer["id"]), inbound_known=True)
                if not compliance["allowed"]:
                    reason = compliance["reason"]
            else:
                reason = "connection_inactive"
        status = "excluded" if reason else "eligible"
        if reason:
            breakdown[reason] = breakdown.get(reason, 0) + 1
        results.append((customer, status, reason, message))
    payload = {"matched": len(metrics), "eligible": sum(1 for _, status, _, _ in results if status == "eligible"), "excluded": sum(1 for _, status, _, _ in results if status == "excluded"), "would_send": sum(1 for _, status, _, _ in results if status == "eligible"), "exclusion_breakdown": breakdown, "sample": [explain(customer) | {"eligibility": status, "exclusion_reason": reason, "message_preview": message} for customer, status, reason, message in results[:20]]}
    if persist:
        run = AutomationRun(automation_id=campaign.id, organization_id=campaign.organization_id, status="simulated", run_key=f"simulation:{datetime.utcnow().isoformat()}", matched_count=payload["matched"], eligible_count=payload["eligible"], excluded_count=payload["excluded"], completed_at=datetime.utcnow())
        db.add(run); db.flush()
        for customer, status, reason, message in results:
            db.add(AutomationRecipientExecution(run_id=run.id, customer_id=customer["id"], status=status, exclusion_reason=reason, rendered_message=message))
        db.commit(); payload["run_id"] = run.id
    return payload


def explain(customer: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "name",
        "phone",
        "country_code",
        "primary_segment",
        "priority",
        "customer_health",
        "flags",
        "customer_score",
        "needs_attention",
        "needs_followup",
        "successful_order_count",
        "last_interaction_at",
        "commercial_classification",
        "value_tier",
        "rfm_recency_days",
        "rfm_frequency",
        "rfm_monetary_value",
        "rfm_score",
    )
    return {key: customer.get(key) for key in fields}


def json_load(value: str | dict[str, Any]) -> dict[str, Any]:
    import json
    if isinstance(value, dict):
        return value
    return json.loads(value or "{}")