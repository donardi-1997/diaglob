"""Flow Builder CRUD + Simulation API endpoints (V2.2)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .db import Base, get_db
from .deps import get_current_active_user
from .models import (
    AutomationFlow, AutomationFlowVersion, AutomationFlowRun,
    AutomationFlowRecipientExecution, AutomationNodeExecution,
    User, Customer, Store,
)
from .automation_flow_graph import validate_graph
from .automation_flow_engine import (
    materialize_flow_trigger, utcnow,
)

router = APIRouter(prefix="/api/automation-flows", tags=["automation-flows"])


# ── Pydantic schemas ──────────────────────────────────────────


class FlowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    graph: dict[str, Any] = {}


class FlowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    graph: dict[str, Any] | None = None


class FlowVersionPublish(BaseModel):
    graph: dict[str, Any]


class FlowRunCreate(BaseModel):
    customer_ids: list[int] = Field(min_length=1, max_length=1000)
    trigger_key: str | None = None


# ── Helpers ────────────────────────────────────────────────────


def _serialize_flow(flow: AutomationFlow) -> dict:
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


def _serialize_version(v: AutomationFlowVersion) -> dict:
    return {
        "id": v.id,
        "flow_id": v.flow_id,
        "version_number": v.version_number,
        "graph": v.graph,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "activated_at": v.activated_at.isoformat() if v.activated_at else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


def _serialize_run(run: AutomationFlowRun) -> dict:
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


def _serialize_recipient(r: AutomationFlowRecipientExecution) -> dict:
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


# ── CRUD Endpoints ─────────────────────────────────────────────


@router.post("")
def create_flow(payload: FlowCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Create a new automation flow (draft)."""
    if payload.graph:
        errors = validate_graph(payload.graph)
        if errors:
            raise HTTPException(422, detail={"errors": errors})
    flow = AutomationFlow(
        organization_id=user.organization_id,
        store_id=user.store_id,
        name=payload.name,
        description=payload.description,
        status="draft",
        created_by=user.id,
        current_version_id=None,
        active_version_id=None,
    )
    db.add(flow)
    db.flush()
    if payload.graph:
        ver = AutomationFlowVersion(
            flow_id=flow.id,
            organization_id=user.organization_id,
            version_number=1,
            graph=payload.graph,
        )
        db.add(ver)
        db.flush()
        flow.current_version_id = ver.id
    db.commit()
    return _serialize_flow(flow)


@router.get("")
def list_flows(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List automation flows for current org/store."""
    q = db.query(AutomationFlow).filter(
        AutomationFlow.organization_id == user.organization_id,
        AutomationFlow.store_id == user.store_id,
    )
    if status:
        q = q.filter(AutomationFlow.status == status)
    flows = q.order_by(AutomationFlow.updated_at.desc()).all()
    return [_serialize_flow(f) for f in flows]


@router.get("/{flow_id}")
def get_flow(flow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Get a flow by ID with its current version graph."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    result = _serialize_flow(flow)
    if flow.current_version_id:
        ver = db.get(AutomationFlowVersion, flow.current_version_id)
        if ver:
            result["current_version"] = _serialize_version(ver)
    return result


@router.put("/{flow_id}")
def update_flow(flow_id: int, payload: FlowUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Update a flow. If graph changes, creates new draft version."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
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
        # Get max version number
        max_ver = db.query(AutomationFlowVersion.version_number).filter(
            AutomationFlowVersion.flow_id == flow.id
        ).order_by(AutomationFlowVersion.version_number.desc()).first()
        next_num = (max_ver[0] if max_ver else 0) + 1
        ver = AutomationFlowVersion(
            flow_id=flow.id,
            organization_id=user.organization_id,
            version_number=next_num,
            graph=payload.graph,
        )
        db.add(ver)
        db.flush()
        flow.current_version_id = ver.id
    flow.updated_at = utcnow()
    db.commit()
    return _serialize_flow(flow)


@router.delete("/{flow_id}")
def archive_flow(flow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Archive (soft-delete) a flow."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    flow.status = "archived"
    flow.updated_at = utcnow()
    db.commit()
    return {"status": "archived", "id": flow.id}


# ── Version Endpoints ──────────────────────────────────────────


@router.get("/{flow_id}/versions")
def list_versions(flow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """List all versions for a flow."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    versions = db.query(AutomationFlowVersion).filter(
        AutomationFlowVersion.flow_id == flow_id
    ).order_by(AutomationFlowVersion.version_number.desc()).all()
    return [_serialize_version(v) for v in versions]


@router.post("/{flow_id}/versions")
def create_version(flow_id: int, payload: FlowVersionPublish, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Create a new version (draft) for a flow."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    errors = validate_graph(payload.graph)
    if errors:
        raise HTTPException(422, detail={"errors": errors})
    max_ver = db.query(AutomationFlowVersion.version_number).filter(
        AutomationFlowVersion.flow_id == flow_id
    ).order_by(AutomationFlowVersion.version_number.desc()).first()
    next_num = (max_ver[0] if max_ver else 0) + 1
    ver = AutomationFlowVersion(
        flow_id=flow_id,
        organization_id=user.organization_id,
        version_number=next_num,
        graph=payload.graph,
    )
    db.add(ver)
    db.flush()
    flow.current_version_id = ver.id
    flow.updated_at = utcnow()
    db.commit()
    return _serialize_version(ver)


@router.post("/{flow_id}/versions/{version_id}/publish")
def publish_version(flow_id: int, version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Publish a version (makes it immutable)."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    ver = db.get(AutomationFlowVersion, version_id)
    if not ver or ver.flow_id != flow_id:
        raise HTTPException(404, detail="Version not found")
    if ver.published_at:
        raise HTTPException(409, detail="Version already published")
    ver.published_at = utcnow()
    flow.updated_at = utcnow()
    db.commit()
    return _serialize_version(ver)


@router.post("/{flow_id}/activate")
def activate_flow(flow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Activate a flow using its current published version."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    if not flow.current_version_id:
        raise HTTPException(409, detail="No version to activate")
    ver = db.get(AutomationFlowVersion, flow.current_version_id)
    if not ver:
        raise HTTPException(404, detail="Current version not found")
    if not ver.published_at:
        raise HTTPException(409, detail="Version must be published before activation")
    ver.activated_at = utcnow()
    flow.active_version_id = ver.id
    flow.status = "active"
    flow.updated_at = utcnow()
    db.commit()
    return _serialize_flow(flow)


@router.post("/{flow_id}/deactivate")
def deactivate_flow(flow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Deactivate a flow (stop accepting new triggers)."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    flow.status = "draft"
    flow.updated_at = utcnow()
    db.commit()
    return _serialize_flow(flow)


# ── Run Endpoints ──────────────────────────────────────────────


@router.post("/{flow_id}/runs")
def trigger_flow_run(flow_id: int, payload: FlowRunCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Trigger a flow run for a set of customers."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    if flow.status != "active" or not flow.active_version_id:
        raise HTTPException(409, detail="Flow must be active to trigger")
    # Verify customers exist and belong to this store
    customers = db.query(Customer).filter(
        Customer.id.in_(payload.customer_ids),
        Customer.store_id == user.store_id,
        Customer.organization_id == user.organization_id,
    ).all()
    found_ids = {c.id for c in customers}
    missing = set(payload.customer_ids) - found_ids
    if missing:
        raise HTTPException(422, detail={"errors": [f"Customer {cid} not found" for cid in sorted(missing)]})
    run = materialize_flow_trigger(db, flow, payload.customer_ids, payload.trigger_key)
    if not run:
        raise HTTPException(409, detail="Trigger key already used or flow not materializable")
    return _serialize_run(run)


@router.get("/{flow_id}/runs")
def list_flow_runs(flow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """List runs for a flow."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    runs = db.query(AutomationFlowRun).filter(
        AutomationFlowRun.flow_id == flow_id
    ).order_by(AutomationFlowRun.created_at.desc()).all()
    return [_serialize_run(r) for r in runs]


@router.get("/{flow_id}/runs/{run_id}")
def get_flow_run(flow_id: int, run_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Get a specific flow run with recipients."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    run = db.get(AutomationFlowRun, run_id)
    if not run or run.flow_id != flow_id:
        raise HTTPException(404, detail="Run not found")
    recipients = db.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id
    ).all()
    result = _serialize_run(run)
    result["recipients"] = [_serialize_recipient(r) for r in recipients]
    return result


@router.get("/{flow_id}/runs/{run_id}/recipients")
def list_flow_run_recipients(
    flow_id: int, run_id: int,
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """List recipients for a flow run with filtering."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
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
    return {
        "items": [_serialize_recipient(r) for r in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, -(-total // size)),
    }


@router.get("/{flow_id}/runs/{run_id}/recipients/{recipient_id}")
def get_flow_recipient_detail(flow_id: int, run_id: int, recipient_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Get a specific flow recipient with node executions."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    recipient = db.get(AutomationFlowRecipientExecution, recipient_id)
    if not recipient or recipient.flow_run_id != run_id:
        raise HTTPException(404, detail="Recipient not found")
    node_execs = db.query(AutomationNodeExecution).filter(
        AutomationNodeExecution.flow_recipient_execution_id == recipient_id
    ).order_by(AutomationNodeExecution.started_at).all()
    result = _serialize_recipient(recipient)
    result["node_executions"] = [
        {
            "id": ne.id, "node_id": ne.node_id, "node_type": ne.node_type,
            "status": ne.status, "outcome": ne.outcome,
            "provider_message_id": ne.provider_message_id,
            "error_code": ne.error_code, "error_message": ne.error_message,
            "metadata": ne.extra_data,
            "started_at": ne.started_at.isoformat() if ne.started_at else None,
            "completed_at": ne.completed_at.isoformat() if ne.completed_at else None,
        }
        for ne in node_execs
    ]
    return result


# ── Simulation ─────────────────────────────────────────────────


@router.post("/simulate")
def simulate_flow(payload: FlowCreate, db: Session = Depends(get_db), user: User = Depends(get_current_active_user)):
    """Simulate a flow graph — validate and report issues."""
    graph = payload.graph
    if not graph:
        raise HTTPException(422, detail={"errors": ["Graph is required for simulation"]})
    errors = validate_graph(graph)
    if errors:
        return {"valid": False, "errors": errors, "warnings": []}
    # Structural analysis
    warnings: list[str] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    message_nodes = [n for n in nodes if n.get("type") == "message"]
    wait_nodes = [n for n in nodes if n.get("type") == "wait"]
    condition_nodes = [n for n in nodes if n.get("type") == "condition"]
    # Path analysis
    from .automation_flow_graph import get_entry_node, _reachable_from_trigger
    entry = get_entry_node(graph)
    reachable = _reachable_from_trigger(nodes, edges)
    if entry:
        reachable.discard(entry["id"])
    end_nodes = [n for n in nodes if n.get("type") == "end"]
    ends_reachable = [n for n in end_nodes if n["id"] in reachable]
    if not ends_reachable:
        warnings.append("No end nodes reachable from trigger")
    if len(message_nodes) == 0:
        warnings.append("Flow has no message nodes — recipients will pass through without communication")
    if len(wait_nodes) > 5:
        warnings.append(f"Flow has {len(wait_nodes)} wait nodes — recipients may wait a long time")
    return {
        "valid": True,
        "errors": [],
        "warnings": warnings,
        "summary": {
            "total_nodes": len(nodes),
            "message_nodes": len(message_nodes),
            "wait_nodes": len(wait_nodes),
            "condition_nodes": len(condition_nodes),
            "end_nodes": len(end_nodes),
        },
    }


# ── Retry endpoint ─────────────────────────────────────────────


@router.post("/{flow_id}/runs/{run_id}/recipients/{recipient_id}/retry")
def retry_flow_recipient(
    flow_id: int, run_id: int, recipient_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
):
    """Manually retry a failed/ambiguous flow recipient execution."""
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != user.organization_id or flow.store_id != user.store_id:
        raise HTTPException(404, detail="Flow not found")
    recipient = db.get(AutomationFlowRecipientExecution, recipient_id)
    if not recipient or recipient.flow_run_id != run_id:
        raise HTTPException(404, detail="Recipient not found")
    if recipient.status not in ("failed", "ambiguous", "completed"):
        raise HTTPException(409, detail=f"Cannot retry recipient in '{recipient.status}' status")
    now = utcnow()
    recipient.status = "active"
    recipient.error_code = None
    recipient.error_message = None
    recipient.claim_token = None
    recipient.claim_expires_at = None
    recipient.next_action_at = now
    recipient.started_at = now
    recipient.completed_at = None
    # Recalculate run counts
    run = db.get(AutomationFlowRun, run_id)
    statuses = [r.status for r in db.query(AutomationFlowRecipientExecution.status).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id,
    ).all()]
    run.failed_recipients = sum(1 for s in statuses if s in ("failed", "ambiguous"))
    run.completed_recipients = sum(1 for s in statuses if s == "completed")
    if run.status == "completed":
        run.status = "pending"
        run.completed_at = None
    db.commit()
    return _serialize_recipient(recipient)
