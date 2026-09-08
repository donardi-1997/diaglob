"""Knowledge Sources business logic.

Source helpers, state transitions, sync orchestration, and freshness
derivation extracted from the Knowledge HTTP router.
"""

import json
import logging
import re
from datetime import datetime, timezone

from ..bedrock_ingestion import start_ingestion_job
from ..google_drive_client import (
    GoogleDriveFileTooLarge,
    MAX_TOTAL_SYNC_BYTES,
    download_drive_file,
    export_google_doc,
    is_google_doc,
    list_folder_children,
    validate_folder_sync_limits,
)
from ..google_sheets_client import (
    fetch_sheet_values,
    get_spreadsheet_metadata,
    normalize_to_csv,
)
from ..knowledge_storage import delete_knowledge_file, upload_knowledge_file
from ..models import GoogleConnection, KnowledgeBase, KnowledgeSource

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTS
# ============================================================

DRIVE_SOURCE_TYPES = (
    "google_doc",
    "google_drive_file",
    "google_drive_folder",
)


# ============================================================
# PURE HELPERS
# ============================================================


def _google_source_import_mode(source: KnowledgeSource) -> str:
    """Treat sources created before workbook support as single-sheet imports."""
    try:
        metadata = json.loads(source.metadata_json or "{}")
    except json.JSONDecodeError:
        return "sheet"
    return metadata.get("import_mode", "sheet")


def _drive_conflict_reason(existing: KnowledgeSource) -> str:
    if existing.source_type == "google_drive_folder":
        return "Drive object already exists as a folder source"
    if existing.parent_source_id is not None:
        return "File already belongs to another folder source"
    return "File already exists as a standalone Drive source"


def _folder_file_record(file_meta: dict) -> dict:
    return {
        "id": file_meta["id"],
        "name": file_meta.get("name", ""),
        "modifiedTime": file_meta.get("modifiedTime", ""),
        "size": file_meta.get("size", "0"),
    }


def _folder_summary() -> dict:
    return {
        "new": 0,
        "modified": 0,
        "removed": 0,
        "unchanged": 0,
        "failed": [],
        "ignored": [],
        "successful_delta": False,
    }


def _folder_sync_error(
    summary: dict,
    warnings: list[dict],
    ingestion_error: str | None = None,
) -> str | None:
    errors = [
        f"{item['action']} {item.get('name') or item['id']}: {item['error']}"
        for item in summary["failed"]
    ]
    errors.extend(
        f"{item['action']} {item.get('name') or item['id']}: {item['warning']}"
        for item in warnings
    )
    if ingestion_error:
        errors.append(ingestion_error)
    return "; ".join(errors) or None


def _parse_google_modified_at(value: str | None) -> datetime | None:
    """Convert Drive's RFC 3339 value to a UTC-naive DB timestamp."""
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        return timestamp
    except ValueError:
        return None


def _is_remote_file_modified(
    source: KnowledgeSource,
    remote_modified_at: str | None,
) -> bool:
    """Compare normalized timestamps without lexical/RFC3339 ambiguity."""
    remote = _parse_google_modified_at(remote_modified_at)
    if not remote:
        return False
    local = source.external_modified_at
    if not local:
        return True
    if local.tzinfo:
        local = local.astimezone(timezone.utc).replace(tzinfo=None)
    return remote > local


def _derive_freshness(
    source: KnowledgeSource,
    connection: GoogleConnection | None,
) -> str:
    """Derive freshness status for a knowledge source.

    Returns one of:
    - fresh
    - changed
    - syncing
    - failed
    - disconnected
    - static
    """
    source_type = source.source_type or ""

    if (
        source_type.startswith("google_")
        and (not connection or connection.status != "connected")
    ):
        return "disconnected"

    if source.sync_status == "failed":
        return "failed"

    if source.sync_status in ("syncing", "indexing"):
        return "syncing"

    if source_type.startswith("google_"):
        if (
            source.external_modified_at
            and source.last_synced_at
            and source.external_modified_at > source.last_synced_at
        ):
            return "changed"
        if source.sync_status == "synced":
            return "fresh"

    return "static"


# ============================================================
# DB + EXTERNAL API HELPERS
# ============================================================


async def _fetch_google_workbook_content(
    access_token: str,
    spreadsheet_id: str,
    spreadsheet_title: str,
) -> tuple[str, str]:
    metadata = await get_spreadsheet_metadata(
        access_token, spreadsheet_id
    )
    spreadsheet_title = metadata.get("title", spreadsheet_title)
    sections = []
    for tab in metadata.get("sheets", []):
        if tab.get("hidden", False):
            continue
        tab_name = tab.get("title", "")
        values = await fetch_sheet_values(
            access_token, spreadsheet_id, tab_name
        )
        csv_content = normalize_to_csv(
            values, spreadsheet_title, tab_name
        )
        if csv_content.strip():
            sections.append(f"## Sheet: {tab_name}\n{csv_content.strip()}")

    if not sections:
        raise ValueError("Workbook has no non-empty visible sheets")

    return spreadsheet_title, (
        f"# Spreadsheet: {spreadsheet_title}\n\n"
        + "\n\n".join(sections)
        + "\n"
    )


def _find_active_drive_source(
    db,
    organization_id: int,
    knowledge_base_id: int,
    external_id: str,
) -> KnowledgeSource | None:
    return (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.organization_id == organization_id,
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.external_id == external_id,
            KnowledgeSource.source_type.in_(DRIVE_SOURCE_TYPES),
            KnowledgeSource.active.is_(True),
        )
        .first()
    )


def _delete_artifact_best_effort(
    bucket: str | None,
    key: str | None,
    context: str,
) -> str | None:
    if not bucket or not key:
        return None
    try:
        delete_knowledge_file(bucket, key)
    except Exception as exc:
        warning = f"{context}: {exc}"
        logger.warning("%s", warning, exc_info=True)
        return warning
    return None


def _persist_new_drive_source(
    db,
    source: KnowledgeSource,
    uploaded: dict,
) -> None:
    """Persist a new source or remove its just-uploaded artifact."""
    try:
        db.add(source)
        db.commit()
        db.refresh(source)
    except Exception:
        db.rollback()
        _delete_artifact_best_effort(
            uploaded.get("bucket"),
            uploaded.get("key"),
            "Failed to clean artifact after DB persistence failure",
        )
        raise


async def _download_drive_child(
    access_token: str,
    file_id: str,
    mime_type: str,
) -> tuple[bytes, str, str]:
    if is_google_doc(mime_type):
        return (
            await export_google_doc(access_token, file_id, "text/plain"),
            "text/plain",
            "google_doc",
        )
    return (
        await download_drive_file(access_token, file_id),
        mime_type,
        "google_drive_file",
    )


def _start_drive_source_ingestion(
    db,
    source: KnowledgeSource,
    kb: KnowledgeBase,
    prior_warning: str | None = None,
) -> tuple[str, str | None]:
    sync_status = "uploaded"
    ingestion_job_id = None
    ingestion_error = None

    if kb.external_id and kb.external_data_source_id:
        try:
            ingestion_job_id = start_ingestion_job(
                kb.external_id,
                kb.external_data_source_id,
            )
            if ingestion_job_id:
                sync_status = "indexing"
            else:
                ingestion_error = "Bedrock ingestion failed to start"
        except Exception as exc:
            ingestion_error = f"Bedrock ingestion failed to start: {exc}"
            logger.exception(
                "Failed to start Drive ingestion for source %s",
                source.id,
            )

    source.sync_status = sync_status
    source.ingestion_job_id = ingestion_job_id
    source.sync_error = "; ".join(
        message
        for message in (prior_warning, ingestion_error)
        if message
    ) or None
    db.commit()
    return sync_status, ingestion_job_id


def _mark_drive_source_failed(
    db,
    source: KnowledgeSource,
    error: str,
) -> None:
    source.sync_status = "failed"
    source.sync_error = error
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Failed to persist Drive source failure for %s",
            source.id,
        )


# ============================================================
# COMPLEX ORCHESTRATION
# ============================================================


def _finish_folder_operation(
    db,
    source: KnowledgeSource,
    kb: KnowledgeBase,
    remote_files: list[dict],
    summary: dict,
    warnings: list[dict],
) -> tuple[str, str | None]:
    summary["successful_delta"] = bool(
        summary["new"] + summary["modified"] + summary["removed"]
    )

    if summary["failed"] and not summary["successful_delta"]:
        sync_status = "failed"
    elif summary["failed"]:
        sync_status = "partial_failed"
    elif summary["successful_delta"]:
        sync_status = "uploaded"
    else:
        sync_status = "synced"

    source.sync_status = sync_status
    source.sync_error = _folder_sync_error(summary, warnings)
    source.ingestion_job_id = None
    source.sync_generation = (source.sync_generation or 0) + 1
    source.last_synced_at = datetime.utcnow()
    source.metadata_json = json.dumps({
        "file_count": len(remote_files),
        "new": summary["new"],
        "modified": summary["modified"],
        "removed": summary["removed"],
        "unchanged": summary["unchanged"],
        "last_synced_files": [
            _folder_file_record(file_meta)
            for file_meta in remote_files
        ],
        "summary": summary,
        "warnings": warnings,
    })
    db.commit()

    ingestion_job_id = None
    ingestion_error = None
    if (
        summary["successful_delta"]
        and kb.external_id
        and kb.external_data_source_id
    ):
        try:
            ingestion_job_id = start_ingestion_job(
                kb.external_id,
                kb.external_data_source_id,
            )
            if not ingestion_job_id:
                ingestion_error = "Bedrock ingestion failed to start"
        except Exception as exc:
            ingestion_error = f"Bedrock ingestion failed to start: {exc}"
            logger.exception(
                "Failed to start folder ingestion for source %s",
                source.id,
            )

        if ingestion_job_id:
            source.ingestion_job_id = ingestion_job_id
            if not summary["failed"]:
                sync_status = "indexing"
        else:
            ingestion_job_id = None
            if not summary["failed"]:
                sync_status = "uploaded"

        source.sync_status = sync_status
        source.sync_error = _folder_sync_error(
            summary, warnings, ingestion_error
        )
        db.commit()

    return sync_status, ingestion_job_id


# ============================================================
# FOLDER ORCHESTRATION
# ============================================================


async def add_google_drive_folder(
    db,
    organization_id: int,
    knowledge_base: KnowledgeBase,
    access_token: str,
    folder_id: str,
    folder_name: str,
) -> dict:
    """Full add-folder workflow. Returns result dict or raises on failure."""
    knowledge_base_id = knowledge_base.id

    existing = _find_active_drive_source(
        db, organization_id, knowledge_base_id, folder_id,
    )

    if existing:
        if existing.source_type != "google_drive_folder":
            raise ValueError(
                _drive_conflict_reason(existing)
            )
        return {
            "duplicate": True,
            "source_id": existing.id,
            "name": existing.name,
            "sync_status": existing.sync_status or "synced",
            "message": "Folder source already exists",
        }

    result = await list_folder_children(access_token, folder_id)
    files = result.get("files", [])

    if result.get("limit_exceeded"):
        raise ValueError("Folder exceeds the configured maximum file count.")

    limit_error = validate_folder_sync_limits(files)
    if limit_error:
        raise ValueError(limit_error)

    summary = _folder_summary()
    warnings = []

    source = KnowledgeSource(
        knowledge_base_id=knowledge_base_id,
        organization_id=organization_id,
        name=folder_name,
        source_type="google_drive_folder",
        s3_bucket="",
        s3_key="",
        status="uploaded",
        external_id=folder_id,
        external_name=folder_name,
        sync_status="uploaded",
        metadata_json=json.dumps({
            "file_count": len(files),
            "last_synced_files": [
                _folder_file_record(f) for f in files
            ],
            "summary": summary,
        }),
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    downloaded_bytes = 0
    for f in files:
        file_id = f["id"]
        file_name = f.get("name", "Untitled")
        mime_type = f.get("mimeType", "")

        child_existing = _find_active_drive_source(
            db, organization_id, knowledge_base_id, file_id,
        )

        if child_existing:
            summary["ignored"].append({
                "id": file_id,
                "name": file_name,
                "reason": _drive_conflict_reason(child_existing),
            })
            continue

        try:
            content, child_mime, child_type = (
                await _download_drive_child(access_token, file_id, mime_type)
            )
        except Exception as exc:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": str(exc),
            })
            continue

        if not content:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": "File is empty",
            })
            continue

        downloaded_bytes += len(content)
        if downloaded_bytes > MAX_TOTAL_SYNC_BYTES:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": (
                    "Actual downloaded content exceeds "
                    f"the {MAX_TOTAL_SYNC_BYTES} byte "
                    "folder sync limit"
                ),
            })
            continue

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", file_name)
        child_filename = f"{safe_name}"

        try:
            s3_result = upload_knowledge_file(
                organization_id=organization_id,
                knowledge_base_id=knowledge_base_id,
                filename=child_filename,
                content=content,
                content_type=child_mime,
            )
        except Exception as exc:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": f"S3 upload failed: {exc}",
            })
            continue

        modified_at = _parse_google_modified_at(f.get("modifiedTime"))
        ext_size = None
        if f.get("size"):
            try:
                ext_size = int(f["size"])
            except (TypeError, ValueError):
                pass

        child_source = KnowledgeSource(
            knowledge_base_id=knowledge_base_id,
            organization_id=organization_id,
            name=file_name,
            source_type=child_type,
            content_type=child_mime,
            s3_bucket=s3_result["bucket"],
            s3_key=s3_result["key"],
            size_bytes=len(content),
            status="uploaded",
            external_id=file_id,
            external_name=file_name,
            external_mime_type=child_mime,
            external_modified_at=modified_at,
            external_size=ext_size,
            parent_source_id=source.id,
            last_synced_at=datetime.utcnow(),
            sync_status="uploaded",
        )
        try:
            _persist_new_drive_source(db, child_source, s3_result)
        except Exception as exc:
            summary["failed"].append({
                "id": file_id,
                "name": file_name,
                "action": "new",
                "error": f"DB persistence failed: {exc}",
            })
            continue
        summary["new"] += 1

    try:
        sync_status, ingestion_job_id = (
            _finish_folder_operation(
                db, source, knowledge_base, files, summary, warnings,
            )
        )
        db.refresh(source)
    except Exception:
        db.rollback()
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
                db, persisted_source, "Folder finalization failed",
            )
        raise

    return {
        "duplicate": False,
        "source_id": source.id,
        "name": source.name,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
        "child_count": summary["new"],
        "new_files": summary["new"],
        "modified_files": summary["modified"],
        "removed_files": summary["removed"],
        "summary": summary,
        "warnings": warnings,
    }


async def sync_google_drive_folder(
    db,
    organization_id: int,
    knowledge_base: KnowledgeBase,
    source: KnowledgeSource,
    access_token: str,
) -> dict:
    """Full sync-folder workflow. Returns result dict or raises on failure."""
    knowledge_base_id = knowledge_base.id

    source.sync_status = "syncing"
    source.sync_error = None
    db.commit()

    try:
        result = await list_folder_children(
            access_token, source.external_id
        )
    except Exception as exc:
        error = f"Unable to list Google Drive folder: {exc}"
        _mark_drive_source_failed(db, source, error)
        raise

    remote_files = result.get("files", [])

    if result.get("limit_exceeded"):
        source.sync_status = "failed"
        source.sync_error = (
            "Folder exceeds the configured maximum file count"
        )
        db.commit()
        raise ValueError(source.sync_error)

    limit_error = validate_folder_sync_limits(remote_files)
    if limit_error:
        source.sync_status = "failed"
        source.sync_error = limit_error
        db.commit()
        raise ValueError(limit_error)

    existing_children = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.parent_source_id == source.id,
            KnowledgeSource.organization_id == organization_id,
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.source_type.in_(DRIVE_SOURCE_TYPES),
            KnowledgeSource.active.is_(True),
        )
        .all()
    )

    remote_by_id = {f["id"]: f for f in remote_files}
    local_by_ext_id = {
        c.external_id: c
        for c in existing_children
        if c.external_id
    }

    summary = _folder_summary()
    warnings = []
    new_files = []
    modified_files = []
    removed_children = []

    for fid, fmeta in remote_by_id.items():
        if fid not in local_by_ext_id:
            conflict = _find_active_drive_source(
                db, organization_id, knowledge_base_id, fid,
            )
            if conflict:
                summary["ignored"].append({
                    "id": fid,
                    "name": fmeta.get("name", "Untitled"),
                    "reason": _drive_conflict_reason(conflict),
                })
                continue
            new_files.append(fmeta)
        else:
            child = local_by_ext_id[fid]
            if _is_remote_file_modified(child, fmeta.get("modifiedTime")):
                modified_files.append(fmeta)
            else:
                summary["unchanged"] += 1

    for fid, child in local_by_ext_id.items():
        if fid not in remote_by_id:
            removed_children.append(child)

    downloaded_bytes = 0

    for fmeta in new_files:
        fid = fmeta["id"]
        fname = fmeta.get("name", "Untitled")
        fmime = fmeta.get("mimeType", "")

        try:
            content, child_mime, child_type = (
                await _download_drive_child(access_token, fid, fmime)
            )
        except Exception as exc:
            summary["failed"].append({
                "id": fid, "name": fname, "action": "new", "error": str(exc),
            })
            continue

        if not content:
            summary["failed"].append({
                "id": fid, "name": fname, "action": "new", "error": "File is empty",
            })
            continue

        downloaded_bytes += len(content)
        if downloaded_bytes > MAX_TOTAL_SYNC_BYTES:
            summary["failed"].append({
                "id": fid, "name": fname, "action": "new",
                "error": (
                    "Actual downloaded content exceeds "
                    f"the {MAX_TOTAL_SYNC_BYTES} byte folder sync limit"
                ),
            })
            continue

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", fname)
        try:
            s3_result = upload_knowledge_file(
                organization_id=organization_id,
                knowledge_base_id=knowledge_base_id,
                filename=safe_name,
                content=content,
                content_type=child_mime,
            )
        except Exception as exc:
            summary["failed"].append({
                "id": fid, "name": fname, "action": "new",
                "error": f"S3 upload failed: {exc}",
            })
            continue

        modified_at = _parse_google_modified_at(fmeta.get("modifiedTime"))
        ext_size = None
        if fmeta.get("size"):
            try:
                ext_size = int(fmeta["size"])
            except (TypeError, ValueError):
                pass

        child_source = KnowledgeSource(
            knowledge_base_id=knowledge_base_id,
            organization_id=organization_id,
            name=fname,
            source_type=child_type,
            content_type=child_mime,
            s3_bucket=s3_result["bucket"],
            s3_key=s3_result["key"],
            size_bytes=len(content),
            status="uploaded",
            external_id=fid,
            external_name=fname,
            external_mime_type=child_mime,
            external_modified_at=modified_at,
            external_size=ext_size,
            parent_source_id=source.id,
            last_synced_at=datetime.utcnow(),
            sync_status="uploaded",
        )
        try:
            _persist_new_drive_source(db, child_source, s3_result)
        except Exception as exc:
            summary["failed"].append({
                "id": fid, "name": fname, "action": "new",
                "error": f"DB persistence failed: {exc}",
            })
            continue
        summary["new"] += 1

    for fmeta in modified_files:
        fid = fmeta["id"]
        fname = fmeta.get("name", "Untitled")
        fmime = fmeta.get("mimeType", "")
        child = local_by_ext_id[fid]

        try:
            content, child_mime, child_type = (
                await _download_drive_child(access_token, fid, fmime)
            )
        except Exception as exc:
            summary["failed"].append({
                "id": fid, "name": fname, "action": "modified", "error": str(exc),
            })
            continue

        if not content:
            summary["failed"].append({
                "id": fid, "name": fname, "action": "modified", "error": "File is empty",
            })
            continue

        downloaded_bytes += len(content)
        if downloaded_bytes > MAX_TOTAL_SYNC_BYTES:
            summary["failed"].append({
                "id": fid, "name": fname, "action": "modified",
                "error": (
                    "Actual downloaded content exceeds "
                    f"the {MAX_TOTAL_SYNC_BYTES} byte folder sync limit"
                ),
            })
            continue

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", fname)
        try:
            s3_result = upload_knowledge_file(
                organization_id=organization_id,
                knowledge_base_id=knowledge_base_id,
                filename=safe_name,
                content=content,
                content_type=child_mime,
            )
        except Exception as exc:
            summary["failed"].append({
                "id": fid, "name": fname, "action": "modified",
                "error": f"S3 upload failed: {exc}",
            })
            continue

        modified_at = _parse_google_modified_at(fmeta.get("modifiedTime"))
        ext_size = None
        if fmeta.get("size"):
            try:
                ext_size = int(fmeta["size"])
            except (TypeError, ValueError):
                pass

        old_bucket = child.s3_bucket
        old_key = child.s3_key
        child.name = fname
        child.source_type = child_type
        child.content_type = child_mime
        child.s3_bucket = s3_result["bucket"]
        child.s3_key = s3_result["key"]
        child.size_bytes = len(content)
        child.status = "uploaded"
        child.external_name = fname
        child.external_mime_type = fmime
        child.external_modified_at = modified_at
        child.external_size = ext_size
        child.last_synced_at = datetime.utcnow()
        child.sync_status = "uploaded"
        child.sync_error = None
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            _delete_artifact_best_effort(
                s3_result.get("bucket"), s3_result.get("key"),
                "Failed to clean new modified artifact",
            )
            summary["failed"].append({
                "id": fid, "name": fname, "action": "modified",
                "error": f"DB persistence failed: {exc}",
            })
            continue

        summary["modified"] += 1
        if (old_bucket, old_key) != (
            s3_result.get("bucket"), s3_result.get("key")
        ):
            cleanup_warning = _delete_artifact_best_effort(
                old_bucket, old_key, "Failed to delete replaced artifact",
            )
            if cleanup_warning:
                warnings.append({
                    "id": fid, "name": fname,
                    "action": "modified_cleanup", "warning": cleanup_warning,
                })

    for child in removed_children:
        try:
            if child.s3_bucket and child.s3_key:
                delete_knowledge_file(child.s3_bucket, child.s3_key)
        except Exception as exc:
            error = f"S3 delete failed: {exc}"
            child.sync_status = "failed"
            child.sync_error = error
            try:
                db.commit()
            except Exception:
                db.rollback()
                logger.exception(
                    "Failed to persist removal failure for %s", child.id,
                )
            summary["failed"].append({
                "id": child.external_id or str(child.id),
                "name": child.name, "action": "removed", "error": error,
            })
            continue

        child.active = False
        child.status = "deleted"
        child.sync_status = "synced"
        child.sync_error = None
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            summary["failed"].append({
                "id": child.external_id or str(child.id),
                "name": child.name, "action": "removed",
                "error": f"DB persistence failed: {exc}",
            })
            continue
        summary["removed"] += 1

    try:
        sync_status, ingestion_job_id = (
            _finish_folder_operation(
                db, source, knowledge_base, remote_files, summary, warnings,
            )
        )
        db.refresh(source)
    except Exception:
        db.rollback()
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source.id,
                KnowledgeSource.organization_id == organization_id,
                KnowledgeSource.knowledge_base_id == knowledge_base_id,
                KnowledgeSource.source_type == "google_drive_folder",
            )
            .first()
        )
        if persisted_source:
            _mark_drive_source_failed(
                db, persisted_source, "Folder finalization failed",
            )
        raise

    return {
        "source_id": source.id,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
        "new_files": summary["new"],
        "modified_files": summary["modified"],
        "removed_files": summary["removed"],
        "summary": summary,
        "warnings": warnings,
    }
