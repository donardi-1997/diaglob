"""HTTP dependency mapping the shared Knowledge domain authorization policy."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import KnowledgeBase, OrganizationMembership
from ..services.knowledge_bases import (
    KnowledgeBaseAccessError,
    KnowledgeBaseNotFoundError,
    get_authorized_knowledge_base,
)
from .deps import get_allowed_store_ids, get_current_membership


def require_authorized_knowledge_base(
    knowledge_base_id: int,
    request: Request,
    membership: OrganizationMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    try:
        return get_authorized_knowledge_base(
            db, membership.organization_id, knowledge_base_id,
            allowed_store_ids=get_allowed_store_ids(membership),
            write=request.method.upper() not in {"GET", "HEAD", "OPTIONS"},
            is_owner=membership.role == "owner",
        )
    except KnowledgeBaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
