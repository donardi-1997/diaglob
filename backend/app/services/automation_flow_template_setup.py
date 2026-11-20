"""Create a ready-to-run flow from a catalog model in one step.

A model's message node can be bound to an approved WhatsApp (Meta) template
and its {{n}} parameters to Diaglob variables, so notifications reach
customers outside the 24h service window without editing the graph. The flow
can optionally be published and activated in the same call. Does NOT import
FastAPI.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..automation_flow_templates import get_flow_template
from ..models import AutomationFlow, WhatsAppConnection, WhatsAppMessageTemplate
from ..whatsapp_compliance import (
    FLOW_TEMPLATE_VARIABLES,
    MESSAGE_MODES,
    template_body_parameter_count,
)
from .automation_flows_service import activate_flow, create_flow, get_flow, publish_version


class FlowTemplateSetupError(Exception):
    """Invalid model setup. `code` is a stable, client-facing identifier."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FlowTemplateSetup:
    whatsapp_template_id: int | None = None
    template_variables: dict | None = None
    message_mode: str | None = None
    activate: bool = False
    name: str | None = None


_MAX_NAME = 255


def _available_flow_name(db: Session, organization_id: int, store_id: int, base: str) -> str:
    """Flow names are unique per store; reusing a model must not fail."""
    base = base[:_MAX_NAME].strip()
    taken = {
        row[0] for row in db.query(AutomationFlow.name).filter(
            AutomationFlow.organization_id == organization_id,
            AutomationFlow.store_id == store_id,
            AutomationFlow.name.like(f"{base[:200]}%"),
        ).all()
    }
    if base not in taken:
        return base
    suffix = 2
    while True:
        tail = f" ({suffix})"
        candidate = base[: _MAX_NAME - len(tail)] + tail
        if candidate not in taken:
            return candidate
        suffix += 1


def _message_node(graph: dict, node_id: str) -> dict:
    for node in graph.get("nodes", []):
        if node.get("id") == node_id and node.get("type") == "message":
            return node
    raise FlowTemplateSetupError("TEMPLATE_MESSAGE_NODE_MISSING")


def _approved_template(db: Session, organization_id: int, store_id: int, template_id: int) -> WhatsAppMessageTemplate:
    connection = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.organization_id == organization_id,
        WhatsAppConnection.store_id == store_id,
        WhatsAppConnection.status == "connected",
    ).first()
    if connection is None:
        raise FlowTemplateSetupError("WHATSAPP_NOT_CONNECTED")
    template = db.query(WhatsAppMessageTemplate).filter(
        WhatsAppMessageTemplate.id == template_id,
        WhatsAppMessageTemplate.organization_id == organization_id,
        WhatsAppMessageTemplate.whatsapp_connection_id == connection.id,
    ).first()
    if template is None:
        raise FlowTemplateSetupError("WHATSAPP_TEMPLATE_NOT_FOUND")
    if template.status != "approved":
        raise FlowTemplateSetupError("WHATSAPP_TEMPLATE_NOT_APPROVED")
    return template


def _apply_whatsapp_template(
    db: Session,
    organization_id: int,
    store_id: int,
    model: dict,
    graph: dict,
    setup: FlowTemplateSetup,
) -> None:
    wa_setup = model.get("whatsapp_setup")
    if not wa_setup:
        raise FlowTemplateSetupError("TEMPLATE_HAS_NO_WHATSAPP_MESSAGE")
    node = _message_node(graph, wa_setup["node_id"])
    template = _approved_template(db, organization_id, store_id, int(setup.whatsapp_template_id))

    variables = setup.template_variables
    if variables is None:
        variables = {"body": list(wa_setup["suggested_template"]["variables"])}
    body = variables.get("body") if isinstance(variables, dict) else None
    if not isinstance(body, list) or not all(isinstance(item, str) for item in body):
        raise FlowTemplateSetupError("TEMPLATE_VARIABLES_INVALID")
    if any(item not in FLOW_TEMPLATE_VARIABLES for item in body):
        raise FlowTemplateSetupError("TEMPLATE_VARIABLES_UNSUPPORTED")
    expected = template_body_parameter_count(template)
    if expected is not None and expected != len(body):
        raise FlowTemplateSetupError("TEMPLATE_PARAMETER_COUNT_MISMATCH")

    mode = setup.message_mode or "auto"
    if mode not in MESSAGE_MODES or mode == "free_form":
        raise FlowTemplateSetupError("MESSAGE_MODE_INVALID")

    config = node.setdefault("config", {})
    config.update({
        "message_mode": mode,
        "whatsapp_template_id": template.id,
        "template_provider_name": template.provider_template_name,
        "template_language": template.language_code,
        "template_variables": {"body": list(body)},
    })


def create_flow_from_model(
    db: Session,
    *,
    organization_id: int,
    store_id: int,
    user_id: int,
    model_id: str,
    setup: FlowTemplateSetup | None = None,
) -> dict:
    """Create (and optionally publish + activate) a flow from a catalog model.

    Integration availability is checked by the caller. Validation of the
    final graph is enforced by create_flow/publish_version/activate_flow.
    """
    setup = setup or FlowTemplateSetup()
    model = get_flow_template(model_id)
    if model is None:
        raise FlowTemplateSetupError("FLOW_TEMPLATE_NOT_FOUND")

    graph = deepcopy(model["graph"])
    if setup.whatsapp_template_id is not None:
        _apply_whatsapp_template(db, organization_id, store_id, model, graph, setup)
    elif setup.template_variables is not None or setup.message_mode is not None:
        raise FlowTemplateSetupError("WHATSAPP_TEMPLATE_REQUIRED")

    name = _available_flow_name(
        db, organization_id, store_id, (setup.name or "").strip() or model["name"],
    )
    flow = create_flow(
        db, organization_id, store_id, user_id, name, model["description"], graph,
    )

    activated = False
    if setup.activate:
        publish_version(db, organization_id, store_id, flow["id"], flow["current_version_id"])
        activate_flow(db, organization_id, store_id, flow["id"])
        activated = True

    return {
        "template_id": model_id,
        "recommended_role": model.get("recommended_role"),
        "flow": get_flow(db, organization_id, store_id, flow["id"]) if activated else flow,
        "whatsapp_template_bound": setup.whatsapp_template_id is not None,
        "activated": activated,
        "trigger_mode": model.get("trigger_mode"),
        "next_step": "monitor_runs" if activated else "review_publish_activate",
    }
