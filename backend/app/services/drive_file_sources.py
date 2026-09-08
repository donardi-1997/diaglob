"""Standalone Drive file orchestration.

Business logic for standalone Google Doc import, Drive file import,
and Drive file sync extracted from the Knowledge HTTP router.
"""

import logging
import re
from datetime import datetime

import httpx

from ..bedrock_ingestion import start_ingestion_job
from ..google_drive_client import (
    GoogleDriveFileTooLarge,
    download_drive_file,
    export_google_doc,
    get_file_metadata,
)
from ..knowledge_storage import upload_knowledge_file
from ..models import KnowledgeBase, KnowledgeSource
from .knowledge_sources import (
    _delete_artifact_best_effort,
    _find_active_drive_source,
    _mark_drive_source_failed,
    _parse_google_modified_at,
    _persist_new_drive_source,
    _start_drive_source_ingestion,
)

logger = logging.getLogger(__name__)


class _EmptyContentError(Exception):
    """Raised when downloaded content is empty."""


class DriveSourceConflictError(Exception):
    """Raised when a Drive object conflicts with an existing source."""


def check_standalone_conflict(
    existing: KnowledgeSource,
) -> dict | None:
    """Check for standalone drive conflicts. Returns response dict if duplicate, None otherwise."""
    if (
        existing.parent_source_id is not None
        or existing.source_type == "google_drive_folder"
    ):
        raise DriveSourceConflictError(
            "Drive object already exists in this "
            "knowledge base with a conflicting "
            "folder relationship."
        )
    return {
        "source_id": existing.id,
        "name": existing.name,
        "sync_status": existing.sync_status or "synced",
        "message": "Source already exists",
    }


async def add_google_doc(
    db,
    organization_id: int,
    knowledge_base: KnowledgeBase,
    access_token: str,
    file_id: str,
    file_name: str,
) -> dict:
    """Add a standalone Google Doc source. Returns result dict or raises on failure."""
    knowledge_base_id = knowledge_base.id

    try:
        content = await export_google_doc(
            access_token, file_id, "text/plain",
        )
    except Exception:
        raise

    if not content:
        raise _EmptyContentError("Document is empty")

    filename = f"{file_name}.txt"
    try:
        s3_result = upload_knowledge_file(
            organization_id=organization_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=content,
            content_type="text/plain",
        )
    except Exception:
        raise

    remote_meta = None
    try:
        remote_meta = await get_file_metadata(
            access_token, file_id
        )
    except Exception:
        pass

    modified_at = _parse_google_modified_at(
        remote_meta.get("modifiedTime") if remote_meta else None
    )

    source = KnowledgeSource(
        knowledge_base_id=knowledge_base_id,
        organization_id=organization_id,
        name=file_name,
        source_type="google_doc",
        s3_bucket=s3_result["bucket"],
        s3_key=s3_result["key"],
        size_bytes=len(content),
        status="uploaded",
        external_id=file_id,
        external_name=file_name,
        external_mime_type="application/vnd.google-apps.document",
        external_modified_at=modified_at,
        last_synced_at=datetime.utcnow(),
        sync_status="uploaded",
    )
    try:
        _persist_new_drive_source(db, source, s3_result)
    except Exception:
        raise

    sync_status, ingestion_job_id = _start_drive_source_ingestion(
        db, source, knowledge_base
    )

    return {
        "source_id": source.id,
        "name": source.name,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
    }


async def add_drive_file(
    db,
    organization_id: int,
    knowledge_base: KnowledgeBase,
    access_token: str,
    file_id: str,
    file_name: str,
    mime_type: str,
) -> dict:
    """Add a standalone Drive file source. Returns result dict or raises on failure."""
    knowledge_base_id = knowledge_base.id

    try:
        content = await download_drive_file(access_token, file_id)
    except Exception:
        raise

    if not content:
        raise _EmptyContentError("File is empty")

    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", file_name)
    filename = f"{safe_name}"
    try:
        s3_result = upload_knowledge_file(
            organization_id=organization_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=content,
            content_type=mime_type,
        )
    except Exception:
        raise

    remote_meta = None
    try:
        remote_meta = await get_file_metadata(access_token, file_id)
    except Exception:
        pass

    modified_at = _parse_google_modified_at(
        remote_meta.get("modifiedTime") if remote_meta else None
    )
    ext_size = None
    if remote_meta:
        if remote_meta.get("size"):
            try:
                ext_size = int(remote_meta["size"])
            except (TypeError, ValueError):
                pass

    source = KnowledgeSource(
        knowledge_base_id=knowledge_base_id,
        organization_id=organization_id,
        name=file_name,
        source_type="google_drive_file",
        content_type=mime_type,
        s3_bucket=s3_result["bucket"],
        s3_key=s3_result["key"],
        size_bytes=len(content),
        status="uploaded",
        external_id=file_id,
        external_name=file_name,
        external_mime_type=mime_type,
        external_modified_at=modified_at,
        external_size=ext_size,
        last_synced_at=datetime.utcnow(),
        sync_status="uploaded",
    )
    try:
        _persist_new_drive_source(db, source, s3_result)
    except Exception:
        raise

    sync_status, ingestion_job_id = _start_drive_source_ingestion(
        db, source, knowledge_base
    )

    return {
        "source_id": source.id,
        "name": source.name,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
    }


async def sync_drive_file(
    db,
    organization_id: int,
    knowledge_base: KnowledgeBase,
    source: KnowledgeSource,
    access_token: str,
) -> dict:
    """Sync a standalone Drive file source. Returns result dict or raises on failure."""
    knowledge_base_id = knowledge_base.id

    source.sync_status = "syncing"
    source.sync_error = None
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Re-download content
    try:
        if source.source_type == "google_doc":
            content = await export_google_doc(
                access_token, source.external_id, "text/plain",
            )
            new_mime = "text/plain"
        else:
            content = await download_drive_file(
                access_token, source.external_id
            )
            new_mime = (
                source.external_mime_type
                or source.content_type
                or "application/octet-stream"
            )
    except httpx.HTTPStatusError:
        raise
    except (GoogleDriveFileTooLarge, ValueError):
        raise
    except Exception as exc:
        _mark_drive_source_failed(
            db, source, f"Google Drive download failed: {exc}",
        )
        raise

    if not content:
        _mark_drive_source_failed(db, source, "File is empty")
        raise _EmptyContentError("File is empty")

    # Upload and durably repoint before deleting the old artifact.
    old_bucket = source.s3_bucket
    old_key = source.s3_key
    safe_name = re.sub(
        r"[^A-Za-z0-9._-]+", "-",
        source.external_name or source.name,
    )
    try:
        s3_result = upload_knowledge_file(
            organization_id=organization_id,
            knowledge_base_id=knowledge_base_id,
            filename=safe_name,
            content=content,
            content_type=new_mime,
        )
    except Exception as exc:
        _mark_drive_source_failed(
            db, source, f"S3 upload failed: {exc}",
        )
        raise

    # Get remote metadata
    remote_meta = None
    try:
        remote_meta = await get_file_metadata(access_token, source.external_id)
    except Exception:
        pass

    if remote_meta:
        source.external_modified_at = (
            _parse_google_modified_at(remote_meta.get("modifiedTime"))
            or source.external_modified_at
        )

    source.s3_bucket = s3_result["bucket"]
    source.s3_key = s3_result["key"]
    source.size_bytes = len(content)
    source.content_type = new_mime
    source.status = "uploaded"
    source.last_synced_at = datetime.utcnow()
    source.sync_status = "uploaded"
    source.sync_error = None
    source.ingestion_job_id = None
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        _delete_artifact_best_effort(
            s3_result.get("bucket"), s3_result.get("key"),
            "Failed to clean new Drive sync artifact",
        )
        # Re-query source after rollback to avoid stale state
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source.id,
                KnowledgeSource.organization_id == organization_id,
                KnowledgeSource.knowledge_base_id == knowledge_base_id,
            )
            .first()
        )
        if persisted_source:
            _mark_drive_source_failed(
                db, persisted_source, f"DB persistence failed: {exc}",
            )
        raise

    cleanup_warning = None
    if (old_bucket, old_key) != (
        s3_result.get("bucket"), s3_result.get("key")
    ):
        cleanup_warning = _delete_artifact_best_effort(
            old_bucket, old_key, "Failed to delete replaced artifact",
        )

    try:
        sync_status, ingestion_job_id = (
            _start_drive_source_ingestion(
                db, source, knowledge_base, cleanup_warning,
            )
        )
        db.refresh(source)
    except Exception as exc:
        db.rollback()
        # Re-query source after rollback
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source.id,
                KnowledgeSource.organization_id == organization_id,
                KnowledgeSource.knowledge_base_id == knowledge_base_id,
            )
            .first()
        )
        if persisted_source:
            persisted_source.sync_status = "uploaded"
            persisted_source.sync_error = (
                f"Ingestion state persistence failed: {exc}"
            )
            try:
                db.commit()
            except Exception:
                db.rollback()
        raise

    return {
        "source_id": source.id,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
        "sync_error": source.sync_error,
        "warning": cleanup_warning,
    }
