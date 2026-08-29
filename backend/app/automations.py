"""
Automation engine for Diaglob.

Responsibilities:
- Evaluate conditions safely
- Execute actions safely
- Manage AutomationExecution lifecycle
- Provide emit_event() for future event dispatch
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from .models import (
    Automation,
    AutomationExecution,
    Order,
)

logger = logging.getLogger(__name__)


# ============================================================
# TRIGGER TYPES
# ============================================================

VALID_TRIGGER_TYPES = frozenset({
    "manual",
    "order.created",
    "order.failed",
    "conversation.created",
    "message.received",
})


# ============================================================
# CONDITION OPERATORS
# ============================================================

OPERATORS = frozenset({
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "contains",
    "exists",
})


# ============================================================
# CONDITION EVALUATION
# ============================================================


def _resolve_field(
    payload: dict[str, Any],
    field: str,
) -> Any:
    """
    Resolve a dotted field path against a payload dict.

    Examples:
        "order.total" -> payload["order"]["total"]
        "customer_name" -> payload["customer_name"]
    """
    parts = field.split(".")
    current: Any = payload

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None

    return current


def evaluate_condition(
    condition: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    """
    Evaluate a single condition against a payload.

    Returns True if condition is met, False otherwise.
    Never raises — unparseable conditions return False.
    """
    try:
        field = condition.get("field", "")
        operator = condition.get("operator", "")
        value = condition.get("value")

        if not field or not operator:
            return False

        if operator not in OPERATORS:
            return False

        resolved = _resolve_field(payload, field)

        if operator == "exists":
            return resolved is not None

        if resolved is None:
            return False

        if operator == "eq":
            return resolved == value

        if operator == "neq":
            return resolved != value

        if operator in ("gt", "gte", "lt", "lte"):
            resolved_num = (
                float(resolved)
                if not isinstance(resolved, (int, float))
                else resolved
            )
            value_num = (
                float(value)
                if not isinstance(value, (int, float))
                else value
            )

            if operator == "gt":
                return resolved_num > value_num
            if operator == "gte":
                return resolved_num >= value_num
            if operator == "lt":
                return resolved_num < value_num
            if operator == "lte":
                return resolved_num <= value_num

        if operator == "contains":
            return str(value).lower() in str(
                resolved
            ).lower()

    except Exception:
        logger.debug(
            "Condition evaluation failed: %s",
            condition,
            exc_info=True,
        )
        return False

    return False


def evaluate_conditions(
    conditions: list[dict[str, Any]],
    payload: dict[str, Any],
) -> bool:
    """
    Evaluate ALL conditions (AND logic).

    Empty conditions list = always passes.
    """
    if not conditions:
        return True

    for condition in conditions:
        if not evaluate_condition(condition, payload):
            return False

    return True


# ============================================================
# ACTION EXECUTION
# ============================================================


def _sanitize_error(exc: Exception) -> str:
    """
    Sanitize exception message for safe storage.
    Never include tokens, passwords, or stack traces.
    """
    msg = str(exc)

    lower = msg.lower()

    dangerous = [
        "token",
        "password",
        "secret",
        "access_token",
        "bearer",
    ]

    for word in dangerous:
        if word in lower:
            return "An internal error occurred."

    return msg[:500]


def execute_log_event(
    db: Session,
    organization_id: int,
    store_id: int | None,
    action: dict[str, Any],
    payload: dict[str, Any],
    execution: AutomationExecution,
) -> dict[str, Any]:
    """
    Log event action — records the event in execution result.
    """
    message = action.get(
        "message",
        "Event logged",
    )

    return {
        "action": "log_event",
        "status": "applied",
        "message": message,
        "logged_at": datetime.utcnow().isoformat(),
    }


def execute_add_order_note(
    db: Session,
    organization_id: int,
    store_id: int | None,
    action: dict[str, Any],
    payload: dict[str, Any],
    execution: AutomationExecution,
) -> dict[str, Any]:
    """
    Add a note to an order.

    Requires order_id in the action or payload.
    Validates store_id and organization_id.
    """
    order_id = action.get("order_id") or payload.get(
        "order_id"
    )

    if not order_id:
        return {
            "action": "add_order_note",
            "status": "skipped",
            "reason": "No order_id provided",
        }

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.organization_id
            == organization_id,
        )
        .first()
    )

    if not order:
        return {
            "action": "add_order_note",
            "status": "skipped",
            "reason": "Order not found in organization",
        }

    if store_id and order.store_id != store_id:
        return {
            "action": "add_order_note",
            "status": "skipped",
            "reason": "Order belongs to a different store",
        }

    note_text = action.get("note", "")

    if not note_text:
        return {
            "action": "add_order_note",
            "status": "skipped",
            "reason": "No note text provided",
        }

    existing = order.note or ""

    if existing:
        order.note = f"{existing}\n{note_text}"
    else:
        order.note = note_text

    db.flush()

    return {
        "action": "add_order_note",
        "status": "applied",
        "order_id": order.id,
    }


ACTION_HANDLERS = {
    "log_event": execute_log_event,
    "add_order_note": execute_add_order_note,
}


def execute_actions(
    db: Session,
    organization_id: int,
    store_id: int | None,
    actions: list[dict[str, Any]],
    payload: dict[str, Any],
    execution: AutomationExecution,
) -> list[dict[str, Any]]:
    """
    Execute all actions in order.

    Returns list of action results.
    If any action fails, subsequent actions are still attempted.
    """
    results = []

    for action in actions:
        action_type = action.get("type", "")

        handler = ACTION_HANDLERS.get(action_type)

        if not handler:
            results.append(
                {
                    "action": action_type,
                    "status": "skipped",
                    "reason": "Unknown action type",
                }
            )
            continue

        try:
            result = handler(
                db=db,
                organization_id=organization_id,
                store_id=store_id,
                action=action,
                payload=payload,
                execution=execution,
            )
            results.append(result)
        except Exception as exc:
            results.append(
                {
                    "action": action_type,
                    "status": "failed",
                    "error": _sanitize_error(exc),
                }
            )

    return results


# ============================================================
# AUTOMATION EXECUTION
# ============================================================


def execute_automation(
    db: Session,
    automation: Automation,
    event_type: str,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> AutomationExecution:
    """
    Execute a single automation end-to-end.

    1. Create execution record (pending)
    2. Evaluate conditions
    3. Execute actions
    4. Update execution status
    """
    execution = AutomationExecution(
        automation_id=automation.id,
        organization_id=automation.organization_id,
        store_id=automation.store_id,
        event_type=event_type,
        event_id=event_id,
        status="running",
        input_json=json.dumps(payload, default=str),
        started_at=datetime.utcnow(),
    )

    db.add(execution)
    db.flush()

    try:
        conditions = json.loads(
            automation.conditions_json
        )
    except (json.JSONDecodeError, TypeError):
        conditions = []

    if not evaluate_conditions(conditions, payload):
        execution.status = "skipped"
        execution.result_json = json.dumps(
            {
                "reason": "Conditions not met",
                "conditions": conditions,
            }
        )
        execution.completed_at = (
            datetime.utcnow()
        )
        db.commit()
        return execution

    try:
        actions = json.loads(
            automation.actions_json
        )
    except (json.JSONDecodeError, TypeError):
        actions = []

    action_results = execute_actions(
        db=db,
        organization_id=automation.organization_id,
        store_id=automation.store_id,
        actions=actions,
        payload=payload,
        execution=execution,
    )

    has_failure = any(
        r.get("status") == "failed"
        for r in action_results
    )

    execution.status = (
        "failed" if has_failure else "success"
    )
    execution.result_json = json.dumps(
        {
            "actions": action_results,
            "conditions_evaluated": True,
        },
        default=str,
    )
    execution.completed_at = datetime.utcnow()

    db.commit()

    return execution


# ============================================================
# EVENT DISPATCH (Phase 1: synchronous)
# ============================================================


def run_automations_for_event(
    db: Session,
    organization_id: int,
    store_id: int | None,
    event_type: str,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> list[AutomationExecution]:
    """
    Find and execute all active automations
    matching the event type.

    Phase 1: synchronous execution.
    """
    if event_type not in VALID_TRIGGER_TYPES:
        logger.warning(
            "Unknown event type: %s", event_type
        )
        return []

    query = (
        db.query(Automation)
        .filter(
            Automation.organization_id
            == organization_id,
            Automation.active.is_(True),
            Automation.trigger_type == event_type,
        )
    )

    if store_id:
        query = query.filter(
            (Automation.store_id == store_id)
            | (Automation.store_id.is_(None))
        )
    else:
        query = query.filter(
            Automation.store_id.is_(None)
        )

    automations = query.all()

    executions = []

    for automation in automations:
        try:
            execution = execute_automation(
                db=db,
                automation=automation,
                event_type=event_type,
                payload=payload,
                event_id=event_id,
            )
            executions.append(execution)
        except Exception as exc:
            logger.error(
                "Automation %d failed: %s",
                automation.id,
                _sanitize_error(exc),
                exc_info=True,
            )

    return executions


def emit_event(
    db: Session,
    organization_id: int,
    store_id: int | None,
    event_type: str,
    payload: dict[str, Any],
    event_id: str | None = None,
) -> list[AutomationExecution]:
    """
    Public API for dispatching events.

    Phase 1: synchronous.
    Phase 2+: queue-based.
    """
    return run_automations_for_event(
        db=db,
        organization_id=organization_id,
        store_id=store_id,
        event_type=event_type,
        payload=payload,
        event_id=event_id,
    )
