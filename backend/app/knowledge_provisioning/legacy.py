"""Verified cleanup for Diaglob's legacy shared Knowledge infrastructure.

The historical Knowledge Base and S3 Vectors index are shared infrastructure and
must never be deleted by tenant cleanup. This module owns only the legacy safety
rules: verify the known parent, verify the tenant-scoped S3 Data Source, delete
that Data Source, then remove the tenant's S3 prefix and local database rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from ..models import KnowledgeBase, KnowledgeSource
from .errors import BedrockProvisioningError

logger = logging.getLogger(__name__)


LEGACY_KNOWLEDGE_INFRASTRUCTURE: dict[str, str] = {
    "bedrock_kb_id": "RDAQY1JNQ8",
    "bedrock_kb_name": "diaglob-knowledge-main",
    "vector_index_name": "diaglob-knowledge-v1",
}


@dataclass(frozen=True)
class LegacyCleanupOperations:
    """Call-time dependencies for the legacy cleanup boundary."""

    get_knowledge_base: Callable[[str], dict[str, Any] | None]
    get_data_source: Callable[[str, str], dict[str, Any] | None]
    delete_data_source: Callable[[str, str], Any]
    validate_data_source_ownership: Callable[
        [dict[str, Any], dict[str, Any], int, int], None
    ]
    delete_knowledge_prefix: Callable[[int, int], None]
    commit_state: Callable[..., None]
    sleep_between_attempts: Callable[[int, int], None]
    client_error_code: Callable[[Exception], str | None]
    log_aws_error: Callable[..., None]
    aws_provisioning_error: Callable[..., BedrockProvisioningError]


def is_verified_legacy_parent(
    bedrock_kb_id: str,
    *,
    infrastructure: Mapping[str, str] = LEGACY_KNOWLEDGE_INFRASTRUCTURE,
) -> bool:
    """Return whether a Bedrock KB ID is the one known shared legacy parent."""
    return bedrock_kb_id == infrastructure["bedrock_kb_id"]


def legacy_vector_index_arn(
    vector_bucket_arn: str,
    *,
    infrastructure: Mapping[str, str] = LEGACY_KNOWLEDGE_INFRASTRUCTURE,
) -> str:
    """Build the ARN of the legacy shared vector index without deleting it."""
    if not vector_bucket_arn:
        raise BedrockProvisioningError(
            "vector_bucket_not_configured",
            resource="configuration",
        )
    return (
        f"{vector_bucket_arn}/index/"
        f"{infrastructure['vector_index_name']}"
    )


def validate_legacy_data_source_ownership(
    remote_ds: dict[str, Any],
    remote_kb: dict[str, Any],
    org_id: int,
    kb_id: int,
    *,
    legacy_kb_id: str,
    knowledge_bucket: str,
    expected_prefix: str,
) -> None:
    """Verify a legacy Data Source belongs exactly to the requested tenant KB."""
    if remote_kb.get("knowledgeBaseId") != legacy_kb_id:
        raise BedrockProvisioningError(
            "resource_ownership_mismatch",
            resource="data_source",
        )

    if remote_ds.get("knowledgeBaseId") != legacy_kb_id:
        raise BedrockProvisioningError(
            "resource_ownership_mismatch",
            resource="data_source",
        )

    ds_config = remote_ds.get("dataSourceConfiguration", {})
    if ds_config.get("type") != "S3":
        raise BedrockProvisioningError(
            "resource_ownership_mismatch",
            resource="data_source",
        )

    s3_config = ds_config.get("s3Configuration", {})
    expected_bucket_arn = f"arn:aws:s3:::{knowledge_bucket}"
    if s3_config.get("bucketArn") != expected_bucket_arn:
        raise BedrockProvisioningError(
            "resource_ownership_mismatch",
            resource="data_source",
        )

    prefixes = s3_config.get("inclusionPrefixes", [])
    if prefixes != [expected_prefix]:
        raise BedrockProvisioningError(
            "resource_ownership_mismatch",
            resource="data_source",
        )


def cleanup_verified_legacy_resources(
    db: Session,
    knowledge_base: KnowledgeBase,
    *,
    infrastructure: Mapping[str, str],
    wait_attempts: int,
    operations: LegacyCleanupOperations,
) -> None:
    """Delete only a verified legacy tenant Data Source and local resources.

    The shared parent Bedrock Knowledge Base and shared S3 Vectors index are
    intentionally outside this operation and are always preserved.
    """
    org_id = knowledge_base.organization_id
    kb_id = knowledge_base.id
    bedrock_kb_id = knowledge_base.external_id
    bedrock_ds_id = knowledge_base.external_data_source_id

    logger.info(
        "knowledge_base_deletion_mode=legacy organization_id=%s "
        "knowledge_base_id=%s bedrock_kb_id=%s bedrock_ds_id=%s "
        "legacy_parent_name=%s",
        org_id,
        kb_id,
        bedrock_kb_id,
        bedrock_ds_id,
        infrastructure["bedrock_kb_name"],
    )

    remote_kb = operations.get_knowledge_base(bedrock_kb_id)
    if not remote_kb:
        logger.warning(
            "legacy_parent_absent organization_id=%s knowledge_base_id=%s "
            "bedrock_kb_id=%s",
            org_id,
            kb_id,
            bedrock_kb_id,
        )
    else:
        logger.info(
            "legacy_parent_verified organization_id=%s knowledge_base_id=%s",
            org_id,
            kb_id,
        )

    if bedrock_ds_id and remote_kb:
        remote_ds = operations.get_data_source(bedrock_kb_id, bedrock_ds_id)
        if remote_ds:
            operations.validate_data_source_ownership(
                remote_ds,
                remote_kb,
                org_id,
                kb_id,
            )
            logger.info(
                "legacy_data_source_verified organization_id=%s "
                "knowledge_base_id=%s bedrock_ds_id=%s",
                org_id,
                kb_id,
                bedrock_ds_id,
            )
            try:
                operations.delete_data_source(bedrock_kb_id, bedrock_ds_id)
            except (BotoCoreError, ClientError) as error:
                if operations.client_error_code(error) != "ResourceNotFoundException":
                    operations.log_aws_error(
                        operation="DeleteDataSource",
                        aws_service="bedrock-agent",
                        stage="legacy_deleting",
                        org_id=org_id,
                        kb_id=kb_id,
                        error=error,
                        bedrock_kb_id=bedrock_kb_id,
                        bedrock_data_source_id=bedrock_ds_id,
                    )
                    raise operations.aws_provisioning_error(
                        "bedrock_data_source_delete_failed",
                        "data_source",
                        error,
                        aws_service="bedrock-agent",
                        aws_operation="DeleteDataSource",
                    ) from error

            for attempt in range(wait_attempts):
                remote_ds = operations.get_data_source(
                    bedrock_kb_id,
                    bedrock_ds_id,
                )
                if remote_ds is None:
                    break
                if remote_ds.get("status") == "DELETE_UNSUCCESSFUL":
                    raise BedrockProvisioningError(
                        "bedrock_data_source_delete_unconfirmed",
                        resource="data_source",
                    )
                operations.sleep_between_attempts(attempt, wait_attempts)
            else:
                raise BedrockProvisioningError(
                    "bedrock_data_source_delete_unconfirmed",
                    resource="data_source",
                )
            logger.info(
                "legacy_data_source_deleted organization_id=%s "
                "knowledge_base_id=%s",
                org_id,
                kb_id,
            )
        else:
            logger.info(
                "legacy_data_source_already_absent organization_id=%s "
                "knowledge_base_id=%s bedrock_ds_id=%s",
                org_id,
                kb_id,
                bedrock_ds_id,
            )

    logger.info(
        "legacy_parent_preserved organization_id=%s knowledge_base_id=%s",
        org_id,
        kb_id,
    )
    logger.info(
        "legacy_vector_index_preserved organization_id=%s knowledge_base_id=%s",
        org_id,
        kb_id,
    )

    operations.delete_knowledge_prefix(org_id, kb_id)
    logger.info(
        "s3_prefix_deleted organization_id=%s knowledge_base_id=%s",
        org_id,
        kb_id,
    )

    db.query(KnowledgeSource).filter(
        KnowledgeSource.organization_id == org_id,
        KnowledgeSource.knowledge_base_id == kb_id,
    ).delete(synchronize_session=False)
    db.delete(knowledge_base)
    operations.commit_state(db, "deletion_state_persist_failed")
    logger.info(
        "database_deleted organization_id=%s knowledge_base_id=%s",
        org_id,
        kb_id,
    )
