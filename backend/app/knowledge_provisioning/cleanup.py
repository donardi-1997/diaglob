"""Compensating cleanup for modern Knowledge Base infrastructure.

This module deliberately knows nothing about SQLAlchemy state or legacy shared
infrastructure. It only coordinates deletion of already-owned modern remote
resources in dependency order while preserving ambiguous resource identifiers
when cleanup cannot be confirmed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """Outcome of best-effort modern remote-resource cleanup."""

    succeeded: bool
    bedrock_kb_id: str | None
    bedrock_ds_id: str | None
    error: Exception | None = None


DeleteDataSource = Callable[[str, str, int, int, str], None]
DeleteKnowledgeBase = Callable[[str, int, int, str], None]
DeleteVectorIndex = Callable[[str, int, int], None]


def cleanup_remote_resources(
    org_id: int,
    kb_id: int,
    index_arn: str | None,
    bedrock_kb_id: str | None,
    bedrock_ds_id: str | None,
    *,
    delete_data_source: DeleteDataSource,
    delete_knowledge_base: DeleteKnowledgeBase,
    delete_vector_index: DeleteVectorIndex,
) -> CleanupResult:
    """Delete modern remote resources in dependency order.

    The operation stops at the first unconfirmed deletion. Identifiers are only
    cleared after the corresponding delete callable returns successfully. This
    preserves the historical ambiguity semantics used by retry/reconciliation
    flows: if a provider call fails, the caller retains every ID that might still
    exist remotely.
    """
    remaining_kb_id = bedrock_kb_id
    remaining_ds_id = bedrock_ds_id

    if remaining_ds_id and remaining_kb_id:
        try:
            delete_data_source(
                remaining_kb_id,
                remaining_ds_id,
                org_id,
                kb_id,
                index_arn,
            )
            remaining_ds_id = None
        except Exception as error:
            logger.exception("Unable to confirm Bedrock Data Source cleanup")
            return CleanupResult(False, remaining_kb_id, remaining_ds_id, error)

    if remaining_kb_id and index_arn:
        try:
            delete_knowledge_base(remaining_kb_id, org_id, kb_id, index_arn)
            remaining_kb_id = None
            remaining_ds_id = None
        except Exception as error:
            logger.exception("Unable to confirm Bedrock Knowledge Base cleanup")
            return CleanupResult(False, remaining_kb_id, remaining_ds_id, error)

    if index_arn:
        try:
            delete_vector_index(index_arn, org_id, kb_id)
        except Exception as error:
            logger.exception("Unable to confirm S3 Vectors index cleanup")
            return CleanupResult(False, remaining_kb_id, remaining_ds_id, error)

    return CleanupResult(True, remaining_kb_id, remaining_ds_id)
