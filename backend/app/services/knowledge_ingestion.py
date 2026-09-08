"""Knowledge Source ingestion/status lifecycle service.

Source ingestion status polling, Bedrock ingestion state synchronization,
source ingestion triggers, and reindex orchestration.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..bedrock_ingestion import (
    STATUS_FAILED,
    STATUS_SYNCED,
    get_ingestion_status,
    start_ingestion_job,
)
from ..models import KnowledgeBase, KnowledgeSource

logger = logging.getLogger(__name__)


# ============================================================
# DOMAIN EXCEPTIONS
# ============================================================


class SourceNotFoundError(Exception):
    """Source not found within the given KB and organization."""


class KnowledgeBaseNotReadyError(Exception):
    """Knowledge Base provisioning is not ready for ingestion operations."""


class IngestionJobMissingError(Exception):
    """No ingestion job ID available for status polling."""


# ============================================================
# INGESTION STATUS POLLING
# ============================================================


def refresh_source_ingestion_status(
    db: Session,
    *,
    organization_id: int,
    knowledge_base_id: int,
    source_id: int,
) -> dict:
    """Poll Bedrock for current ingestion status and update source state.

    Returns a response dict with source_id, sync_status,
    last_synced_at, and sync_error.
    """
    kb = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id == organization_id,
        )
        .first()
    )
    if not kb:
        raise SourceNotFoundError("Knowledge Base not found")

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.organization_id == organization_id,
        )
        .first()
    )
    if not source:
        raise SourceNotFoundError("Source not found")

    # If not in indexing state, return current status
    if source.sync_status != "indexing":
        return _build_status_response(source)

    # Guard: do not call Bedrock if KB is not ready.
    if kb.external_status != "ready":
        return _build_status_response(source)

    # Check Bedrock ingestion status
    if (
        not source.ingestion_job_id
        or not kb.external_id
        or not kb.external_data_source_id
    ):
        return _build_status_response(source)

    new_status = get_ingestion_status(
        kb.external_id,
        kb.external_data_source_id,
        source.ingestion_job_id,
    )

    if new_status != source.sync_status:
        source.sync_status = new_status
        if new_status == STATUS_SYNCED:
            source.last_synced_at = datetime.utcnow()
        elif new_status == STATUS_FAILED:
            source.sync_error = "Bedrock ingestion failed"
        db.commit()

    return _build_status_response(source)


def _build_status_response(source: KnowledgeSource) -> dict:
    """Build the standard ingestion status response dict."""
    return {
        "source_id": source.id,
        "sync_status": source.sync_status,
        "last_synced_at": (
            source.last_synced_at.isoformat()
            if source.last_synced_at
            else None
        ),
        "sync_error": source.sync_error,
    }


# ============================================================
# REINDEX TRIGGER
# ============================================================


def trigger_source_reindex(
    kb: KnowledgeBase,
) -> tuple[str | None, str]:
    """Trigger a Bedrock ingestion job to reindex after source deletion.

    Returns (ingestion_job_id, reindex_status).
    """
    ingestion_job_id = None
    reindex_status = "not_configured"

    job_id = start_ingestion_job(
        kb.external_id,
        kb.external_data_source_id,
    )
    if job_id:
        ingestion_job_id = job_id
        reindex_status = "indexing"
    else:
        reindex_status = "reindex_failed"

    return ingestion_job_id, reindex_status


# ============================================================
# IDEMPOTENCY CHECK
# ============================================================


def is_source_sync_in_progress(source: KnowledgeSource) -> bool:
    """Check if a source is currently syncing or indexing."""
    return source.sync_status in ("syncing", "indexing")
