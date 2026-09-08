"""Knowledge Sources business logic.

Source helpers, state transitions, sync orchestration, and freshness
derivation extracted from the Knowledge HTTP router.
"""

import json
import logging
from datetime import datetime, timezone

from ..bedrock_ingestion import start_ingestion_job
from ..google_drive_client import (
    download_drive_file,
    export_google_doc,
    is_google_doc,
)
from ..google_sheets_client import (
    fetch_sheet_values,
    get_spreadsheet_metadata,
    normalize_to_csv,
)
from ..knowledge_storage import delete_knowledge_file
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
