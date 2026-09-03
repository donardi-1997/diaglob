"""Durable execution engine for V2.2 Flow Builder."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from .automation_flow_graph import get_next_node, get_entry_node
from .automation_execution_engine import (
    BACKOFF_SECONDS, BATCH_SIZE, LEASE_SECONDS, MAX_ATTEMPTS, MAX_PER_MINUTE,
    _acquire_rate_slot, utcnow,
)
from .automation_campaigns import render_template
from .models import (
    AutomationFlow, AutomationFlowVersion, AutomationFlowRun,
    AutomationFlowRecipientExecution, AutomationNodeExecution,
    AutomationDeliveryAttempt, AutomationRateLimit,
    Customer, Store, WhatsAppConnection,
)
from .whatsapp_client import WhatsAppDeliveryError, send_whatsapp_template_message, send_whatsapp_text_message
from .whatsapp_compliance import evaluate_whatsapp_delivery_eligibility, get_last_whatsapp_inbound_by_customer
from .whatsapp_security import decrypt_whatsapp_secret

logger = logging.getLogger(__name__)

FLOW_POLL_BATCH = int(os.getenv("AUTOMATION_FLOW_BATCH_SIZE", str(BATCH_SIZE)))


# ============================================================
# MATERIALIZE
# ============================================================


def materialize_flow_trigger(db: Session, flow: AutomationFlow, customer_ids: list[int], trigger_key: str | None = None, now: datetime | None = None) -> AutomationFlowRun | None:
    """Create a flow run and recipient executions for a manual/audience trigger."""
    now = now or utcnow()
    if flow.status != "active" or not flow.active_version_id:
        return None
    version = db.get(AutomationFlowVersion, flow.active_version_id)
    if not version:
        return None
    graph = version.graph
    entry = get_entry_node(graph)
    if not entry:
        return None
    if trigger_key:
        existing = db.query(AutomationFlowRun).filter(
            AutomationFlowRun.flow_id == flow.id,
            AutomationFlowRun.trigger_key == trigger_key,
        ).first()
        if existing:
            return None
    run = AutomationFlowRun(
        flow_id=flow.id, flow_version_id=version.id,
        organization_id=flow.organization_id, store_id=flow.store_id,
        status="pending", trigger_key=trigger_key,
        total_recipients=len(customer_ids), started_at=now,
    )
    db.add(run)
    db.flush()
    entry_after_trigger = get_next_node(graph, entry["id"])
    first_node_id = entry_after_trigger["id"] if entry_after_trigger else entry["id"]
    for cid in customer_ids:
        existing_recip = db.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.flow_run_id == run.id,
            AutomationFlowRecipientExecution.customer_id == cid,
        ).first()
        if existing_recip:
            continue
        recipient = AutomationFlowRecipientExecution(
            flow_run_id=run.id, flow_version_id=version.id,
            customer_id=cid, organization_id=flow.organization_id,
            status="active", current_node_id=first_node_id,
            next_action_at=now, started_at=now,
        )
        db.add(recipient)
    db.commit()
    return run


# ============================================================
# CLAIM
# ============================================================


def claim_flow_recipients(db: Session, now: datetime | None = None, limit: int = FLOW_POLL_BATCH) -> list[int]:
    """Claim due flow recipient executions with FOR UPDATE SKIP LOCKED."""
    now = now or utcnow()
    query = db.query(AutomationFlowRecipientExecution.id).join(
        AutomationFlowRun
    ).filter(
        AutomationFlowRecipientExecution.status.in_(("active", "waiting")),
        AutomationFlowRecipientExecution.next_action_at <= now,
        AutomationFlowRecipientExecution.claim_expires_at.is_(None),
        AutomationFlowRun.status.in_(("pending", "running")),
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    ids = [row[0] for row in query.order_by(AutomationFlowRecipientExecution.id).limit(limit).all()]
    if ids:
        db.query(AutomationFlowRecipientExecution).filter(
            AutomationFlowRecipientExecution.id.in_(ids),
        ).update({
            "claim_token": str(uuid.uuid4()),
            "claim_expires_at": now + timedelta(seconds=LEASE_SECONDS),
        }, synchronize_session=False)
        db.query(AutomationFlowRun).filter(
            AutomationFlowRun.id.in_(
                db.query(AutomationFlowRun.id).join(AutomationFlowRecipientExecution).filter(
                    AutomationFlowRecipientExecution.id.in_(ids)
                )
            ),
            AutomationFlowRun.status == "pending",
        ).update({"status": "running"}, synchronize_session=False)
    db.commit()
    return ids


def reclaim_expired_flow_leases(db: Session, now: datetime | None = None) -> None:
    """Reclaim expired flow recipient leases."""
    now = now or utcnow()
    db.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.status == "waiting",
        AutomationFlowRecipientExecution.claim_expires_at < now,
    ).update({
        "status": "active",
        "claim_token": None,
        "claim_expires_at": None,
    }, synchronize_session=False)
    db.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.status == "processing",
        AutomationFlowRecipientExecution.claim_expires_at < now,
    ).update({
        "status": "waiting",
        "claim_token": None,
        "claim_expires_at": None,
        "error_code": "lease_expired",
        "error_message": "Worker stopped during processing",
    }, synchronize_session=False)
    db.commit()


# ============================================================
# PROCESS
# ============================================================


def process_flow_recipient(db: Session, recipient_id: int, now: datetime | None = None, sender=send_whatsapp_text_message) -> str:
    """Process a single flow recipient at its current node."""
    now = now or utcnow()
    recipient = db.get(AutomationFlowRecipientExecution, recipient_id)
    if not recipient or recipient.status not in ("active", "waiting"):
        return "not_claimed"
    if recipient.claim_expires_at and recipient.claim_expires_at < now:
        return "claim_expired"
    version = db.get(AutomationFlowVersion, recipient.flow_version_id)
    if not version:
        _finish_flow_recipient(db, recipient, "failed", now, code="version_missing", message="Flow version not found")
        return "failed"
    graph = version.graph
    node = None
    for n in graph.get("nodes", []):
        if n.get("id") == recipient.current_node_id:
            node = n
            break
    if not node:
        _finish_flow_recipient(db, recipient, "failed", now, code="node_missing", message="Current node not found")
        return "failed"
    node_type = node.get("type")
    config = node.get("config", {})
    run = db.get(AutomationFlowRun, recipient.flow_run_id)
    if run.status not in ("pending", "running"):
        return "run_not_active"
    if node_type == "end":
        _finish_flow_recipient(db, recipient, "completed", now)
        return "completed"
    if node_type == "wait":
        return _process_wait_node(db, recipient, node, now)
    if node_type == "condition":
        return _process_condition_node(db, recipient, node, graph, now)
    if node_type == "message":
        return _process_message_node(db, recipient, node, run, now, sender)
    _advance_flow(db, recipient, graph, node["id"], now)
    return "advanced"


def _process_wait_node(db: Session, recipient: AutomationFlowRecipientExecution, node: dict, now: datetime) -> str:
    config = node.get("config", {})
    unit = config.get("unit", "hours")
    value = config.get("value", 1)
    if unit == "minutes":
        delta = timedelta(minutes=value)
    elif unit == "hours":
        delta = timedelta(hours=value)
    elif unit == "days":
        delta = timedelta(days=value)
    else:
        delta = timedelta(hours=value)
    recipient.status = "waiting"
    recipient.next_action_at = now + delta
    recipient.claim_token = None
    recipient.claim_expires_at = None
    _record_node_execution(db, recipient, node["id"], "wait", "completed", now)
    db.commit()
    return "waiting"


def _process_condition_node(db: Session, recipient: AutomationFlowRecipientExecution, node: dict, graph: dict, now: datetime) -> str:
    config = node.get("config", {})
    field = config.get("field", "")
    operator = config.get("operator", "")
    value = config.get("value")
    customer = db.get(Customer, recipient.customer_id)
    if not customer:
        _finish_flow_recipient(db, recipient, "failed", now, code="customer_missing", message="Customer not found")
        return "failed"
    customer_data = {
        "customer.segment": getattr(customer, "primary_segment", None),
        "customer.health": getattr(customer, "customer_health", None),
        "customer.priority": getattr(customer, "priority", None),
        "customer.needs_attention": getattr(customer, "needs_attention", False),
        "customer.needs_followup": getattr(customer, "needs_followup", False),
        "customer.order_count": getattr(customer, "orders_count", 0),
        "customer.country": getattr(customer, "country_code", None),
        "has_successful_order_since_flow_start": False,
    }
    actual = customer_data.get(field)
    result = _evaluate_condition(actual, operator, value)
    branch = "true" if result else "false"
    _record_node_execution(db, recipient, node["id"], "condition", "completed", now, outcome=branch)
    _advance_flow(db, recipient, graph, node["id"], now, outcome=branch)
    return "advanced"


def _process_message_node(db: Session, recipient: AutomationFlowRecipientExecution, node: dict, run: AutomationFlowRun, now: datetime, sender) -> str:
    config = node.get("config", {})
    customer = db.get(Customer, recipient.customer_id)
    store = db.get(Store, run.store_id)
    if not customer or not customer.phone:
        _finish_flow_recipient(db, recipient, "failed", now, code="no_phone", message="Customer phone unavailable")
        return "failed"
    connection = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.store_id == run.store_id,
        WhatsAppConnection.organization_id == run.organization_id,
        WhatsAppConnection.status == "connected",
    ).first()
    if not connection:
        recipient.status = "active"
        recipient.next_action_at = now + timedelta(minutes=5)
        recipient.claim_token = None
        recipient.claim_expires_at = None
        db.commit()
        return "retry_wait"
    message_mode = config.get("message_mode", "free_form")
    message_template = config.get("message_template", "")
    rendered = render_template(message_template, {
        "name": customer.name, "phone": customer.phone,
        "primary_segment": getattr(customer, "primary_segment", None),
        "customer_health": getattr(customer, "customer_health", None),
    }, store) if message_template else None
    compliance = evaluate_whatsapp_delivery_eligibility(
        db, _make_flow_campaign_proxy(config, run), connection, customer.id, now,
    )
    if not compliance["allowed"]:
        _record_node_execution(db, recipient, node["id"], "message", "skipped", now,
                               outcome=compliance["reason"], error_code=compliance["reason"])
        _advance_flow(db, recipient, config.get("_graph", {}), node["id"], now)
        return "skipped"
    if not _acquire_rate_slot(db, connection.id, now):
        recipient.status = "active"
        recipient.next_action_at = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        recipient.claim_token = None
        recipient.claim_expires_at = None
        db.commit()
        return "rate_limited"
    recipient.status = "processing"
    recipient.attempt_count += 1
    node_exec = _record_node_execution(db, recipient, node["id"], "message", "sending", now)
    db.commit()
    token = decrypt_whatsapp_secret(connection.access_token_encrypted)
    try:
        if compliance["mode"] == "template":
            from .whatsapp_compliance import template_components
            template = compliance["template"]
            components = template_components(template, config.get("template_variables", {}), {
                "customer.name": customer.name, "store.name": store.name,
                "customer.segment": getattr(customer, "primary_segment", None),
                "customer.health": getattr(customer, "customer_health", None),
            })
            result = send_whatsapp_template_message(connection.phone_number_id, token, customer.phone, template.provider_template_name, template.language_code, components)
        else:
            result = sender(connection.phone_number_id, token, customer.phone, rendered or "")
    except WhatsAppDeliveryError as exc:
        recipient = db.get(AutomationFlowRecipientExecution, recipient.id)
        if exc.category == "ambiguous":
            _finish_node_attempt(db, node_exec, "ambiguous", now, code=exc.code, message=str(exc))
            _finish_flow_recipient(db, recipient, "ambiguous", now, code=exc.code, message=str(exc))
            return "ambiguous"
        if exc.category == "transient" and recipient.attempt_count < MAX_ATTEMPTS:
            backoff = BACKOFF_SECONDS[min(recipient.attempt_count - 1, len(BACKOFF_SECONDS) - 1)]
            recipient.status = "active"
            recipient.next_action_at = now + timedelta(seconds=backoff)
            recipient.claim_token = None
            recipient.claim_expires_at = None
            _finish_node_attempt(db, node_exec, "retry_wait", now, code=exc.code, message=str(exc))
            db.commit()
            return "retry_wait"
        _finish_node_attempt(db, node_exec, "failed", now, code=exc.code, message=str(exc))
        _finish_flow_recipient(db, recipient, "failed", now, code=exc.code, message=str(exc))
        return "failed"
    except ValueError:
        recipient = db.get(AutomationFlowRecipientExecution, recipient.id)
        _finish_node_attempt(db, node_exec, "skipped", now, code="invalid_template_data", message="Template variables unavailable")
        _advance_flow(db, recipient, _get_graph_from_version(db, recipient.flow_version_id), node["id"], now)
        return "skipped"
    recipient = db.get(AutomationFlowRecipientExecution, recipient.id)
    _finish_node_attempt(db, node_exec, "completed", now, provider_id=result.get("message_id"))
    _advance_flow(db, recipient, _get_graph_from_version(db, recipient.flow_version_id), node["id"], now)
    return "sent"


def _evaluate_condition(actual, operator: str, expected) -> bool:
    if operator == "equals":
        return actual == expected
    if operator == "not_equals":
        return actual != expected
    if operator == "greater_than":
        return (actual or 0) > (expected or 0)
    if operator == "greater_or_equal":
        return (actual or 0) >= (expected or 0)
    if operator == "less_than":
        return (actual or 0) < (expected or 0)
    if operator == "less_or_equal":
        return (actual or 0) <= (expected or 0)
    if operator == "in":
        return actual in (expected or [])
    if operator == "not_in":
        return actual not in (expected or [])
    if operator == "is_true":
        return bool(actual)
    if operator == "is_false":
        return not bool(actual)
    return False


def _make_flow_campaign_proxy(config: dict, run: AutomationFlowRun):
    class _Proxy:
        pass
    p = _Proxy()
    p.store_id = run.store_id
    p.organization_id = run.organization_id
    p.message_mode = config.get("message_mode", "free_form")
    p.whatsapp_template_id = config.get("whatsapp_template_id")
    p.template_variables = config.get("template_variables", {})
    p.cooldown_days = 0
    return p


def _advance_flow(db: Session, recipient: AutomationFlowRecipientExecution, graph: dict, current_node_id: str, now: datetime, outcome: str | None = None) -> None:
    nxt = get_next_node(graph, current_node_id, outcome)
    if not nxt:
        _finish_flow_recipient(db, recipient, "completed", now)
        return
    recipient.current_node_id = nxt["id"]
    if nxt["type"] == "wait":
        pass
    else:
        recipient.next_action_at = now
    recipient.status = "active"
    recipient.claim_token = None
    recipient.claim_expires_at = None
    db.commit()


def _get_graph_from_version(db: Session, version_id: int) -> dict:
    v = db.get(AutomationFlowVersion, version_id)
    return v.graph if v else {}


def _finish_flow_recipient(db: Session, recipient: AutomationFlowRecipientExecution, status: str, now: datetime, *, code: str | None = None, message: str | None = None) -> None:
    recipient.status = status
    recipient.error_code = code
    recipient.error_message = message
    recipient.completed_at = now
    recipient.claim_token = None
    recipient.claim_expires_at = None
    run = db.get(AutomationFlowRun, recipient.flow_run_id)
    if status == "completed":
        run.completed_recipients += 1
    elif status in ("failed", "ambiguous"):
        run.failed_recipients += 1
    if run.total_recipients <= run.completed_recipients + run.failed_recipients:
        run.status = "completed" if run.failed_recipients == 0 else "partial"
        run.completed_at = now
    db.commit()


def _record_node_execution(db: Session, recipient: AutomationFlowRecipientExecution, node_id: str, node_type: str, status: str, now: datetime, *, outcome: str | None = None, error_code: str | None = None, message: str | None = None, provider_id: str | None = None) -> AutomationNodeExecution:
    ne = AutomationNodeExecution(
        flow_recipient_execution_id=recipient.id,
        node_id=node_id, node_type=node_type, status=status,
        started_at=now, outcome=outcome,
        error_code=error_code, error_message=message,
        provider_message_id=provider_id,
    )
    db.add(ne)
    db.flush()
    return ne


def _finish_node_attempt(db: Session, ne: AutomationNodeExecution, status: str, now: datetime, *, code: str | None = None, message: str | None = None, provider_id: str | None = None) -> None:
    ne.status = status
    ne.error_code = code
    ne.error_message = message
    ne.provider_message_id = provider_id or ne.provider_message_id
    ne.completed_at = now
    ne.attempt_count += 1
    db.commit()


# ============================================================
# AGGREGATE
# ============================================================


def aggregate_flow_runs(db: Session, now: datetime | None = None) -> None:
    now = now or utcnow()
    for run in db.query(AutomationFlowRun).filter(AutomationFlowRun.status.in_(("pending", "running"))).all():
        total = run.total_recipients
        if total == 0:
            run.status = "completed"
            run.completed_at = now
            continue
        if run.completed_recipients + run.failed_recipients < total:
            continue
        run.status = "completed" if run.failed_recipients == 0 else "partial"
        run.completed_at = now
    db.commit()
