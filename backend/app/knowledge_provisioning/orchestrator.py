"""Application orchestration for isolated Knowledge Base provisioning.

Provider details, transactional state helpers, and compensating cleanup are
supplied explicitly by the caller. This keeps the orchestration deterministic
and preserves the facade's historical monkeypatch seams without coupling this
module back to AWS SDK construction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..models import KnowledgeBase
from .cleanup import CleanupResult
from .errors import BedrockProvisioningError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProvisioningOperations:
    """Runtime dependencies used by the provisioning state machine."""

    claim_provisioning: Callable[[Session, KnowledgeBase], None]
    create_vector_index: Callable[[int, int], dict[str, Any]]
    set_stage: Callable[[Session, KnowledgeBase, str], None]
    get_knowledge_base: Callable[[str], dict[str, Any] | None]
    wait_for_knowledge_base: Callable[[str, int, int, str], dict[str, Any]]
    create_knowledge_base: Callable[..., dict[str, Any]]
    commit_state: Callable[..., None]
    get_data_source: Callable[[str, str], dict[str, Any] | None]
    wait_for_data_source: Callable[[str, str, int, int], dict[str, Any]]
    create_data_source: Callable[..., dict[str, Any]]
    cleanup_remote_resources: Callable[
        [int, int, str | None, str | None, str | None], CleanupResult
    ]
    as_utc: Callable[[datetime], datetime]


def provision_knowledge_base(
    db: Session,
    knowledge_base: KnowledgeBase,
    *,
    operations: ProvisioningOperations,
) -> tuple[str, str]:
    """Provision one isolated vector index, Bedrock KB, and Data Source.

    This is the historical Diaglob provisioning state machine moved behind an
    explicit application boundary. Ordering, persistence checkpoints, cleanup
    behavior, and customer-safe error translation intentionally remain unchanged.
    """
    if knowledge_base.external_status == "ready":
        if knowledge_base.external_id and knowledge_base.external_data_source_id:
            return knowledge_base.external_id, knowledge_base.external_data_source_id
        raise BedrockProvisioningError(
            "ready_resource_ids_missing", resource="knowledge_base"
        )

    operations.claim_provisioning(db, knowledge_base)
    org_id = knowledge_base.organization_id
    kb_id = knowledge_base.id
    logger.info(
        "knowledge_base_provisioning_started organization_id=%s knowledge_base_id=%s stage=%s",
        org_id,
        kb_id,
        knowledge_base.provisioning_stage,
    )
    index_arn: str | None = None
    bedrock_kb_id = knowledge_base.external_id
    bedrock_ds_id = knowledge_base.external_data_source_id
    failure: BedrockProvisioningError | None = None

    try:
        vector_index = operations.create_vector_index(org_id, kb_id)
        index_arn = vector_index["indexArn"]

        operations.set_stage(db, knowledge_base, "creating_knowledge_base")
        if bedrock_kb_id:
            remote_kb = operations.get_knowledge_base(bedrock_kb_id)
            if remote_kb is None:
                bedrock_kb_id = None
                bedrock_ds_id = None
                knowledge_base.external_id = None
                knowledge_base.external_data_source_id = None
                operations.commit_state(db)
            else:
                operations.wait_for_knowledge_base(
                    bedrock_kb_id, org_id, kb_id, index_arn
                )

        if not bedrock_kb_id:
            remote_kb = operations.create_knowledge_base(
                org_id=org_id,
                kb_id=kb_id,
                index_arn=index_arn,
            )
            bedrock_kb_id = remote_kb.get("knowledgeBaseId")
            if not bedrock_kb_id:
                raise BedrockProvisioningError(
                    "bedrock_kb_create_failed", resource="knowledge_base"
                )
            knowledge_base.external_id = bedrock_kb_id
            operations.commit_state(db)
            operations.wait_for_knowledge_base(
                bedrock_kb_id, org_id, kb_id, index_arn
            )

        operations.set_stage(db, knowledge_base, "creating_data_source")
        if bedrock_ds_id:
            remote_ds = operations.get_data_source(bedrock_kb_id, bedrock_ds_id)
            if remote_ds is None:
                bedrock_ds_id = None
                knowledge_base.external_data_source_id = None
                operations.commit_state(db)
            else:
                operations.wait_for_data_source(
                    bedrock_kb_id, bedrock_ds_id, org_id, kb_id
                )

        if not bedrock_ds_id:
            remote_ds = operations.create_data_source(
                bedrock_kb_id=bedrock_kb_id,
                org_id=org_id,
                kb_id=kb_id,
            )
            bedrock_ds_id = remote_ds.get("dataSourceId")
            if not bedrock_ds_id:
                raise BedrockProvisioningError(
                    "bedrock_data_source_create_failed", resource="data_source"
                )
            knowledge_base.external_data_source_id = bedrock_ds_id
            operations.commit_state(db)
            operations.wait_for_data_source(
                bedrock_kb_id, bedrock_ds_id, org_id, kb_id
            )

        operations.set_stage(db, knowledge_base, "finalizing")
        knowledge_base.external_status = "ready"
        knowledge_base.external_last_error = None
        knowledge_base.provisioning_stage = "ready"
        knowledge_base.provisioning_stage_started_at = datetime.now(timezone.utc)
        operations.commit_state(db)
        logger.info(
            "knowledge_base_provisioning_completed organization_id=%s knowledge_base_id=%s total_duration_seconds=%s",
            org_id,
            kb_id,
            round(
                (
                    datetime.now(timezone.utc)
                    - operations.as_utc(knowledge_base.provisioning_started_at)
                ).total_seconds(),
                3,
            )
            if knowledge_base.provisioning_started_at
            else None,
        )
        return bedrock_kb_id, bedrock_ds_id
    except BedrockProvisioningError as error:
        failure = error
    except Exception as error:
        logger.exception("Unexpected Bedrock provisioning failure")
        failure = BedrockProvisioningError("provisioning_failed")

    db.rollback()
    cleanup = operations.cleanup_remote_resources(
        org_id,
        kb_id,
        index_arn,
        bedrock_kb_id,
        bedrock_ds_id,
    )
    knowledge_base.external_id = cleanup.bedrock_kb_id
    knowledge_base.external_data_source_id = cleanup.bedrock_ds_id
    knowledge_base.external_status = "failed"
    knowledge_base.provisioning_stage = "failed"
    knowledge_base.provisioning_stage_started_at = datetime.now(timezone.utc)
    knowledge_base.external_last_error = (
        failure.persistence_code if cleanup.succeeded else "cleanup_failed"
    )
    operations.commit_state(db, "failure_state_persist_failed")
    logger.error(
        "knowledge_base_provisioning_failed organization_id=%s knowledge_base_id=%s error_code=%s stage=%s classification=%s cleanup_succeeded=%s",
        org_id,
        kb_id,
        knowledge_base.external_last_error,
        failure.resource,
        failure.classification,
        cleanup.succeeded,
    )
    raise BedrockProvisioningError(
        failure.code if cleanup.succeeded else "cleanup_failed",
        resource=failure.resource,
        classification=failure.classification,
        aws_service=failure.aws_service if cleanup.succeeded else None,
        aws_operation=failure.aws_operation if cleanup.succeeded else None,
        aws_error_code=failure.aws_error_code if cleanup.succeeded else None,
        aws_request_id=failure.aws_request_id if cleanup.succeeded else None,
    ) from failure
