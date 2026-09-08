"""Automation flow business orchestration service.

Handles flow CRUD, version lifecycle, publish/activate/deactivate,
flow runs, and recipient operations. Does NOT import FastAPI.
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..automation_flow_graph import validate_graph
from ..automation_flow_engine import materialize_flow_trigger, utcnow
from ..automation_flow_helpers import (
    serialize_flow as _sf,
    serialize_version as _sv,
    serialize_run as _sr,
    serialize_recipient as _srec,
)
from ..models import (
    AutomationFlow,
    AutomationFlowVersion,
    AutomationFlowRun,
    AutomationFlowRecipientExecution,
    AutomationNodeExecution,
    Customer,
    CustomerStoreProfile,
    Store,
)

logger = logging.getLogger(__name__)


class FlowNotFoundError(Exception):
    pass


class FlowConflictError(Exception):
    pass


class FlowValidationError(Exception):
    pass


class FlowVersionMismatchError(Exception):
    pass


def _flow_or_404(db: Session, organization_id: int, store_id: int, flow_id: int) -> AutomationFlow:
    flow = db.get(AutomationFlow, flow_id)
    if not flow or flow.organization_id != organization_id or flow.store_id != store_id:
        raise FlowNotFoundError("Flow not found")
    return flow


def _flow_version_or_404(db: Session, flow: AutomationFlow, version_id: int) -> AutomationFlowVersion:
    version = db.query(AutomationFlowVersion).filter(
        AutomationFlowVersion.id == version_id,
        AutomationFlowVersion.flow_id == flow.id,
        AutomationFlowVersion.organization_id == flow.organization_id,
    ).first()
    if not version:
        raise FlowNotFoundError("Version not found")
    return version


def _store_or_404(db: Session, organization_id: int, store_id: int) -> Store:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise FlowNotFoundError("Store not found")
    return store


def create_flow(db: Session, organization_id: int, store_id: int, user_id: int, name: str, description: str | None, graph: dict) -> dict:
    _store_or_404(db, organization_id, store_id)

    if graph:
        errors = validate_graph(graph)
        if errors:
            raise FlowValidationError(str(errors))

    flow = AutomationFlow(
        organization_id=organization_id, store_id=store_id,
        name=name, description=description,
        status="draft", created_by=user_id,
    )
    db.add(flow)
    db.flush()

    if graph:
        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=organization_id,
            version_number=1, graph=graph,
        )
        db.add(ver)
        db.flush()
        flow.current_version_id = ver.id

    db.commit()
    return _sf(flow)


def list_flows(db: Session, organization_id: int, store_id: int, status: str | None = None) -> list:
    q = db.query(AutomationFlow).filter(
        AutomationFlow.organization_id == organization_id,
        AutomationFlow.store_id == store_id,
    )
    if status:
        q = q.filter(AutomationFlow.status == status)
    return [_sf(f) for f in q.order_by(AutomationFlow.updated_at.desc()).all()]


def get_flow(db: Session, organization_id: int, store_id: int, flow_id: int) -> dict:
    flow = _flow_or_404(db, organization_id, store_id, flow_id)
    result = _sf(flow)
    if flow.current_version_id:
        ver = _flow_version_or_404(db, flow, flow.current_version_id)
        result["current_version"] = _sv(ver)
    return result


def update_flow(db: Session, organization_id: int, store_id: int, flow_id: int, name: str | None, description: str | None, graph: dict | None) -> dict:
    flow = _flow_or_404(db, organization_id, store_id, flow_id)

    if flow.status == "active":
        raise FlowConflictError("Cannot edit active flow; duplicate or archive first")

    if name is not None:
        flow.name = name
    if description is not None:
        flow.description = description

    if graph is not None:
        errors = validate_graph(graph)
        if errors:
            raise FlowValidationError(str(errors))

        max_ver = db.query(AutomationFlowVersion.version_number).filter(
            AutomationFlowVersion.flow_id == flow.id
        ).order_by(AutomationFlowVersion.version_number.desc()).first()
        next_num = (max_ver[0] if max_ver else 0) + 1

        ver = AutomationFlowVersion(
            flow_id=flow.id, organization_id=organization_id,
            version_number=next_num, graph=graph,
        )
        db.add(ver)
        db.flush()
        flow.current_version_id = ver.id

    flow.updated_at = utcnow()
    db.commit()
    return _sf(flow)


def archive_flow(db: Session, organization_id: int, store_id: int, flow_id: int) -> dict:
    flow = _flow_or_404(db, organization_id, store_id, flow_id)
    flow.status = "archived"
    flow.updated_at = utcnow()
    db.commit()
    return {"status": "archived", "id": flow.id}


def list_versions(db: Session, organization_id: int, store_id: int, flow_id: int) -> list:
    flow = _flow_or_404(db, organization_id, store_id, flow_id)
    versions = db.query(AutomationFlowVersion).filter(
        AutomationFlowVersion.flow_id == flow_id
    ).order_by(AutomationFlowVersion.version_number.desc()).all()
    return [_sv(v) for v in versions]


def create_version(db: Session, organization_id: int, store_id: int, flow_id: int, graph: dict) -> dict:
    flow = _flow_or_404(db, organization_id, store_id, flow_id)

    errors = validate_graph(graph)
    if errors:
        raise FlowValidationError(str(errors))

    max_ver = db.query(AutomationFlowVersion.version_number).filter(
        AutomationFlowVersion.flow_id == flow_id
    ).order_by(AutomationFlowVersion.version_number.desc()).first()
    next_num = (max_ver[0] if max_ver else 0) + 1

    ver = AutomationFlowVersion(
        flow_id=flow_id, organization_id=organization_id,
        version_number=next_num, graph=graph,
    )
    db.add(ver)
    db.flush()
    flow.current_version_id = ver.id
    flow.updated_at = utcnow()
    db.commit()
    return _sv(ver)


def publish_version(db: Session, organization_id: int, store_id: int, flow_id: int, version_id: int) -> dict:
    flow = _flow_or_404(db, organization_id, store_id, flow_id)
    ver = _flow_version_or_404(db, flow, version_id)

    if ver.published_at:
        raise FlowConflictError("Version already published")

    ver.published_at = utcnow()
    flow.updated_at = utcnow()
    db.commit()
    return _sv(ver)


def activate_flow(db: Session, organization_id: int, store_id: int, flow_id: int) -> dict:
    flow = _flow_or_404(db, organization_id, store_id, flow_id)

    if not flow.current_version_id:
        raise FlowConflictError("No version to activate")

    ver = _flow_version_or_404(db, flow, flow.current_version_id)

    if not ver.published_at:
        raise FlowConflictError("Version must be published before activation")

    ver.activated_at = utcnow()
    flow.active_version_id = ver.id
    flow.status = "active"
    flow.updated_at = utcnow()
    db.commit()
    return _sf(flow)


def deactivate_flow(db: Session, organization_id: int, store_id: int, flow_id: int) -> dict:
    flow = _flow_or_404(db, organization_id, store_id, flow_id)
    flow.status = "draft"
    flow.updated_at = utcnow()
    db.commit()
    return _sf(flow)


def trigger_flow_run(db: Session, organization_id: int, store_id: int, flow_id: int, customer_ids: list[int], trigger_key: str | None) -> dict:
    flow = _flow_or_404(db, organization_id, store_id, flow_id)

    if flow.status != "active" or not flow.active_version_id:
        raise FlowConflictError("Flow must be active to trigger")

    customers = db.query(Customer).join(
        CustomerStoreProfile,
        CustomerStoreProfile.customer_id == Customer.id,
    ).filter(
        Customer.id.in_(customer_ids),
        Customer.organization_id == organization_id,
        CustomerStoreProfile.store_id == store_id,
    ).all()

    found_ids = {c.id for c in customers}
    missing = set(customer_ids) - found_ids
    if missing:
        raise FlowValidationError(str([f"Customer {cid} not found" for cid in sorted(missing)]))

    run = materialize_flow_trigger(db, flow, customer_ids, trigger_key)
    if not run:
        raise FlowConflictError("Trigger key already used or flow not materializable")

    return _sr(run)


def list_flow_runs(db: Session, organization_id: int, store_id: int, flow_id: int) -> list:
    _flow_or_404(db, organization_id, store_id, flow_id)
    runs = db.query(AutomationFlowRun).filter(
        AutomationFlowRun.flow_id == flow_id
    ).order_by(AutomationFlowRun.created_at.desc()).all()
    return [_sr(r) for r in runs]


def get_flow_run(db: Session, organization_id: int, store_id: int, flow_id: int, run_id: int) -> dict:
    _flow_or_404(db, organization_id, store_id, flow_id)
    run = db.get(AutomationFlowRun, run_id)
    if not run or run.flow_id != flow_id:
        raise FlowNotFoundError("Run not found")

    recipients = db.query(AutomationFlowRecipientExecution).filter(
        AutomationFlowRecipientExecution.flow_run_id == run_id
    ).all()
    result = _sr(run)
    result["recipients"] = [_srec(r) for r in recipients]
    return result


def list_flow_run_recipients(
    db: Session, organization_id: int, store_id: int, flow_id: int, run_id: int,
    status: str | None = None, search: str | None = None,
    page: int = 1, size: int = 50,
) -> dict:
    _flow_or_404(db, organization_id, store_id, flow_id)
    run = db.get(AutomationFlowRun, run_id)
    if not run or run.flow_id != flow_id:
        raise FlowNotFoundError("Run not found")

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


def get_flow_recipient_detail(db: Session, organization_id: int, store_id: int, flow_id: int, run_id: int, recipient_id: int) -> dict:
    _flow_or_404(db, organization_id, store_id, flow_id)
    recipient = db.get(AutomationFlowRecipientExecution, recipient_id)
    if not recipient or recipient.flow_run_id != run_id:
        raise FlowNotFoundError("Recipient not found")

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


def retry_flow_recipient(db: Session, organization_id: int, store_id: int, flow_id: int, run_id: int, recipient_id: int) -> dict:
    _flow_or_404(db, organization_id, store_id, flow_id)
    recipient = db.get(AutomationFlowRecipientExecution, recipient_id)
    if not recipient or recipient.flow_run_id != run_id:
        raise FlowNotFoundError("Recipient not found")

    if recipient.status not in ("failed", "ambiguous", "completed"):
        raise FlowConflictError(f"Cannot retry recipient in '{recipient.status}' status")

    now = utcnow()
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


def simulate_flow(db: Session, organization_id: int, store_id: int, graph: dict) -> dict:
    _store_or_404(db, organization_id, store_id)

    if not graph:
        raise FlowValidationError("Graph is required for simulation")

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
