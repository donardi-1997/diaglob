"""Map Meta delivery callbacks to campaigns and flow message nodes."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..model_domains.whatsapp_delivery import WhatsAppAutomationDelivery
from ..models import AutomationRecipientExecution

_RANK = {"sent": 1, "delivered": 2, "read": 3, "failed": 4}


def record_campaign_delivery(db: Session, *, organization_id: int, store_id: int, recipient_id: int, provider_message_id: str, sent_at: datetime) -> None:
    _record(db, organization_id, store_id, provider_message_id, sent_at, campaign_recipient_execution_id=recipient_id)


def record_flow_delivery(db: Session, *, organization_id: int, store_id: int, node_execution_id: int, provider_message_id: str, sent_at: datetime) -> None:
    _record(db, organization_id, store_id, provider_message_id, sent_at, flow_node_execution_id=node_execution_id)


def _record(db: Session, organization_id: int, store_id: int, provider_message_id: str, sent_at: datetime, **target: int) -> None:
    if not provider_message_id:
        return
    existing = db.query(WhatsAppAutomationDelivery).filter_by(
        organization_id=organization_id, store_id=store_id, provider_message_id=provider_message_id,
    ).first()
    if existing is None:
        db.add(WhatsAppAutomationDelivery(
            organization_id=organization_id, store_id=store_id,
            provider_message_id=provider_message_id, sent_at=sent_at, **target,
        ))


def apply_delivery_status(db: Session, *, organization_id: int, store_id: int, provider_message_id: str, status: str, error_code: str | None, now: datetime) -> bool:
    """Apply only forward Meta statuses. A later delivered never regresses read."""
    row = db.query(WhatsAppAutomationDelivery).filter_by(
        organization_id=organization_id, store_id=store_id, provider_message_id=provider_message_id,
    ).first()
    if row is None or status not in _RANK or _RANK[status] < _RANK.get(row.status, 0):
        return False
    # Failed is terminal; duplicate callbacks can enrich only the error code.
    if row.status == "failed" and status != "failed":
        return False
    row.status = status
    row.updated_at = now
    if status == "delivered": row.delivered_at = row.delivered_at or now
    elif status == "read":
        row.delivered_at = row.delivered_at or now
        row.read_at = row.read_at or now
    elif status == "failed":
        row.failed_at = row.failed_at or now
        row.error_code = error_code
    return True


def campaign_delivery_metrics(db: Session, run_id: int) -> dict:
    rows = db.query(WhatsAppAutomationDelivery.status, func.count(WhatsAppAutomationDelivery.id)).join(
        AutomationRecipientExecution,
        WhatsAppAutomationDelivery.campaign_recipient_execution_id == AutomationRecipientExecution.id,
    ).filter(AutomationRecipientExecution.run_id == run_id).group_by(WhatsAppAutomationDelivery.status).all()
    return _metrics(rows)


def flow_delivery_metrics(db: Session, run_id: int) -> dict:
    from ..models import AutomationFlowRecipientExecution, AutomationNodeExecution
    rows = db.query(WhatsAppAutomationDelivery.status, func.count(WhatsAppAutomationDelivery.id)).join(
        AutomationNodeExecution, WhatsAppAutomationDelivery.flow_node_execution_id == AutomationNodeExecution.id,
    ).join(AutomationFlowRecipientExecution, AutomationNodeExecution.flow_recipient_execution_id == AutomationFlowRecipientExecution.id).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id,
    ).group_by(WhatsAppAutomationDelivery.status).all()
    return _metrics(rows)


def _metrics(rows) -> dict:
    counts = {status: count for status, count in rows}
    sent = sum(counts.values())
    # Read is also a delivered message; current state is mutually exclusive.
    delivered = counts.get("delivered", 0) + counts.get("read", 0)
    read, failed = counts.get("read", 0), counts.get("failed", 0)
    return {"sent": sent, "delivered": delivered, "read": read, "failed": failed,
            "delivery_rate": round(delivered / sent, 4) if sent else None,
            "read_rate": round(read / sent, 4) if sent else None}
