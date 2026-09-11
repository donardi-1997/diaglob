"""Transactional lifecycle state for Knowledge Base provisioning."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import KnowledgeBase
from .errors import BedrockProvisioningError, ProvisioningInProgressError

logger = logging.getLogger(__name__)


def _commit_state(
    db: Session,
    error_code: str = "database_state_persist_failed",
) -> None:
    """Commit lifecycle state and translate persistence failures safely."""
    try:
        db.commit()
    except Exception as error:
        db.rollback()
        logger.exception("Failed to persist Knowledge Base provisioning state")
        raise BedrockProvisioningError(error_code, resource="database") from error


def _as_utc(value: datetime) -> datetime:
    """Normalize a naive or aware timestamp to an aware UTC value."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _set_provisioning_stage(
    db: Session,
    knowledge_base: KnowledgeBase,
    stage: str,
) -> None:
    """Persist a customer-safe lifecycle checkpoint and its timing."""
    now = datetime.now(timezone.utc)
    previous_stage = knowledge_base.provisioning_stage
    previous_started_at = knowledge_base.provisioning_stage_started_at
    if knowledge_base.provisioning_started_at is None:
        knowledge_base.provisioning_started_at = now
    knowledge_base.provisioning_stage = stage
    knowledge_base.provisioning_stage_started_at = now
    _commit_state(db)
    logger.info(
        "knowledge_base_provisioning_stage organization_id=%s "
        "knowledge_base_id=%s stage=%s previous_stage=%s "
        "stage_duration_seconds=%s total_duration_seconds=%s",
        knowledge_base.organization_id,
        knowledge_base.id,
        stage,
        previous_stage,
        round((now - _as_utc(previous_started_at)).total_seconds(), 3)
        if previous_started_at
        else None,
        round(
            (now - _as_utc(knowledge_base.provisioning_started_at)).total_seconds(),
            3,
        ),
    )


def _claim_provisioning(
    db: Session,
    knowledge_base: KnowledgeBase,
) -> None:
    """Atomically claim a non-terminal provisioning attempt."""
    previous_status = knowledge_base.external_status
    now = datetime.now(timezone.utc)
    claim_values: dict[object, object] = {
        KnowledgeBase.external_status: "provisioning",
        KnowledgeBase.external_last_error: None,
        KnowledgeBase.provisioning_stage: "creating_vector_index",
        KnowledgeBase.provisioning_stage_started_at: now,
    }
    if previous_status == "failed" or knowledge_base.provisioning_started_at is None:
        claim_values[KnowledgeBase.provisioning_started_at] = now
    updated = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base.id,
            KnowledgeBase.organization_id == knowledge_base.organization_id,
            KnowledgeBase.external_status.in_(("pending", "retrying", "failed")),
        )
        .update(
            claim_values,
            synchronize_session=False,
        )
    )
    _commit_state(db)
    db.refresh(knowledge_base)
    if updated == 1:
        logger.info(
            "knowledge_base_provisioning_claimed organization_id=%s "
            "knowledge_base_id=%s previous_status=%s status=%s stage=%s",
            knowledge_base.organization_id,
            knowledge_base.id,
            previous_status,
            knowledge_base.external_status,
            knowledge_base.provisioning_stage,
        )
        return
    if knowledge_base.external_status == "provisioning":
        raise ProvisioningInProgressError()
    raise BedrockProvisioningError(
        "invalid_provisioning_state",
        resource="knowledge_base",
    )


__all__ = [
    "_as_utc",
    "_claim_provisioning",
    "_commit_state",
    "_set_provisioning_stage",
]
