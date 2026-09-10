"""Manual sales-attribution corrections with immutable audit history."""
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..model_domains.sales_attribution import (
    OrderSalesAttribution,
    OrderSalesAttributionChange,
)
from ..models import Agent, Order, OrganizationMembership, User
from .sales_attribution import SalesAttributionError


MANUAL_SOURCE = "manual_reclassification"


def _require_order(
    db: Session,
    organization_id: int,
    store_id: int,
    order_id: int,
) -> Order:
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.organization_id == organization_id,
            Order.store_id == store_id,
        )
        .first()
    )
    if not order:
        raise SalesAttributionError("Order not found")
    return order


def _require_human_with_store_access(
    db: Session,
    organization_id: int,
    store_id: int,
    user_id: int,
    *,
    label: str,
) -> tuple[int, str]:
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.active.is_(True),
        )
        .first()
    )
    if not membership:
        raise SalesAttributionError(f"{label} is not an active organization member")

    if not membership.all_stores:
        allowed_store_ids = {store.id for store in membership.stores if not store.deleted}
        if store_id not in allowed_store_ids:
            raise SalesAttributionError(f"{label} does not have access to this store")

    user = db.query(User).filter(User.id == user_id, User.active.is_(True)).first()
    if not user:
        raise SalesAttributionError(f"{label} user not found")

    return user.id, (user.name or "").strip() or user.email


def _resolve_new_actor(
    db: Session,
    organization_id: int,
    store_id: int,
    actor_type: str,
    actor_id: int,
) -> tuple[int, str]:
    if actor_type == "human":
        return _require_human_with_store_access(
            db,
            organization_id,
            store_id,
            actor_id,
            label="Human closer",
        )

    if actor_type == "ai":
        agent = (
            db.query(Agent)
            .filter(
                Agent.id == actor_id,
                Agent.organization_id == organization_id,
                Agent.active.is_(True),
            )
            .first()
        )
        if not agent:
            raise SalesAttributionError("AI closer is not an active organization agent")

        allowed_store_ids = {store.id for store in agent.stores if store.active}
        if store_id not in allowed_store_ids:
            raise SalesAttributionError("AI closer does not belong to this store")

        return agent.id, agent.name

    raise SalesAttributionError("actor_type must be human, ai, or null")


def _actor_id(attribution: OrderSalesAttribution | None) -> int | None:
    if attribution is None:
        return None
    if attribution.actor_type == "human":
        return attribution.human_user_id
    return attribution.ai_agent_id


def _serialize(attribution: OrderSalesAttribution | None) -> dict[str, Any] | None:
    if attribution is None:
        return None
    return {
        "actor_type": attribution.actor_type,
        "actor_id": _actor_id(attribution),
        "actor_label": attribution.actor_label,
        "human_user_id": attribution.human_user_id,
        "ai_agent_id": attribution.ai_agent_id,
        "conversation_id": attribution.conversation_id,
        "source": attribution.source,
    }


def set_manual_order_attribution(
    db: Session,
    organization_id: int,
    store_id: int,
    order_id: int,
    *,
    changed_by_user_id: int,
    actor_type: str | None,
    actor_id: int | None,
) -> dict[str, Any] | None:
    """Assign, reassign, or clear one order attribution atomically.

    ``actor_type=None`` with ``actor_id=None`` clears the current attribution.
    Every effective manual change writes an immutable audit record in the same
    transaction as the current-attribution update.
    """
    _require_order(db, organization_id, store_id, order_id)
    changer_id, changer_label = _require_human_with_store_access(
        db,
        organization_id,
        store_id,
        changed_by_user_id,
        label="Attribution editor",
    )

    current = (
        db.query(OrderSalesAttribution)
        .filter(
            OrderSalesAttribution.organization_id == organization_id,
            OrderSalesAttribution.store_id == store_id,
            OrderSalesAttribution.order_id == order_id,
        )
        .first()
    )

    previous_type = current.actor_type if current else None
    previous_id = _actor_id(current)
    previous_label = current.actor_label if current else None

    if actor_type is None:
        if actor_id is not None:
            raise SalesAttributionError("actor_id must be null when clearing attribution")
        if current is None:
            return None

        audit = OrderSalesAttributionChange(
            organization_id=organization_id,
            store_id=store_id,
            order_id=order_id,
            changed_by_user_id=changer_id,
            changed_by_label=changer_label,
            action="clear",
            previous_actor_type=previous_type,
            previous_actor_id=previous_id,
            previous_actor_label=previous_label,
            new_actor_type=None,
            new_actor_id=None,
            new_actor_label=None,
        )
        db.add(audit)
        db.delete(current)
        db.commit()
        return None

    if actor_id is None:
        raise SalesAttributionError("actor_id is required for human or ai attribution")

    new_id, new_label = _resolve_new_actor(
        db,
        organization_id,
        store_id,
        actor_type,
        actor_id,
    )

    if current is not None and previous_type == actor_type and previous_id == new_id:
        return _serialize(current)

    now = datetime.utcnow()
    action = "reassign" if current is not None else "assign"

    if current is None:
        current = OrderSalesAttribution(
            organization_id=organization_id,
            store_id=store_id,
            order_id=order_id,
            actor_type=actor_type,
            actor_label=new_label,
            human_user_id=new_id if actor_type == "human" else None,
            ai_agent_id=new_id if actor_type == "ai" else None,
            conversation_id=None,
            source=MANUAL_SOURCE,
            created_at=now,
            updated_at=now,
        )
        db.add(current)
    else:
        current.actor_type = actor_type
        current.actor_label = new_label
        current.human_user_id = new_id if actor_type == "human" else None
        current.ai_agent_id = new_id if actor_type == "ai" else None
        current.conversation_id = None
        current.source = MANUAL_SOURCE
        current.updated_at = now

    db.add(
        OrderSalesAttributionChange(
            organization_id=organization_id,
            store_id=store_id,
            order_id=order_id,
            changed_by_user_id=changer_id,
            changed_by_label=changer_label,
            action=action,
            previous_actor_type=previous_type,
            previous_actor_id=previous_id,
            previous_actor_label=previous_label,
            new_actor_type=actor_type,
            new_actor_id=new_id,
            new_actor_label=new_label,
            created_at=now,
        )
    )

    db.commit()
    db.refresh(current)
    return _serialize(current)


def get_order_attribution_history(
    db: Session,
    organization_id: int,
    store_id: int,
    order_id: int,
) -> list[dict[str, Any]]:
    """Return newest-first manual correction history for one scoped order."""
    _require_order(db, organization_id, store_id, order_id)
    rows = (
        db.query(OrderSalesAttributionChange)
        .filter(
            OrderSalesAttributionChange.organization_id == organization_id,
            OrderSalesAttributionChange.store_id == store_id,
            OrderSalesAttributionChange.order_id == order_id,
        )
        .order_by(OrderSalesAttributionChange.created_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "action": row.action,
            "changed_by_user_id": row.changed_by_user_id,
            "changed_by_label": row.changed_by_label,
            "previous_actor_type": row.previous_actor_type,
            "previous_actor_id": row.previous_actor_id,
            "previous_actor_label": row.previous_actor_label,
            "new_actor_type": row.new_actor_type,
            "new_actor_id": row.new_actor_id,
            "new_actor_label": row.new_actor_label,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
