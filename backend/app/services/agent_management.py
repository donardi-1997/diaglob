"""Tenant-safe domain service for AI agent CRUD and store/KB assignments.

This module deliberately does not issue provider requests or send messages.
"""

from sqlalchemy.orm import Session

from ..models import Agent, KnowledgeBase, OrganizationMembership, Store


class AgentNotFoundError(Exception):
    pass


class AgentAccessError(Exception):
    pass


class AgentValidationError(Exception):
    pass


def _allowed_ids(membership: OrganizationMembership) -> set[int] | None:
    if membership.all_stores:
        return None
    return {
        store.id
        for store in membership.stores
        if (
            store.organization_id == membership.organization_id
            and store.active
            and not store.deleted
        )
    }


def _visible(agent: Agent, allowed: set[int] | None) -> bool:
    return allowed is None or any(
        store.id in allowed and store.active and not store.deleted
        for store in agent.stores
    )


def list_agents(db: Session, membership: OrganizationMembership) -> list[Agent]:
    agents = (
        db.query(Agent)
        .filter(Agent.organization_id == membership.organization_id)
        .order_by(Agent.name.asc(), Agent.id.asc())
        .all()
    )
    allowed = _allowed_ids(membership)
    return [agent for agent in agents if _visible(agent, allowed)]


def _get_agent(
    db: Session,
    membership: OrganizationMembership,
    agent_id: int,
    *,
    for_write: bool = False,
) -> Agent:
    agent = (
        db.query(Agent)
        .filter(
            Agent.id == agent_id,
            Agent.organization_id == membership.organization_id,
        )
        .first()
    )
    allowed = _allowed_ids(membership)
    if not agent or not _visible(agent, allowed):
        raise AgentNotFoundError("Agent not found")
    if for_write and allowed is not None:
        # Never allow a restricted membership to overwrite assignments that
        # include stores it is not permitted to manage.
        if any(store.id not in allowed for store in agent.stores):
            raise AgentAccessError("Agent has stores outside your assignment")
    return agent


def serialize_agent(agent: Agent, membership: OrganizationMembership) -> dict:
    allowed = _allowed_ids(membership)
    stores = [
        store for store in agent.stores
        if allowed is None or store.id in allowed
    ]
    kbs = [
        kb for kb in agent.knowledge_bases
        if allowed is None or (
            kb.scope == "selected_stores"
            and any(store.id in allowed for store in kb.stores)
        )
    ]
    return {
        "id": agent.id,
        "organization_id": agent.organization_id,
        "name": agent.name,
        "role": agent.role,
        "active": agent.active,
        "stores": [
            {
                "id": store.id,
                "name": store.name,
                "country_code": store.country_code,
                "currency": store.currency,
            }
            for store in stores
        ],
        "knowledge_bases": [
            {
                "id": kb.id,
                "name": kb.name,
                "scope": kb.scope,
                "active": kb.active,
            }
            for kb in kbs
        ],
    }


def _resolve_stores(
    db: Session,
    membership: OrganizationMembership,
    store_ids: list[int],
    *,
    active: bool,
) -> list[Store]:
    ids = set(store_ids)
    if len(ids) != len(store_ids) or any(i <= 0 for i in ids):
        raise AgentValidationError("Invalid or duplicated store IDs")
    if active and not ids:
        raise AgentValidationError("Active agent requires an assigned store")
    allowed = _allowed_ids(membership)
    if allowed is not None and not ids:
        raise AgentValidationError("Assigned stores are required for this member")
    if allowed is not None and not ids.issubset(allowed):
        raise AgentAccessError("Store access denied")
    stores = (
        db.query(Store)
        .filter(
            Store.id.in_(ids),
            Store.organization_id == membership.organization_id,
            Store.active.is_(True),
            Store.deleted.is_(False),
        )
        .all()
    ) if ids else []
    if len(stores) != len(ids):
        raise AgentValidationError("Store is inactive, deleted, or unavailable")
    return stores


def _resolve_knowledge_bases(
    db: Session,
    membership: OrganizationMembership,
    kb_ids: list[int],
) -> list[KnowledgeBase]:
    ids = set(kb_ids)
    if len(ids) != len(kb_ids) or any(i <= 0 for i in ids):
        raise AgentValidationError("Invalid or duplicated knowledge base IDs")
    if not ids:
        return []
    kbs = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id.in_(ids),
            KnowledgeBase.organization_id == membership.organization_id,
            KnowledgeBase.active.is_(True),
        )
        .all()
    )
    if len(kbs) != len(ids):
        raise AgentValidationError("Knowledge base unavailable")
    allowed = _allowed_ids(membership)
    if allowed is not None:
        for kb in kbs:
            if kb.scope != "selected_stores" or not any(
                store.id in allowed and store.active and not store.deleted
                for store in kb.stores
            ):
                raise AgentAccessError("Knowledge base access denied")
    return kbs


def _valid_text(value: str, field: str, maximum: int) -> str:
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum:
        raise AgentValidationError(f"Invalid {field}")
    return cleaned


def create_agent(
    db: Session,
    membership: OrganizationMembership,
    *,
    name: str,
    role: str,
    active: bool,
    store_ids: list[int],
    knowledge_base_ids: list[int],
) -> Agent:
    name = _valid_text(name, "name", 150)
    role = _valid_text(role, "role", 50)
    stores = _resolve_stores(db, membership, store_ids, active=active)
    kbs = _resolve_knowledge_bases(db, membership, knowledge_base_ids)
    agent = Agent(
        organization_id=membership.organization_id,
        name=name,
        role=role,
        active=active,
    )
    agent.stores = stores
    agent.knowledge_bases = kbs
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def update_agent(
    db: Session,
    membership: OrganizationMembership,
    agent_id: int,
    *,
    updates: dict,
) -> Agent:
    agent = _get_agent(db, membership, agent_id, for_write=True)
    name = (
        _valid_text(updates["name"], "name", 150)
        if updates.get("name") is not None else agent.name
    )
    role = (
        _valid_text(updates["role"], "role", 50)
        if updates.get("role") is not None else agent.role
    )
    active = (
        updates["active"]
        if updates.get("active") is not None else agent.active
    )
    store_ids = (
        updates["store_ids"]
        if updates.get("store_ids") is not None
        else [store.id for store in agent.stores]
    )
    stores = _resolve_stores(
        db, membership, store_ids, active=active,
    )
    kbs = (
        _resolve_knowledge_bases(db, membership, updates["knowledge_base_ids"])
        if updates.get("knowledge_base_ids") is not None
        else agent.knowledge_bases
    )
    agent.name = name
    agent.role = role
    agent.active = active
    agent.stores = stores
    agent.knowledge_bases = list(kbs)
    db.commit()
    db.refresh(agent)
    return agent
