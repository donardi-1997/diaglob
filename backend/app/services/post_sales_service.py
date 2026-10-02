"""Post-sales case orchestration.

Cases are tenant/store scoped and link back to real orders/customers whenever
possible. Lifecycle changes emit automation events after persistence.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..automations import safe_emit_event
from ..model_domains.post_sales import PostSalesCase, PostSalesCaseEvent
from ..models import Agent, Conversation, Customer, Order, Store


CASE_TYPES = {
    "warranty",
    "return",
    "refund",
    "damaged",
    "wrong_product",
    "delivery_issue",
    "other",
}
STATUSES = {
    "open",
    "waiting_customer",
    "investigating",
    "approved",
    "rejected",
    "resolved",
    "closed",
}
PRIORITIES = {"low", "normal", "high", "urgent"}

ALLOWED_STATUS_TRANSITIONS = {
    "open": {"waiting_customer", "investigating", "approved", "rejected", "resolved", "closed"},
    "waiting_customer": {"open", "investigating", "approved", "rejected", "resolved", "closed"},
    "investigating": {"waiting_customer", "approved", "rejected", "resolved", "closed"},
    "approved": {"resolved", "closed"},
    "rejected": {"resolved", "closed"},
    "resolved": {"closed"},
    "closed": set(),
}


class PostSalesError(Exception):
    pass


class PostSalesNotFoundError(PostSalesError):
    pass


class PostSalesValidationError(PostSalesError):
    pass


def _store_or_error(db: Session, organization_id: int, store_id: int) -> Store:
    store = db.query(Store).filter(
        Store.id == store_id,
        Store.organization_id == organization_id,
        Store.deleted.is_(False),
    ).first()
    if not store:
        raise PostSalesNotFoundError("Store not found")
    return store


def _case_or_error(
    db: Session,
    organization_id: int,
    store_id: int,
    case_id: int,
) -> PostSalesCase:
    case = db.query(PostSalesCase).filter(
        PostSalesCase.id == case_id,
        PostSalesCase.organization_id == organization_id,
        PostSalesCase.store_id == store_id,
    ).first()
    if not case:
        raise PostSalesNotFoundError("Post-sales case not found")
    return case


def _serialize_event(event: PostSalesCaseEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "note": event.note,
        "metadata": event.event_metadata or {},
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


def _serialize_case(case: PostSalesCase, *, include_events: bool = False, db: Session | None = None) -> dict[str, Any]:
    payload = {
        "id": case.id,
        "organization_id": case.organization_id,
        "store_id": case.store_id,
        "order_id": case.order_id,
        "customer_id": case.customer_id,
        "assigned_agent_id": case.assigned_agent_id,
        "case_type": case.case_type,
        "status": case.status,
        "priority": case.priority,
        "title": case.title,
        "description": case.description,
        "resolution": case.resolution,
        "amount": float(case.amount) if case.amount is not None else None,
        "currency": case.currency,
        "evidence_refs": case.evidence_refs or [],
        "source_channel": case.source_channel,
        "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
    }
    if include_events and db is not None:
        events = db.query(PostSalesCaseEvent).filter(
            PostSalesCaseEvent.case_id == case.id,
            PostSalesCaseEvent.organization_id == case.organization_id,
        ).order_by(PostSalesCaseEvent.created_at, PostSalesCaseEvent.id).all()
        payload["events"] = [_serialize_event(event) for event in events]
    return payload


def _add_event(
    db: Session,
    case: PostSalesCase,
    *,
    actor_user_id: int | None,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
    metadata: dict | None = None,
) -> PostSalesCaseEvent:
    event = PostSalesCaseEvent(
        case_id=case.id,
        organization_id=case.organization_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        note=(note or "").strip() or None,
        event_metadata=metadata or {},
    )
    db.add(event)
    return event


def _automation_payload(db: Session, case: PostSalesCase) -> dict[str, Any]:
    conversation = None
    if case.customer_id:
        conversation = db.query(Conversation).filter(
            Conversation.organization_id == case.organization_id,
            Conversation.store_id == case.store_id,
            Conversation.customer_id == case.customer_id,
        ).order_by(Conversation.updated_at.desc(), Conversation.id.desc()).first()

    return {
        "case_id": case.id,
        "case_type": case.case_type,
        "case_status": case.status,
        "case_priority": case.priority,
        "order_id": case.order_id,
        "customer_id": case.customer_id,
        "conversation_id": conversation.id if conversation else None,
        "customer": {
            "id": case.customer_id,
        },
        "post_sales": {
            "id": case.id,
            "type": case.case_type,
            "status": case.status,
            "priority": case.priority,
            "title": case.title,
        },
    }


def list_cases(
    db: Session,
    organization_id: int,
    store_id: int,
    *,
    status: str | None = None,
    case_type: str | None = None,
    priority: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    _store_or_error(db, organization_id, store_id)
    query = db.query(PostSalesCase).filter(
        PostSalesCase.organization_id == organization_id,
        PostSalesCase.store_id == store_id,
    )
    if status:
        if status not in STATUSES:
            raise PostSalesValidationError("Invalid status")
        query = query.filter(PostSalesCase.status == status)
    if case_type:
        if case_type not in CASE_TYPES:
            raise PostSalesValidationError("Invalid case type")
        query = query.filter(PostSalesCase.case_type == case_type)
    if priority:
        if priority not in PRIORITIES:
            raise PostSalesValidationError("Invalid priority")
        query = query.filter(PostSalesCase.priority == priority)
    items = query.order_by(
        PostSalesCase.updated_at.desc(),
        PostSalesCase.id.desc(),
    ).limit(max(1, min(limit, 200))).all()
    return [_serialize_case(item) for item in items]


def get_case(
    db: Session,
    organization_id: int,
    store_id: int,
    case_id: int,
) -> dict[str, Any]:
    case = _case_or_error(db, organization_id, store_id, case_id)
    return _serialize_case(case, include_events=True, db=db)


def get_summary(db: Session, organization_id: int, store_id: int) -> dict[str, Any]:
    _store_or_error(db, organization_id, store_id)
    cases = db.query(PostSalesCase).filter(
        PostSalesCase.organization_id == organization_id,
        PostSalesCase.store_id == store_id,
    ).all()
    open_statuses = {"open", "waiting_customer", "investigating", "approved", "rejected"}
    return {
        "total": len(cases),
        "open": sum(1 for item in cases if item.status in open_statuses),
        "urgent": sum(1 for item in cases if item.priority == "urgent" and item.status in open_statuses),
        "waiting_customer": sum(1 for item in cases if item.status == "waiting_customer"),
        "resolved": sum(1 for item in cases if item.status in {"resolved", "closed"}),
        "by_type": {
            case_type: sum(1 for item in cases if item.case_type == case_type)
            for case_type in sorted(CASE_TYPES)
        },
    }


def create_case(
    db: Session,
    organization_id: int,
    store_id: int,
    actor_user_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    store = _store_or_error(db, organization_id, store_id)
    case_type = str(payload.get("case_type") or "").strip().lower()
    priority = str(payload.get("priority") or "normal").strip().lower()
    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()

    if case_type not in CASE_TYPES:
        raise PostSalesValidationError("Invalid case type")
    if priority not in PRIORITIES:
        raise PostSalesValidationError("Invalid priority")
    if not title:
        raise PostSalesValidationError("Title is required")
    if len(title) > 240:
        raise PostSalesValidationError("Title is too long")
    if len(description) > 5000:
        raise PostSalesValidationError("Description is too long")

    order = None
    order_id = payload.get("order_id")
    if order_id is not None:
        order = db.query(Order).filter(
            Order.id == int(order_id),
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        ).first()
        if not order:
            raise PostSalesValidationError("Order does not belong to this store")

    customer_id = payload.get("customer_id")
    if customer_id is None and order is not None:
        customer_id = order.customer_id
    if customer_id is not None:
        customer = db.query(Customer).filter(
            Customer.id == int(customer_id),
            Customer.organization_id == organization_id,
        ).first()
        if not customer:
            raise PostSalesValidationError("Customer not found")
        if order is not None and order.customer_id and order.customer_id != customer.id:
            raise PostSalesValidationError("Customer does not match order")
        customer_id = customer.id

    evidence_refs = payload.get("evidence_refs") or []
    if not isinstance(evidence_refs, list) or len(evidence_refs) > 20:
        raise PostSalesValidationError("Evidence references must be a list with at most 20 items")
    evidence_refs = [str(item).strip()[:1000] for item in evidence_refs if str(item).strip()]

    case = PostSalesCase(
        organization_id=organization_id,
        store_id=store_id,
        order_id=order.id if order else None,
        customer_id=customer_id,
        created_by_user_id=actor_user_id,
        case_type=case_type,
        status="open",
        priority=priority,
        title=title,
        description=description,
        amount=payload.get("amount"),
        currency=(payload.get("currency") or (order.currency if order else store.currency)),
        evidence_refs=evidence_refs,
        source_channel=(payload.get("source_channel") or None),
    )
    db.add(case)
    db.flush()
    _add_event(
        db,
        case,
        actor_user_id=actor_user_id,
        event_type="case_created",
        to_status="open",
    )
    db.commit()
    db.refresh(case)

    safe_emit_event(
        db,
        organization_id,
        store_id,
        "post_sales.case_created",
        _automation_payload(db, case),
        event_id=f"post_sales_case:{case.id}:created",
    )
    return _serialize_case(case, include_events=True, db=db)


def update_case(
    db: Session,
    organization_id: int,
    store_id: int,
    case_id: int,
    actor_user_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    case = _case_or_error(db, organization_id, store_id, case_id)
    previous_status = case.status

    if payload.get("status") is not None:
        next_status = str(payload["status"]).strip().lower()
        if next_status not in STATUSES:
            raise PostSalesValidationError("Invalid status")
        if next_status != case.status and next_status not in ALLOWED_STATUS_TRANSITIONS.get(case.status, set()):
            raise PostSalesValidationError(
                f"Invalid status transition: {case.status} -> {next_status}"
            )
        case.status = next_status
        if next_status in {"resolved", "closed"} and case.resolved_at is None:
            case.resolved_at = datetime.utcnow()

    if payload.get("priority") is not None:
        priority = str(payload["priority"]).strip().lower()
        if priority not in PRIORITIES:
            raise PostSalesValidationError("Invalid priority")
        case.priority = priority

    if "resolution" in payload:
        resolution = str(payload.get("resolution") or "").strip()
        if len(resolution) > 5000:
            raise PostSalesValidationError("Resolution is too long")
        case.resolution = resolution or None

    if "assigned_agent_id" in payload:
        assigned_agent_id = payload.get("assigned_agent_id")
        if assigned_agent_id is None:
            case.assigned_agent_id = None
        else:
            agent = db.query(Agent).filter(
                Agent.id == int(assigned_agent_id),
                Agent.organization_id == organization_id,
                Agent.active.is_(True),
                Agent.stores.any(Store.id == store_id),
            ).first()
            if not agent:
                raise PostSalesValidationError(
                    "Assigned agent is not active for this store"
                )
            case.assigned_agent_id = agent.id

    case.updated_at = datetime.utcnow()
    event_type = "status_changed" if case.status != previous_status else "case_updated"
    _add_event(
        db,
        case,
        actor_user_id=actor_user_id,
        event_type=event_type,
        from_status=previous_status if case.status != previous_status else None,
        to_status=case.status if case.status != previous_status else None,
        note=payload.get("note"),
    )
    db.commit()
    db.refresh(case)

    emitted = "post_sales.case_resolved" if case.status in {"resolved", "closed"} else "post_sales.case_updated"
    safe_emit_event(
        db,
        organization_id,
        store_id,
        emitted,
        _automation_payload(db, case),
        event_id=f"post_sales_case:{case.id}:{case.updated_at.isoformat()}",
    )
    return _serialize_case(case, include_events=True, db=db)


def add_note(
    db: Session,
    organization_id: int,
    store_id: int,
    case_id: int,
    actor_user_id: int,
    note: str,
) -> dict[str, Any]:
    case = _case_or_error(db, organization_id, store_id, case_id)
    clean = note.strip()
    if not clean:
        raise PostSalesValidationError("Note is required")
    if len(clean) > 3000:
        raise PostSalesValidationError("Note is too long")
    _add_event(
        db,
        case,
        actor_user_id=actor_user_id,
        event_type="note_added",
        note=clean,
    )
    case.updated_at = datetime.utcnow()
    db.commit()
    return get_case(db, organization_id, store_id, case_id)
