"""Knowledge Base CRUD lifecycle service.

KB query/orchestration, scope rules, store assignment,
create/update lifecycle, delete lifecycle, DB transactions,
and provisioning scheduling decisions.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..bedrock_knowledge_base import (
    BedrockProvisioningError,
    delete_diaglob_knowledge_base,
)
from ..models import KnowledgeBase, Store

logger = logging.getLogger(__name__)


# ============================================================
# DOMAIN EXCEPTIONS
# ============================================================


class KnowledgeBaseNotFoundError(Exception):
    """Knowledge Base not found within organization."""


class InvalidKnowledgeBaseScopeError(Exception):
    """Scope value is not allowed."""


class KnowledgeBaseAccessError(Exception):
    """Organization-wide KB requires all-store access."""


class InvalidStoreSelectionError(Exception):
    """Selected-store KB requires at least one valid store."""


# ============================================================
# LIST
# ============================================================


def list_knowledge_bases(
    db: Session,
    organization_id: int,
) -> list[KnowledgeBase]:
    """Return all knowledge bases for the organization, ordered by name."""
    return (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.organization_id == organization_id,
        )
        .order_by(KnowledgeBase.name.asc())
        .all()
    )


# ============================================================
# GET
# ============================================================


def get_knowledge_base(
    db: Session,
    organization_id: int,
    knowledge_base_id: int,
) -> KnowledgeBase:
    """Locate a knowledge base by ID within the organization.

    Raises KnowledgeBaseNotFoundError if not found.
    """
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id == organization_id,
        )
        .first()
    )
    if not knowledge_base:
        raise KnowledgeBaseNotFoundError(
            "Knowledge base not found",
        )
    return knowledge_base


# ============================================================
# CREATE
# ============================================================


def create_knowledge_base(
    db: Session,
    *,
    organization_id: int,
    name: str,
    scope: str,
    active: bool,
    store_ids: list[int],
    is_owner: bool,
    all_stores: bool,
    resolve_stores_fn,
) -> KnowledgeBase:
    """Create a new KnowledgeBase with validation and store assignment.

    Parameters
    ----------
    resolve_stores_fn:
        Callable(membership, store_ids, db) -> list[Store].
        Injected by the API layer to avoid importing deps.
    """
    name = name.strip()
    scope = scope.strip()

    if not name:
        raise InvalidKnowledgeBaseScopeError(
            "Knowledge base name is required",
        )

    if scope not in {"organization", "selected_stores"}:
        raise InvalidKnowledgeBaseScopeError(
            "Invalid knowledge base scope",
        )

    if (
        scope == "organization"
        and not all_stores
        and not is_owner
    ):
        raise KnowledgeBaseAccessError(
            "Organization-wide knowledge bases "
            "require all-store access",
        )

    if scope == "organization":
        stores = []
    else:
        stores = resolve_stores_fn(store_ids)

        if not stores:
            raise InvalidStoreSelectionError(
                "Selected-store knowledge bases "
                "require at least one store",
            )

    knowledge_base = KnowledgeBase(
        organization_id=organization_id,
        name=name,
        scope=scope,
        external_status="pending",
        provisioning_stage="queued",
        provisioning_started_at=datetime.now(timezone.utc),
        provisioning_stage_started_at=datetime.now(timezone.utc),
        active=active,
    )

    knowledge_base.stores = stores

    db.add(knowledge_base)
    db.commit()
    db.refresh(knowledge_base)

    # Analytics: knowledge created
    from .product_analytics import track_knowledge_created
    track_knowledge_created(
        user_id=0,  # No user context in service
        organization_id=organization_id,
        kb_id=knowledge_base.id,
    )

    return knowledge_base


# ============================================================
# UPDATE
# ============================================================


def update_knowledge_base(
    db: Session,
    knowledge_base: KnowledgeBase,
    *,
    name: str | None = None,
    scope: str | None = None,
    active: bool | None = None,
    store_ids: list[int] | None = None,
    is_owner: bool,
    all_stores: bool,
    resolve_stores_fn=None,
) -> KnowledgeBase:
    """Apply partial updates to a KnowledgeBase.

    Parameters
    ----------
    resolve_stores_fn:
        Callable(membership, store_ids, db) -> list[Store].
        Only called when store_ids is not None and scope is selected_stores.
    """
    if name is not None:
        name = name.strip()
        if not name:
            raise InvalidKnowledgeBaseScopeError(
                "Knowledge base name is required",
            )
        knowledge_base.name = name

    next_scope = (
        scope.strip()
        if scope is not None
        else knowledge_base.scope
    )

    if next_scope not in {"organization", "selected_stores"}:
        raise InvalidKnowledgeBaseScopeError(
            "Invalid knowledge base scope",
        )

    if (
        next_scope == "organization"
        and not all_stores
        and not is_owner
    ):
        raise KnowledgeBaseAccessError(
            "Organization-wide knowledge bases "
            "require all-store access",
        )

    knowledge_base.scope = next_scope

    if active is not None:
        knowledge_base.active = active

    if next_scope == "organization":
        knowledge_base.stores = []

    elif store_ids is not None and resolve_stores_fn is not None:
        stores = resolve_stores_fn(store_ids)

        if not stores:
            raise InvalidStoreSelectionError(
                "Selected-store knowledge bases "
                "require at least one store",
            )

        knowledge_base.stores = stores

    db.commit()
    db.refresh(knowledge_base)

    return knowledge_base


# ============================================================
# DELETE
# ============================================================


def delete_knowledge_base(
    db: Session,
    knowledge_base: KnowledgeBase,
) -> None:
    """Delete a KnowledgeBase including external Bedrock resources.

    Raises BedrockProvisioningError if external deletion fails.
    """
    delete_diaglob_knowledge_base(db, knowledge_base)

    logger.info(
        "Knowledge Base deleted: organization_id=%s knowledge_base_id=%s",
        knowledge_base.organization_id,
        knowledge_base.id,
    )


# ============================================================
# RETRY PROVISIONING
# ============================================================


def retry_knowledge_base_provisioning(
    db: Session,
    knowledge_base: KnowledgeBase,
) -> KnowledgeBase:
    """Validate and transition to retrying state.

    Raises KnowledgeBaseNotFoundError if not found (should not happen if called after get).
    Raises InvalidKnowledgeBaseScopeError if status does not allow retry.
    Raises KnowledgeBaseAccessError if provisioning state changed concurrently.
    """
    if knowledge_base.external_status in ("provisioning", "retrying"):
        raise InvalidKnowledgeBaseScopeError(
            "Knowledge Base provisioning is already in progress.",
        )

    if knowledge_base.external_status not in ("pending", "failed"):
        raise InvalidKnowledgeBaseScopeError(
            f"Cannot retry provisioning for KnowledgeBase with status: {knowledge_base.external_status}",
        )

    previous_status = knowledge_base.external_status
    logger.info(
        "knowledge_base_manual_retry_requested organization_id=%s knowledge_base_id=%s previous_status=%s",
        knowledge_base.organization_id,
        knowledge_base.id,
        previous_status,
    )

    now = datetime.now(timezone.utc)
    updated = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base.id,
            KnowledgeBase.organization_id == knowledge_base.organization_id,
            KnowledgeBase.external_status == previous_status,
        )
        .update(
            {
                KnowledgeBase.external_status: "retrying",
                KnowledgeBase.external_last_error: None,
                KnowledgeBase.provisioning_stage: "queued",
                KnowledgeBase.provisioning_started_at: now,
                KnowledgeBase.provisioning_stage_started_at: now,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        db.refresh(knowledge_base)
        raise KnowledgeBaseAccessError(
            "Knowledge Base provisioning state changed. Try again.",
        )

    db.commit()
    db.refresh(knowledge_base)

    logger.info(
        "knowledge_base_manual_retry_scheduled organization_id=%s knowledge_base_id=%s previous_status=%s status=%s stage=%s",
        knowledge_base.organization_id,
        knowledge_base.id,
        previous_status,
        knowledge_base.external_status,
        knowledge_base.provisioning_stage,
    )

    return knowledge_base
