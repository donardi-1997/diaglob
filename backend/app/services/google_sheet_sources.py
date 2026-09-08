"""Google Sheet source orchestration.

Business logic for creating and syncing Google Sheet / Workbook
sources extracted from the Knowledge HTTP router.
"""

import json
import logging
from datetime import datetime

import httpx

from ..bedrock_ingestion import start_ingestion_job
from ..google_sheets_client import (
    fetch_sheet_values,
    get_spreadsheet_metadata,
    normalize_to_csv,
)
from ..knowledge_storage import upload_knowledge_file
from ..models import KnowledgeBase, KnowledgeSource
from .knowledge_sources import _google_source_import_mode

logger = logging.getLogger(__name__)


# ============================================================
# HELPERS
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


# ============================================================
# CREATE
# ============================================================


async def add_google_sheet(
    db,
    org_id: int,
    kb: KnowledgeBase,
    sheet_id: str,
    import_mode: str,
    sheet_name: str | None,
    spreadsheet_title: str,
    access_token: str,
) -> dict:
    """Create a Google Sheet / Workbook knowledge source.

    Returns a result dict with source_id, sync_status, ingestion_job_id,
    and name on success.

    Raises on provider / storage / validation errors; the caller
    (HTTP router) is responsible for mapping exceptions to HTTP.
    """
    knowledge_base_id = kb.id

    # --- fetch content ---
    try:
        if import_mode == "workbook":
            spreadsheet_title, csv_content = (
                await _fetch_google_workbook_content(
                    access_token, sheet_id, spreadsheet_title
                )
            )
        else:
            try:
                metadata = await get_spreadsheet_metadata(
                    access_token, sheet_id
                )
                spreadsheet_title = metadata.get("title", spreadsheet_title)
            except Exception:
                pass
            values = await fetch_sheet_values(
                access_token, sheet_id, sheet_name
            )
            csv_content = normalize_to_csv(
                values, spreadsheet_title, sheet_name
            )
    except httpx.HTTPStatusError:
        raise
    except ValueError:
        raise

    # --- empty check ---
    if not csv_content.strip():
        raise ValueError(
            "Workbook has no non-empty visible sheets"
            if import_mode == "workbook"
            else "Sheet is empty"
        )

    # --- upload to S3 ---
    filename = f"{sheet_id}_{sheet_name or 'workbook'}.csv"
    s3_result = upload_knowledge_file(
        organization_id=org_id,
        knowledge_base_id=knowledge_base_id,
        filename=filename,
        content=csv_content.encode("utf-8"),
        content_type="text/csv",
    )

    # --- create KnowledgeSource ---
    source = KnowledgeSource(
        organization_id=org_id,
        knowledge_base_id=knowledge_base_id,
        name=(
            spreadsheet_title
            if import_mode == "workbook"
            else f"{spreadsheet_title} — {sheet_name}"
        ),
        source_type="google_sheet",
        content_type="text/csv",
        s3_bucket=s3_result["bucket"],
        s3_key=s3_result["key"],
        size_bytes=len(csv_content.encode("utf-8")),
        status="uploaded",
        external_id=sheet_id,
        external_name=spreadsheet_title,
        sheet_name=sheet_name,
        sync_status="uploaded",
        metadata_json=json.dumps({"import_mode": import_mode}),
    )
    db.add(source)
    db.flush()

    # --- start ingestion ---
    ingestion_job_id = None
    sync_status = "uploaded"

    ingestion_job_id = start_ingestion_job(
        kb.external_id,
        kb.external_data_source_id,
    )
    if ingestion_job_id:
        sync_status = "indexing"
        source.ingestion_job_id = ingestion_job_id
        source.sync_status = "indexing"
    else:
        sync_status = "uploaded"
        source.sync_status = "uploaded"

    db.commit()
    db.refresh(source)

    return {
        "source_id": source.id,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
        "name": source.name,
    }


# ============================================================
# SYNC
# ============================================================


async def sync_google_sheet(
    db,
    org_id: int,
    kb: KnowledgeBase,
    source: KnowledgeSource,
    access_token: str,
) -> dict:
    """Sync an existing Google Sheet / Workbook source.

    Returns a result dict with source_id, sync_status, and
    ingestion_job_id on success.

    On provider / storage errors the source state is persisted
    (sync_status=failed) before the exception propagates to the caller.
    """
    # --- mark syncing ---
    source.sync_status = "syncing"
    source.sync_error = None
    db.flush()

    import_mode = _google_source_import_mode(source)

    # --- fetch content ---
    try:
        if import_mode == "workbook":
            spreadsheet_title, csv_content = (
                await _fetch_google_workbook_content(
                    access_token,
                    source.external_id,
                    source.external_name or source.external_id,
                )
            )
            source.external_name = spreadsheet_title
        else:
            values = await fetch_sheet_values(
                access_token,
                source.external_id,
                source.sheet_name,
            )
            csv_content = normalize_to_csv(
                values,
                source.external_name or "",
                source.sheet_name or "",
            )
    except httpx.HTTPStatusError as exc:
        from ..bedrock_ingestion import map_google_api_error

        code, msg = map_google_api_error(exc.response.status_code)
        source.sync_status = "failed"
        source.sync_error = msg
        db.commit()
        raise
    except ValueError as exc:
        source.sync_status = "failed"
        source.sync_error = str(exc)
        db.commit()
        raise

    # --- empty check ---
    if not csv_content.strip():
        source.sync_status = "failed"
        source.sync_error = (
            "Workbook has no non-empty visible sheets"
            if import_mode == "workbook" else "Sheet is empty"
        )
        db.commit()
        raise ValueError(source.sync_error)

    # --- upload to S3 ---
    filename = f"{source.external_id}_{source.sheet_name or 'workbook'}.csv"
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=kb.id,
            filename=filename,
            content=csv_content.encode("utf-8"),
            content_type="text/csv",
        )
    except Exception as exc:
        source.sync_status = "failed"
        source.sync_error = f"S3 upload failed: {exc}"
        db.commit()
        raise

    # --- update source ---
    source.s3_bucket = s3_result["bucket"]
    source.s3_key = s3_result["key"]
    source.size_bytes = len(csv_content.encode("utf-8"))
    source.status = "uploaded"
    source.last_synced_at = datetime.utcnow()

    # --- start ingestion ---
    ingestion_job_id = None
    sync_status = "uploaded"

    ingestion_job_id = start_ingestion_job(
        kb.external_id,
        kb.external_data_source_id,
    )
    if ingestion_job_id:
        sync_status = "indexing"
        source.ingestion_job_id = ingestion_job_id
        source.sync_status = "indexing"
    else:
        sync_status = "uploaded"
        source.sync_status = "uploaded"

    db.commit()
    db.refresh(source)

    return {
        "source_id": source.id,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
    }
