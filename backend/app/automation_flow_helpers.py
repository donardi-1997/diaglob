"""Flow Builder helper functions for V2.2."""
from __future__ import annotations

from typing import Any

from .models import (
    AutomationFlow, AutomationFlowVersion, AutomationFlowRun,
    AutomationFlowRecipientExecution, AutomationNodeExecution,
)


def serialize_flow(flow: AutomationFlow) -> dict:
    return {
        "id": flow.id,
        "name": flow.name,
        "status": flow.status,
        "description": flow.description,
        "current_version_id": flow.current_version_id,
        "active_version_id": flow.active_version_id,
        "created_by": flow.created_by,
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
        "updated_at": flow.updated_at.isoformat() if flow.updated_at else None,
    }


def serialize_version(v: AutomationFlowVersion) -> dict:
    return {
        "id": v.id,
        "flow_id": v.flow_id,
        "version_number": v.version_number,
        "graph": v.graph,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "activated_at": v.activated_at.isoformat() if v.activated_at else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def serialize_run(run: AutomationFlowRun) -> dict:
    return {
        "id": run.id,
        "flow_id": run.flow_id,
        "flow_version_id": run.flow_version_id,
        "status": run.status,
        "trigger_key": run.trigger_key,
        "total_recipients": run.total_recipients,
        "completed_recipients": run.completed_recipients,
        "failed_recipients": run.failed_recipients,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def serialize_recipient(r: AutomationFlowRecipientExecution) -> dict:
    return {
        "id": r.id,
        "flow_run_id": r.flow_run_id,
        "customer_id": r.customer_id,
        "status": r.status,
        "current_node_id": r.current_node_id,
        "next_action_at": r.next_action_at.isoformat() if r.next_action_at else None,
        "attempt_count": r.attempt_count,
        "error_code": r.error_code,
        "error_message": r.error_message,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }
