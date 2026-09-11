"""Application orchestration for Knowledge Base cleanup and deletion.

Legacy and modern deletion remain explicit, separate paths. Provider ownership
verification stays in the injected infrastructure operations; this module only
coordinates persistence, routing, cleanup, and customer-safe error behavior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from ..models import KnowledgeBase, KnowledgeSource
from .cleanup import CleanupResult
from .errors import BedrockProvisioningError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeletionOperations:
    """Runtime dependencies for Knowledge Base cleanup/deletion."""

    vector_index_arn: Callable[[int], str]
    cleanup_remote_resources: Callable[
        [int, int, str | None, str | None, str | None], CleanupResult
    ]
    commit_state: Callable[..., None]
    is_verified_legacy_parent: Callable[[str], bool]
    cleanup_verified_legacy_resources: Callable[[Session, KnowledgeBase], None]
    delete_knowledge_prefix: Callable[[int, int], None]
    client_error_code: Callable[[Exception], str | None]
    client_error_message: Callable[[Exception], str | None]
    client_error_request_id: Callable[[Exception], str | None]


def cleanup_owned_resources(
    db: Session,
    knowledge_base: KnowledgeBase,
    *,
    operations: DeletionOperations,
) -> None:
    """Safely clean owned modern resources without losing ambiguous IDs."""
    try:
        index_arn = operations.vector_index_arn(knowledge_base.id)
    except BedrockProvisioningError:
        index_arn = None

    result = operations.cleanup_remote_resources(
        knowledge_base.organization_id,
        knowledge_base.id,
        index_arn,
        knowledge_base.external_id,
        knowledge_base.external_data_source_id,
    )
    knowledge_base.external_id = result.bedrock_kb_id
    knowledge_base.external_data_source_id = result.bedrock_ds_id
    knowledge_base.external_status = "failed"
    knowledge_base.external_last_error = (
        "resources_cleaned" if result.succeeded else "cleanup_failed"
    )
    operations.commit_state(db, "failure_state_persist_failed")


def delete_knowledge_base(
    db: Session,
    knowledge_base: KnowledgeBase,
    *,
    operations: DeletionOperations,
) -> None:
    """Delete one Knowledge Base and only its verified owned resources."""
    claimed = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base.id,
            KnowledgeBase.organization_id == knowledge_base.organization_id,
            KnowledgeBase.external_status != "deleting",
        )
        .update(
            {
                KnowledgeBase.external_status: "deleting",
                KnowledgeBase.external_last_error: None,
                KnowledgeBase.provisioning_stage: "deleting",
                KnowledgeBase.provisioning_stage_started_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
    )
    operations.commit_state(db)
    db.refresh(knowledge_base)

    if not claimed and knowledge_base.external_status != "deleting":
        raise BedrockProvisioningError(
            "invalid_deletion_state", resource="knowledge_base"
        )

    org_id = knowledge_base.organization_id
    kb_id = knowledge_base.id

    if operations.is_verified_legacy_parent(knowledge_base.external_id or ""):
        logger.info(
            "knowledge_base_deletion_routing organization_id=%s knowledge_base_id=%s deletion_mode=legacy",
            org_id,
            kb_id,
        )
        try:
            operations.cleanup_verified_legacy_resources(db, knowledge_base)
            return
        except Exception as error:
            db.rollback()
            current = db.get(KnowledgeBase, kb_id)
            original_error_code = (
                error.code
                if isinstance(error, BedrockProvisioningError)
                else type(error).__name__
            )
            if current:
                current.external_status = "deleting"
                current.external_last_error = f"deletion_failed:{original_error_code}"
                current.provisioning_stage = "deleting"
                current.provisioning_stage_started_at = datetime.now(timezone.utc)
                operations.commit_state(db, "deletion_state_persist_failed")
            logger.exception(
                "knowledge_base_deletion_failed deletion_mode=legacy "
                "organization_id=%s knowledge_base_id=%s error_code=%s",
                org_id,
                kb_id,
                original_error_code,
            )
            if isinstance(error, BedrockProvisioningError):
                raise
            raise BedrockProvisioningError(
                "deletion_failed", resource="knowledge_base"
            ) from error

    logger.info(
        "knowledge_base_deletion_routing organization_id=%s knowledge_base_id=%s deletion_mode=modern",
        org_id,
        kb_id,
    )
    index_arn: str | None = None
    try:
        index_arn = operations.vector_index_arn(kb_id)
        cleanup = operations.cleanup_remote_resources(
            org_id,
            kb_id,
            index_arn,
            knowledge_base.external_id,
            knowledge_base.external_data_source_id,
        )
        if not cleanup.succeeded:
            if isinstance(cleanup.error, BedrockProvisioningError):
                raise cleanup.error
            raise BedrockProvisioningError(
                "deletion_cleanup_failed", resource="knowledge_base"
            ) from cleanup.error

        operations.delete_knowledge_prefix(org_id, kb_id)
        db.query(KnowledgeSource).filter(
            KnowledgeSource.organization_id == org_id,
            KnowledgeSource.knowledge_base_id == kb_id,
        ).delete(synchronize_session=False)
        db.delete(knowledge_base)
        operations.commit_state(db, "deletion_state_persist_failed")
    except Exception as error:
        db.rollback()
        current = db.get(KnowledgeBase, kb_id)
        original_error_code = (
            error.code
            if isinstance(error, BedrockProvisioningError)
            else type(error).__name__
        )
        if current:
            current.external_status = "deleting"
            current.external_last_error = f"deletion_failed:{original_error_code}"
            current.provisioning_stage = "deleting"
            current.provisioning_stage_started_at = datetime.now(timezone.utc)
            operations.commit_state(db, "deletion_state_persist_failed")
        logger.exception(
            "knowledge_base_deletion_failed deletion_mode=modern "
            "organization_id=%s knowledge_base_id=%s provisioning_stage=deleting "
            "error_code=%s aws_error_code=%s aws_error_message=%s "
            "aws_request_id=%s vector_index_arn=%s bedrock_kb_id=%s "
            "bedrock_data_source_id=%s",
            org_id,
            kb_id,
            original_error_code,
            operations.client_error_code(error),
            operations.client_error_message(error),
            operations.client_error_request_id(error),
            index_arn,
            knowledge_base.external_id,
            knowledge_base.external_data_source_id,
        )
        if isinstance(error, BedrockProvisioningError):
            raise
        raise BedrockProvisioningError(
            "deletion_failed", resource="knowledge_base"
        ) from error
