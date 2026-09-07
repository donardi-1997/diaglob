import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..bedrock_ingestion import (
    STATUS_FAILED,
    STATUS_INDEXING,
    STATUS_SYNCED,
    get_ingestion_status,
    map_google_api_error,
    start_ingestion_job,
)
from ..bedrock_knowledge_base import (
    BedrockProvisioningError,
    ProvisioningErrorClassification,
    ProvisioningInProgressError,
    delete_diaglob_knowledge_base,
    provision_diaglob_knowledge_base,
)
from ..db import SessionLocal, get_db
from ..google_drive_client import (
    GoogleDriveFileTooLarge,
    MAX_TOTAL_SYNC_BYTES,
    download_drive_file,
    export_google_doc,
    get_file_metadata,
    is_google_doc,
    is_supported_mime_type,
    list_folder_children,
    validate_folder_sync_limits,
)
from ..google_sheets_client import (
    extract_spreadsheet_id,
    fetch_sheet_values,
    get_spreadsheet_metadata,
    normalize_to_csv,
)
from ..knowledge_storage import (
    delete_knowledge_file,
    upload_knowledge_file,
)
from ..models import (
    GoogleConnection,
    KnowledgeBase,
    KnowledgeSource,
    OrganizationMembership,
    Store,
)
from ..permissions import has_permission
from .deps import get_allowed_store_ids, require_permission
from .google import _get_valid_google_token, _require_drive_scope

router = APIRouter()

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTS
# ============================================================

PROVISIONING_RETRY_DELAYS_SECONDS = (0, 60, 300, 900)

DRIVE_SOURCE_TYPES = (
    "google_doc",
    "google_drive_file",
    "google_drive_folder",
)

# ============================================================
# DTOs / PYDANTIC MODELS
# ============================================================


class KnowledgeBaseCreate(BaseModel):
    name: str
    scope: str = "selected_stores"
    active: bool = True
    store_ids: list[int] = []


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = None
    scope: str | None = None
    active: bool | None = None
    store_ids: list[int] | None = None


class GoogleSheetSourceRequest(BaseModel):
    spreadsheet_id: str
    spreadsheet_name: str = ""
    sheet_name: str | None = None
    import_mode: Literal["sheet", "workbook"] = "sheet"


class GoogleSyncResponse(BaseModel):
    source_id: int
    sync_status: str
    ingestion_job_id: str | None = None
    message: str = ""


class GoogleDriveFileRequest(BaseModel):
    file_id: str
    file_name: str
    mime_type: str


class GoogleDriveFolderRequest(BaseModel):
    folder_id: str
    folder_name: str


# ============================================================
# SERIALIZERS
# ============================================================


def serialize_store_short(store: Store):
    return {
        "id": store.id,
        "name": store.name,
        "country_code": store.country_code,
        "currency": store.currency,
    }


def serialize_knowledge_source(source: KnowledgeSource):
    return {
        "id": source.id,
        "organization_id": source.organization_id,
        "knowledge_base_id": source.knowledge_base_id,
        "name": source.name,
        "source_type": source.source_type,
        "content_type": source.content_type,
        "size_bytes": source.size_bytes,
        "status": source.status,
        "ingestion_job_id": source.ingestion_job_id,
        "error_message": source.error_message,
        "active": source.active,
        "created_at": (
            source.created_at.isoformat()
            if source.created_at
            else None
        ),
        "external_id": source.external_id,
        "external_name": source.external_name,
        "sheet_name": source.sheet_name,
        "last_synced_at": (
            source.last_synced_at.isoformat()
            if source.last_synced_at
            else None
        ),
        "sync_status": source.sync_status,
        "sync_error": source.sync_error,
        "external_mime_type": source.external_mime_type,
        "external_modified_at": (
            source.external_modified_at.isoformat()
            if source.external_modified_at
            else None
        ),
        "parent_source_id": source.parent_source_id,
        "external_size": source.external_size,
        "sync_generation": source.sync_generation,
    }


def serialize_knowledge_base(knowledge_base: KnowledgeBase):
    return {
        "id": knowledge_base.id,
        "organization_id": knowledge_base.organization_id,
        "name": knowledge_base.name,
        "scope": knowledge_base.scope,
        "external_id": knowledge_base.external_id,
        "external_status": knowledge_base.external_status,
        "external_last_error": knowledge_base.external_last_error,
        "provisioning_stage": knowledge_base.provisioning_stage,
        "provisioning_started_at": (
            knowledge_base.provisioning_started_at.isoformat()
            if knowledge_base.provisioning_started_at
            else None
        ),
        "provisioning_stage_started_at": (
            knowledge_base.provisioning_stage_started_at.isoformat()
            if knowledge_base.provisioning_stage_started_at
            else None
        ),
        "active": knowledge_base.active,
        "stores": [
            serialize_store_short(store)
            for store in knowledge_base.stores
            if store.active
        ],
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "role": agent.role,
                "active": agent.active,
            }
            for agent in knowledge_base.agents
        ],
    }


# ============================================================
# HELPERS — SHARED (duplicated from main.py)
# ============================================================


def resolve_member_stores(
    membership: OrganizationMembership,
    store_ids: list[int],
    db: Session,
):
    requested_ids = sorted(set(store_ids))

    if not requested_ids:
        return []

    stores = (
        db.query(Store)
        .filter(
            Store.organization_id
            == membership.organization_id,
            Store.id.in_(requested_ids),
            Store.active.is_(True),
        )
        .all()
    )

    found_ids = {store.id for store in stores}

    if found_ids != set(requested_ids):
        raise HTTPException(
            status_code=400,
            detail="One or more stores are invalid",
        )

    allowed_ids = get_allowed_store_ids(membership)

    if (
        allowed_ids is not None
        and not set(requested_ids).issubset(set(allowed_ids))
    ):
        raise HTTPException(
            status_code=403,
            detail="Store access denied",
        )

    return stores


# ============================================================
# HELPERS — KNOWLEDGE DOMAIN
# ============================================================


def _require_knowledge_base_ready(
    db: Session,
    organization_id: int,
    knowledge_base_id: int,
) -> KnowledgeBase:
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id == organization_id,
        )
        .first()
    )
    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge Base not found",
        )
    if (
        knowledge_base.external_status != "ready"
        or not knowledge_base.external_id
        or not knowledge_base.external_data_source_id
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "KNOWLEDGE_BASE_NOT_READY",
                "message": "Knowledge Base provisioning is not ready.",
                "status": knowledge_base.external_status or "pending",
            },
        )
    return knowledge_base


def _google_source_import_mode(source: KnowledgeSource) -> str:
    """Treat sources created before workbook support as single-sheet imports."""
    try:
        metadata = json.loads(source.metadata_json or "{}")
    except json.JSONDecodeError:
        return "sheet"
    return metadata.get("import_mode", "sheet")


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
    db: Session,
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


def _standalone_drive_duplicate_response(
    existing: KnowledgeSource,
) -> dict:
    if (
        existing.parent_source_id is not None
        or existing.source_type == "google_drive_folder"
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DRIVE_SOURCE_CONFLICT",
                "message": (
                    "Drive object already exists in this "
                    "knowledge base with a conflicting "
                    "folder relationship."
                ),
                "source_id": existing.id,
            },
        )
    return {
        "source_id": existing.id,
        "name": existing.name,
        "sync_status": existing.sync_status or "synced",
        "message": "Source already exists",
    }


def _drive_conflict_reason(existing: KnowledgeSource) -> str:
    if existing.source_type == "google_drive_folder":
        return "Drive object already exists as a folder source"
    if existing.parent_source_id is not None:
        return "File already belongs to another folder source"
    return "File already exists as a standalone Drive source"


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
    db: Session,
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


def _finish_folder_operation(
    db: Session,
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


def _start_drive_source_ingestion(
    db: Session,
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
    db: Session,
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
# PROVISIONING
# ============================================================


def run_knowledge_base_provisioning(knowledge_base_id: int) -> None:
    """Provision in the background so customers never wait on AWS setup."""
    for attempt, delay in enumerate(PROVISIONING_RETRY_DELAYS_SECONDS, start=1):
        if delay:
            time.sleep(delay)
        db = SessionLocal()
        try:
            knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
            if not knowledge_base or knowledge_base.external_status == "ready":
                return
            try:
                provision_diaglob_knowledge_base(db, knowledge_base)
                logger.info(
                    "knowledge_base_provisioning_attempt_succeeded organization_id=%s knowledge_base_id=%s attempt=%s",
                    knowledge_base.organization_id, knowledge_base.id, attempt,
                )
                return
            except ProvisioningInProgressError:
                return
            except BedrockProvisioningError as error:
                retry_scheduled = (
                    error.classification in {
                        ProvisioningErrorClassification.RETRYABLE_INFRASTRUCTURE,
                        ProvisioningErrorClassification.PLATFORM_CONFIGURATION_ERROR,
                    }
                    and attempt < len(PROVISIONING_RETRY_DELAYS_SECONDS)
                )
                logger.error(
                    "knowledge_base_provisioning_attempt_failed organization_id=%s knowledge_base_id=%s attempt=%s stage=%s classification=%s retry_scheduled=%s",
                    knowledge_base.organization_id, knowledge_base.id, attempt,
                    error.resource, error.classification, retry_scheduled,
                )
                if retry_scheduled:
                    knowledge_base.external_status = "retrying"
                    knowledge_base.provisioning_stage = "retrying"
                    knowledge_base.provisioning_stage_started_at = datetime.now(timezone.utc)
                    db.commit()
                else:
                    return
        finally:
            db.close()


def schedule_knowledge_base_provisioning(knowledge_base_id: int) -> None:
    """Run startup recovery outside the request lifecycle."""
    threading.Thread(
        target=run_knowledge_base_provisioning,
        args=(knowledge_base_id,),
        daemon=True,
    ).start()


def reconcile_knowledge_base_provisioning() -> None:
    """Resume stranded non-terminal provisioning after a process restart."""
    db = SessionLocal()
    try:
        try:
            knowledge_bases = db.query(KnowledgeBase).filter(
                KnowledgeBase.active.is_(True),
                KnowledgeBase.external_status.in_(("pending", "provisioning", "retrying")),
            ).all()
        except OperationalError as error:
            db.rollback()
            if "no such column" in str(error).lower() and "knowledge_bases.external_status" in str(error):
                logger.warning("Skipping Knowledge Base provisioning reconciliation until migration 007 is applied")
                return
            raise
        now = datetime.now(timezone.utc)
        for knowledge_base in knowledge_bases:
            if knowledge_base.external_status == "provisioning":
                knowledge_base.external_status = "retrying"
                knowledge_base.provisioning_stage = "retrying"
                knowledge_base.provisioning_stage_started_at = now
        db.commit()
        for knowledge_base in knowledge_bases:
            logger.info(
                "Reconciling Knowledge Base provisioning: organization_id=%s knowledge_base_id=%s status=%s",
                knowledge_base.organization_id,
                knowledge_base.id,
                knowledge_base.external_status,
            )
            schedule_knowledge_base_provisioning(knowledge_base.id)
    finally:
        db.close()


# ============================================================
# ROUTES — KNOWLEDGE BASE CRUD
# ============================================================


@router.get("/api/knowledge-bases")
def list_knowledge_bases(
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    query = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.organization_id
            == membership.organization_id
        )
        .order_by(KnowledgeBase.name.asc())
    )

    knowledge_bases = query.all()

    allowed_store_ids = get_allowed_store_ids(membership)

    if allowed_store_ids is not None:
        allowed_set = set(allowed_store_ids)

        knowledge_bases = [
            knowledge_base
            for knowledge_base in knowledge_bases
            if (
                knowledge_base.scope == "organization"
                or bool(
                    {
                        store.id
                        for store in knowledge_base.stores
                    }.intersection(allowed_set)
                )
            )
        ]

    return {
        "items": [
            serialize_knowledge_base(knowledge_base)
            for knowledge_base in knowledge_bases
        ],
        "total": len(knowledge_bases),
    }


@router.get(
    "/api/knowledge-bases/{knowledge_base_id}"
)
def get_knowledge_base(
    knowledge_base_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    allowed_store_ids = get_allowed_store_ids(membership)

    if (
        allowed_store_ids is not None
        and knowledge_base.scope != "organization"
    ):
        kb_store_ids = {
            store.id for store in knowledge_base.stores
        }

        if not kb_store_ids.intersection(allowed_store_ids):
            raise HTTPException(
                status_code=404,
                detail="Knowledge base not found",
            )

    return serialize_knowledge_base(knowledge_base)


@router.post("/api/knowledge-bases")
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    background_tasks: BackgroundTasks,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    name = payload.name.strip()
    scope = payload.scope.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Knowledge base name is required",
        )

    if scope not in {"organization", "selected_stores"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid knowledge base scope",
        )

    if (
        scope == "organization"
        and not membership.all_stores
        and membership.role != "owner"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Organization-wide knowledge bases "
                "require all-store access"
            ),
        )

    if scope == "organization":
        stores = []
    else:
        stores = resolve_member_stores(
            membership, payload.store_ids, db
        )

        if not stores:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Selected-store knowledge bases "
                    "require at least one store"
                ),
            )

    knowledge_base = KnowledgeBase(
        organization_id=membership.organization_id,
        name=name,
        scope=scope,
        external_status="pending",
        provisioning_stage="queued",
        provisioning_started_at=datetime.now(timezone.utc),
        provisioning_stage_started_at=datetime.now(timezone.utc),
        active=payload.active,
    )

    knowledge_base.stores = stores

    db.add(knowledge_base)
    db.commit()
    db.refresh(knowledge_base)

    background_tasks.add_task(run_knowledge_base_provisioning, knowledge_base.id)

    return serialize_knowledge_base(knowledge_base)


@router.patch(
    "/api/knowledge-bases/{knowledge_base_id}"
)
def update_knowledge_base(
    knowledge_base_id: int,
    payload: KnowledgeBaseUpdate,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    if payload.name is not None:
        name = payload.name.strip()

        if not name:
            raise HTTPException(
                status_code=400,
                detail="Knowledge base name is required",
            )

        knowledge_base.name = name

    next_scope = (
        payload.scope.strip()
        if payload.scope is not None
        else knowledge_base.scope
    )

    if next_scope not in {"organization", "selected_stores"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid knowledge base scope",
        )

    if (
        next_scope == "organization"
        and not membership.all_stores
        and membership.role != "owner"
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Organization-wide knowledge bases "
                "require all-store access"
            ),
        )

    knowledge_base.scope = next_scope

    if payload.active is not None:
        knowledge_base.active = payload.active

    if next_scope == "organization":
        knowledge_base.stores = []

    elif payload.store_ids is not None:
        stores = resolve_member_stores(
            membership, payload.store_ids, db
        )

        if not stores:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Selected-store knowledge bases "
                    "require at least one store"
                ),
            )

        knowledge_base.stores = stores

    db.commit()
    db.refresh(knowledge_base)

    return serialize_knowledge_base(knowledge_base)


@router.delete("/api/knowledge-bases/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == knowledge_base_id,
        KnowledgeBase.organization_id == membership.organization_id,
    ).first()
    if not knowledge_base:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    try:
        delete_diaglob_knowledge_base(db, knowledge_base)
    except BedrockProvisioningError as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "KNOWLEDGE_BASE_DELETION_FAILED",
                "message": "Knowledge Base deletion could not be completed.",
            },
        ) from error
    logger.info(
        "Knowledge Base deleted: organization_id=%s knowledge_base_id=%s actor_user_id=%s",
        membership.organization_id, knowledge_base_id, membership.user_id,
    )
    return {"id": knowledge_base_id, "deleted": True}


# ============================================================
# ROUTES — RETRY PROVISIONING
# ============================================================


@router.post(
    "/api/knowledge-bases/{knowledge_base_id}/retry-provisioning"
)
def retry_knowledge_base_provisioning(
    knowledge_base_id: int,
    background_tasks: BackgroundTasks,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id == membership.organization_id,
        )
        .first()
    )

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    if knowledge_base.external_status in ("provisioning", "retrying"):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PROVISIONING_IN_PROGRESS",
                "message": "Knowledge Base provisioning is already in progress.",
            },
        )

    if knowledge_base.external_status not in ("pending", "failed"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_PROVISIONING_STATE",
                "message": f"Cannot retry provisioning for KnowledgeBase with status: {knowledge_base.external_status}",
            },
        )

    previous_status = knowledge_base.external_status
    logger.info(
        "knowledge_base_manual_retry_requested organization_id=%s knowledge_base_id=%s previous_status=%s",
        knowledge_base.organization_id,
        knowledge_base.id,
        previous_status,
    )
    now = datetime.now(timezone.utc)
    updated = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base.id,
            KnowledgeBase.organization_id == knowledge_base.organization_id,
            KnowledgeBase.external_status == previous_status,
        )
        .update(
            {
                KnowledgeBase.external_status: "retrying",
                KnowledgeBase.external_last_error: None,
                KnowledgeBase.provisioning_stage: "queued",
                KnowledgeBase.provisioning_started_at: now,
                KnowledgeBase.provisioning_stage_started_at: now,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        db.refresh(knowledge_base)
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PROVISIONING_STATE_CHANGED",
                "message": "Knowledge Base provisioning state changed. Try again.",
            },
        )
    db.commit()
    db.refresh(knowledge_base)
    background_tasks.add_task(run_knowledge_base_provisioning, knowledge_base.id)
    logger.info(
        "knowledge_base_manual_retry_scheduled organization_id=%s knowledge_base_id=%s previous_status=%s status=%s stage=%s",
        knowledge_base.organization_id,
        knowledge_base.id,
        previous_status,
        knowledge_base.external_status,
        knowledge_base.provisioning_stage,
    )

    return serialize_knowledge_base(knowledge_base)


# ============================================================
# ROUTES — KNOWLEDGE SOURCES
# ============================================================


@router.get(
    "/api/knowledge-bases/{knowledge_base_id}/sources"
)
def list_knowledge_sources(
    knowledge_base_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id
            == membership.organization_id,
        )
        .first()
    )

    if not knowledge_base:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    sources = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.organization_id
            == membership.organization_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
            KnowledgeSource.active.is_(True),
        )
        .order_by(KnowledgeSource.created_at.desc())
        .all()
    )

    google_connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id
            == membership.organization_id,
        )
        .first()
    )

    return {
        "items": [
            {
                **serialize_knowledge_source(source),
                "freshness": _derive_freshness(
                    source, google_connection,
                ),
            }
            for source in sources
        ],
        "total": len(sources),
    }


@router.post(
    "/api/knowledge-bases/{knowledge_base_id}/sources"
)
async def upload_knowledge_source(
    knowledge_base_id: int,
    file: UploadFile = File(...),
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    knowledge_base = _require_knowledge_base_ready(
        db,
        membership.organization_id,
        knowledge_base_id,
    )

    filename = file.filename or "document"

    extension = (
        filename.rsplit(".", 1)[-1].lower()
        if "." in filename
        else ""
    )

    allowed_extensions = {
        "pdf", "txt", "md", "html", "doc", "docx", "csv", "xlsx",
    }

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type",
        )

    content = await file.read()

    max_size = 25 * 1024 * 1024

    if not content:
        raise HTTPException(
            status_code=400,
            detail="File is empty",
        )

    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail="File exceeds 25 MB limit",
        )

    try:
        uploaded = upload_knowledge_file(
            organization_id=membership.organization_id,
            knowledge_base_id=knowledge_base.id,
            filename=filename,
            content=content,
            content_type=file.content_type,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Unable to upload knowledge document",
        ) from exc

    source = KnowledgeSource(
        organization_id=membership.organization_id,
        knowledge_base_id=knowledge_base.id,
        name=filename,
        source_type="file",
        content_type=file.content_type,
        s3_bucket=uploaded["bucket"],
        s3_key=uploaded["key"],
        size_bytes=len(content),
        status="uploaded",
        active=True,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return serialize_knowledge_source(source)


@router.delete(
    "/api/knowledge-bases/{knowledge_base_id}/sources/{source_id}"
)
def delete_knowledge_source(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    kb = _require_knowledge_base_ready(
        db,
        membership.organization_id,
        knowledge_base_id,
    )
    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.organization_id
            == membership.organization_id,
            KnowledgeSource.knowledge_base_id
            == knowledge_base_id,
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Knowledge source not found",
        )

    sources_to_delete = [source]
    if source.source_type == "google_drive_folder":
        sources_to_delete.extend(
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.parent_source_id == source.id,
                KnowledgeSource.organization_id
                == membership.organization_id,
                KnowledgeSource.knowledge_base_id
                == knowledge_base_id,
                KnowledgeSource.active.is_(True),
            )
            .all()
        )

    # A folder is metadata only; its children own the S3 artifacts.
    try:
        for item in sources_to_delete:
            if item.s3_bucket and item.s3_key:
                delete_knowledge_file(
                    item.s3_bucket, item.s3_key,
                )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="Unable to delete knowledge document",
        ) from exc

    for item in sources_to_delete:
        item.active = False
        item.status = "deleted"
    db.flush()

    # Trigger Bedrock reindex to remove deleted content from vector index
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

    db.commit()

    return {
        "id": source.id,
        "deleted": True,
        "reindex_status": reindex_status,
        "ingestion_job_id": ingestion_job_id,
    }


# ============================================================
# ROUTES — GOOGLE SHEET KNOWLEDGE SOURCES
# ============================================================


@router.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "google-sheet"
)
async def add_google_sheet_source(
    knowledge_base_id: int,
    payload: GoogleSheetSourceRequest,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(db, org_id, knowledge_base_id)

    # Validate spreadsheet ID
    sheet_id = extract_spreadsheet_id(payload.spreadsheet_id)
    if not sheet_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid spreadsheet ID or URL",
        )
    if payload.import_mode == "sheet" and not payload.sheet_name:
        raise HTTPException(
            status_code=400,
            detail="Sheet name is required for sheet imports",
        )
    source_sheet_name = (
        payload.sheet_name if payload.import_mode == "sheet" else None
    )

    # Check for duplicate source in same KB
    candidates = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.external_id == sheet_id,
            KnowledgeSource.source_type == "google_sheet",
            KnowledgeSource.active.is_(True),
        )
        .all()
    )
    existing = next(
        (
            source for source in candidates
            if _google_source_import_mode(source) == payload.import_mode
            and source.sheet_name == source_sheet_name
        ),
        None,
    )

    if existing:
        return {
            "source_id": existing.id,
            "sync_status": existing.sync_status or "synced",
            "message": "Source already exists",
        }

    # Get Google connection
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id == org_id,
            GoogleConnection.status == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail="Google not connected",
        )

    access_token = _get_valid_google_token(connection, db)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": "Google connection expired. Please reconnect.",
            },
        )

    spreadsheet_title = payload.spreadsheet_name or sheet_id
    try:
        if payload.import_mode == "workbook":
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
                access_token, sheet_id, source_sheet_name
            )
            csv_content = normalize_to_csv(
                values, spreadsheet_title, source_sheet_name
            )
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(exc.response.status_code)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if not csv_content.strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "Workbook has no non-empty visible sheets"
                if payload.import_mode == "workbook"
                else "Sheet is empty"
            ),
        )

    # Upload to S3
    filename = f"{sheet_id}_{source_sheet_name or 'workbook'}.csv"
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=csv_content.encode("utf-8"),
            content_type="text/csv",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {exc}",
        ) from exc

    # Create KnowledgeSource
    source = KnowledgeSource(
        organization_id=org_id,
        knowledge_base_id=knowledge_base_id,
        name=(
            spreadsheet_title
            if payload.import_mode == "workbook"
            else f"{spreadsheet_title} — {source_sheet_name}"
        ),
        source_type="google_sheet",
        content_type="text/csv",
        s3_bucket=s3_result["bucket"],
        s3_key=s3_result["key"],
        size_bytes=len(csv_content.encode("utf-8")),
        status="uploaded",
        external_id=sheet_id,
        external_name=spreadsheet_title,
        sheet_name=source_sheet_name,
        sync_status="uploaded",
        metadata_json=json.dumps({"import_mode": payload.import_mode}),
    )
    db.add(source)
    db.flush()

    # Start Bedrock ingestion
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
# ROUTES — SOURCE SYNC (SHEET)
# ============================================================


@router.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/sync"
)
async def sync_google_sheet_source(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(db, org_id, knowledge_base_id)

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.organization_id == org_id,
            KnowledgeSource.source_type == "google_sheet",
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Google Sheet source not found",
        )

    # Idempotency: don't re-sync if already syncing
    if source.sync_status in ("syncing", "indexing"):
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "ingestion_job_id": source.ingestion_job_id,
            "message": "Sync already in progress",
        }

    # Get Google connection
    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id == org_id,
            GoogleConnection.status == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": "Google not connected. Please reconnect.",
            },
        )

    access_token = _get_valid_google_token(connection, db)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": "Google connection expired. Please reconnect.",
            },
        )

    # Mark as syncing
    source.sync_status = "syncing"
    source.sync_error = None
    db.flush()

    import_mode = _google_source_import_mode(source)

    # Fetch the selected tab or every visible workbook tab.
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
        code, msg = map_google_api_error(exc.response.status_code)
        source.sync_status = "failed"
        source.sync_error = msg
        db.commit()
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except ValueError as exc:
        source.sync_status = "failed"
        source.sync_error = str(exc)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if not csv_content.strip():
        source.sync_status = "failed"
        source.sync_error = (
            "Workbook has no non-empty visible sheets"
            if import_mode == "workbook" else "Sheet is empty"
        )
        db.commit()
        raise HTTPException(
            status_code=400,
            detail=source.sync_error,
        )

    # Upload to S3
    filename = f"{source.external_id}_{source.sheet_name or 'workbook'}.csv"
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=csv_content.encode("utf-8"),
            content_type="text/csv",
        )
    except Exception as exc:
        source.sync_status = "failed"
        source.sync_error = f"S3 upload failed: {exc}"
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {exc}",
        ) from exc

    # Update source
    source.s3_bucket = s3_result["bucket"]
    source.s3_key = s3_result["key"]
    source.size_bytes = len(csv_content.encode("utf-8"))
    source.status = "uploaded"
    source.last_synced_at = datetime.utcnow()

    # Start Bedrock ingestion
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


# ============================================================
# ROUTES — INGESTION STATUS
# ============================================================


@router.get(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/ingestion-status"
)
def check_ingestion_status(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id == org_id,
        )
        .first()
    )

    if not kb:
        raise HTTPException(
            status_code=404,
            detail="Knowledge Base not found",
        )

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.organization_id == org_id,
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )

    # If not in indexing state, return current status
    if source.sync_status != "indexing":
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

    # Guard: do not call Bedrock if KB is not ready.
    if kb.external_status != "ready":
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

    # Check Bedrock ingestion status
    if (
        not source.ingestion_job_id
        or not kb.external_id
        or not kb.external_data_source_id
    ):
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "last_synced_at": (
                source.last_synced_at.isoformat()
                if source.last_synced_at
                else None
            ),
        }

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
# ROUTES — GOOGLE DOC SOURCE
# ============================================================


@router.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "google-doc"
)
async def add_google_doc_source(
    knowledge_base_id: int,
    request: GoogleDriveFileRequest,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(db, org_id, knowledge_base_id)

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id == org_id,
            GoogleConnection.status == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": "Google not connected. Please connect Google first.",
            },
        )

    _require_drive_scope(connection)

    existing = _find_active_drive_source(
        db, org_id, knowledge_base_id, request.file_id,
    )

    if existing:
        return _standalone_drive_duplicate_response(existing)

    access_token = _get_valid_google_token(connection, db)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": "Google connection expired.",
            },
        )

    # Export Google Doc to text/plain
    try:
        content = await export_google_doc(
            access_token, request.file_id, "text/plain",
        )
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(exc.response.status_code)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except (GoogleDriveFileTooLarge, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "GOOGLE_DOWNLOAD_FAILED", "message": str(exc)},
        ) from exc

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Document is empty",
        )

    # Upload to S3
    filename = f"{request.file_name}.txt"
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=content,
            content_type="text/plain",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {exc}",
        ) from exc

    # Get remote modified time
    remote_meta = None
    try:
        remote_meta = await get_file_metadata(
            access_token, request.file_id
        )
    except Exception:
        pass

    modified_at = _parse_google_modified_at(
        remote_meta.get("modifiedTime") if remote_meta else None
    )

    source = KnowledgeSource(
        knowledge_base_id=knowledge_base_id,
        organization_id=org_id,
        name=request.file_name,
        source_type="google_doc",
        s3_bucket=s3_result["bucket"],
        s3_key=s3_result["key"],
        size_bytes=len(content),
        status="uploaded",
        external_id=request.file_id,
        external_name=request.file_name,
        external_mime_type="application/vnd.google-apps.document",
        external_modified_at=modified_at,
        last_synced_at=datetime.utcnow(),
        sync_status="uploaded",
    )
    try:
        _persist_new_drive_source(db, source, s3_result)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SOURCE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    sync_status, ingestion_job_id = _start_drive_source_ingestion(
        db, source, kb
    )

    return {
        "source_id": source.id,
        "name": source.name,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
    }


# ============================================================
# ROUTES — DRIVE FILE SOURCE
# ============================================================


@router.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "google-drive-file"
)
async def add_google_drive_file_source(
    knowledge_base_id: int,
    request: GoogleDriveFileRequest,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(db, org_id, knowledge_base_id)

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id == org_id,
            GoogleConnection.status == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": "Google not connected.",
            },
        )

    _require_drive_scope(connection)

    if not is_supported_mime_type(request.mime_type):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": f"File type '{request.mime_type}' is not supported.",
            },
        )

    existing = _find_active_drive_source(
        db, org_id, knowledge_base_id, request.file_id,
    )

    if existing:
        return _standalone_drive_duplicate_response(existing)

    access_token = _get_valid_google_token(connection, db)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": "Google connection expired.",
            },
        )

    # Download file from Drive
    try:
        content = await download_drive_file(access_token, request.file_id)
    except (GoogleDriveFileTooLarge, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": str(exc)},
        ) from exc
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(exc.response.status_code)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "GOOGLE_DOWNLOAD_FAILED", "message": str(exc)},
        ) from exc

    if not content:
        raise HTTPException(
            status_code=400,
            detail="File is empty",
        )

    # Upload to S3
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", request.file_name)
    filename = f"{safe_name}"
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            content=content,
            content_type=request.mime_type,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"S3 upload failed: {exc}",
        ) from exc

    # Get remote metadata
    remote_meta = None
    try:
        remote_meta = await get_file_metadata(access_token, request.file_id)
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
        organization_id=org_id,
        name=request.file_name,
        source_type="google_drive_file",
        content_type=request.mime_type,
        s3_bucket=s3_result["bucket"],
        s3_key=s3_result["key"],
        size_bytes=len(content),
        status="uploaded",
        external_id=request.file_id,
        external_name=request.file_name,
        external_mime_type=request.mime_type,
        external_modified_at=modified_at,
        external_size=ext_size,
        last_synced_at=datetime.utcnow(),
        sync_status="uploaded",
    )
    try:
        _persist_new_drive_source(db, source, s3_result)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SOURCE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    sync_status, ingestion_job_id = _start_drive_source_ingestion(
        db, source, kb
    )

    return {
        "source_id": source.id,
        "name": source.name,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
    }


# ============================================================
# ROUTES — DRIVE FOLDER SOURCE
# ============================================================


@router.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "google-drive-folder"
)
async def add_google_drive_folder_source(
    knowledge_base_id: int,
    request: GoogleDriveFolderRequest,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(db, org_id, knowledge_base_id)

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id == org_id,
            GoogleConnection.status == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": "Google not connected.",
            },
        )

    _require_drive_scope(connection)

    existing = _find_active_drive_source(
        db, org_id, knowledge_base_id, request.folder_id,
    )

    if existing:
        if existing.source_type != "google_drive_folder":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DRIVE_SOURCE_CONFLICT",
                    "message": _drive_conflict_reason(existing),
                    "source_id": existing.id,
                },
            )
        return {
            "source_id": existing.id,
            "name": existing.name,
            "sync_status": existing.sync_status or "synced",
            "message": "Folder source already exists",
        }

    # List folder children to validate
    access_token = _get_valid_google_token(connection, db)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": "Google connection expired.",
            },
        )

    try:
        result = await list_folder_children(access_token, request.folder_id)
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(exc.response.status_code)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "GOOGLE_FOLDER_LIST_FAILED",
                "message": str(exc),
            },
        ) from exc

    files = result.get("files", [])

    if result.get("limit_exceeded"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": "Folder exceeds the configured maximum file count.",
            },
        )

    # Validate limits
    limit_error = validate_folder_sync_limits(files)
    if limit_error:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": limit_error,
            },
        )

    summary = _folder_summary()
    warnings = []

    # Persist the metadata-only parent before creating child artifacts.
    source = KnowledgeSource(
        knowledge_base_id=knowledge_base_id,
        organization_id=org_id,
        name=request.folder_name,
        source_type="google_drive_folder",
        s3_bucket="",
        s3_key="",
        status="uploaded",
        external_id=request.folder_id,
        external_name=request.folder_name,
        sync_status="uploaded",
        metadata_json=json.dumps({
            "file_count": len(files),
            "last_synced_files": [
                _folder_file_record(f) for f in files
            ],
            "summary": summary,
        }),
    )
    try:
        db.add(source)
        db.commit()
        db.refresh(source)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SOURCE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    downloaded_bytes = 0
    for f in files:
        file_id = f["id"]
        file_name = f.get("name", "Untitled")
        mime_type = f.get("mimeType", "")

        child_existing = _find_active_drive_source(
            db, org_id, knowledge_base_id, file_id,
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
                organization_id=org_id,
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
            organization_id=org_id,
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
                db, source, kb, files, summary, warnings,
            )
        )
        db.refresh(source)
    except Exception as exc:
        db.rollback()
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source.id,
                KnowledgeSource.organization_id == org_id,
                KnowledgeSource.knowledge_base_id == knowledge_base_id,
            )
            .first()
        )
        if persisted_source:
            _mark_drive_source_failed(
                db, persisted_source, f"Folder finalization failed: {exc}",
            )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "FOLDER_FINALIZATION_FAILED",
                "message": str(exc),
            },
        ) from exc

    return {
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


# ============================================================
# ROUTES — SYNC DRIVE FOLDER
# ============================================================


@router.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/sync-folder"
)
async def sync_drive_folder(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(db, org_id, knowledge_base_id)

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.organization_id == org_id,
            KnowledgeSource.source_type == "google_drive_folder",
            KnowledgeSource.active.is_(True),
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Folder source not found",
        )

    # Idempotency
    if source.sync_status in ("syncing", "indexing"):
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "message": "Sync already in progress",
        }

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id == org_id,
            GoogleConnection.status == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": "Google not connected.",
            },
        )

    _require_drive_scope(connection)

    access_token = _get_valid_google_token(connection, db)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": "Google connection expired.",
            },
        )

    source.sync_status = "syncing"
    source.sync_error = None
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYNC_STATE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

    # List current folder children
    try:
        result = await list_folder_children(
            access_token, source.external_id
        )
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(exc.response.status_code)
        _mark_drive_source_failed(db, source, msg)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except Exception as exc:
        error = f"Unable to list Google Drive folder: {exc}"
        _mark_drive_source_failed(db, source, error)
        raise HTTPException(
            status_code=502,
            detail={
                "code": "GOOGLE_FOLDER_LIST_FAILED",
                "message": error,
            },
        ) from exc

    remote_files = result.get("files", [])

    if result.get("limit_exceeded"):
        source.sync_status = "failed"
        source.sync_error = (
            "Folder exceeds the configured maximum file count"
        )
        db.commit()
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": source.sync_error,
            },
        )

    limit_error = validate_folder_sync_limits(remote_files)
    if limit_error:
        source.sync_status = "failed"
        source.sync_error = limit_error
        db.commit()
        raise HTTPException(
            status_code=400,
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": limit_error,
            },
        )

    # Load existing children from DB
    existing_children = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.parent_source_id == source.id,
            KnowledgeSource.organization_id == org_id,
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
                db, org_id, knowledge_base_id, fid,
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

    # Detect removed
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
                organization_id=org_id,
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
            organization_id=org_id,
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
                organization_id=org_id,
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
                db, source, kb, remote_files, summary, warnings,
            )
        )
        db.refresh(source)
    except Exception as exc:
        db.rollback()
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source_id,
                KnowledgeSource.organization_id == org_id,
                KnowledgeSource.knowledge_base_id == knowledge_base_id,
                KnowledgeSource.source_type == "google_drive_folder",
            )
            .first()
        )
        if persisted_source:
            _mark_drive_source_failed(
                db, persisted_source, f"Folder finalization failed: {exc}",
            )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "FOLDER_FINALIZATION_FAILED",
                "message": str(exc),
            },
        ) from exc

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


# ============================================================
# ROUTES — SYNC SINGLE DRIVE FILE OR DOC
# ============================================================


@router.post(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/sync-drive-file"
)
async def sync_drive_file_source(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    kb = _require_knowledge_base_ready(db, org_id, knowledge_base_id)

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.organization_id == org_id,
            KnowledgeSource.source_type.in_([
                "google_doc",
                "google_drive_file",
            ]),
            KnowledgeSource.active.is_(True),
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Drive source not found",
        )

    if source.parent_source_id is not None:
        parent = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source.parent_source_id,
                KnowledgeSource.organization_id == org_id,
                KnowledgeSource.knowledge_base_id == knowledge_base_id,
                KnowledgeSource.source_type == "google_drive_folder",
                KnowledgeSource.active.is_(True),
            )
            .first()
        )
        if not parent:
            raise HTTPException(
                status_code=404,
                detail="Drive source parent not found",
            )

    # Idempotency
    if source.sync_status in ("syncing", "indexing"):
        return {
            "source_id": source.id,
            "sync_status": source.sync_status,
            "message": "Sync already in progress",
        }

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id == org_id,
            GoogleConnection.status == "connected",
        )
        .first()
    )

    if not connection:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "GOOGLE_DISCONNECTED",
                "message": "Google not connected.",
            },
        )

    _require_drive_scope(connection)

    access_token = _get_valid_google_token(connection, db)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "GOOGLE_TOKEN_EXPIRED",
                "message": "Google connection expired.",
            },
        )

    source.sync_status = "syncing"
    source.sync_error = None
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SYNC_STATE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

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
    except httpx.HTTPStatusError as exc:
        code, msg = map_google_api_error(exc.response.status_code)
        _mark_drive_source_failed(db, source, msg)
        raise HTTPException(
            status_code=exc.response.status_code,
            detail={"code": code, "message": msg},
        ) from exc
    except (GoogleDriveFileTooLarge, ValueError) as exc:
        error = str(exc)
        _mark_drive_source_failed(db, source, error)
        raise HTTPException(
            status_code=400,
            detail={"code": "FILE_TOO_LARGE", "message": error},
        ) from exc
    except Exception as exc:
        error = f"Google Drive download failed: {exc}"
        _mark_drive_source_failed(db, source, error)
        raise HTTPException(
            status_code=502,
            detail={"code": "GOOGLE_DOWNLOAD_FAILED", "message": error},
        ) from exc

    if not content:
        _mark_drive_source_failed(db, source, "File is empty")
        raise HTTPException(
            status_code=400,
            detail="File is empty",
        )

    # Upload and durably repoint before deleting the old artifact.
    old_bucket = source.s3_bucket
    old_key = source.s3_key
    safe_name = re.sub(
        r"[^A-Za-z0-9._-]+", "-",
        source.external_name or source.name,
    )
    try:
        s3_result = upload_knowledge_file(
            organization_id=org_id,
            knowledge_base_id=knowledge_base_id,
            filename=safe_name,
            content=content,
            content_type=new_mime,
        )
    except Exception as exc:
        error = f"S3 upload failed: {exc}"
        _mark_drive_source_failed(db, source, error)
        raise HTTPException(
            status_code=500,
            detail=error,
        ) from exc

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
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source_id,
                KnowledgeSource.organization_id == org_id,
                KnowledgeSource.knowledge_base_id == knowledge_base_id,
            )
            .first()
        )
        if persisted_source:
            _mark_drive_source_failed(
                db, persisted_source, f"DB persistence failed: {exc}",
            )
        raise HTTPException(
            status_code=500,
            detail={
                "code": "SOURCE_PERSISTENCE_FAILED",
                "message": str(exc),
            },
        ) from exc

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
                db, source, kb, cleanup_warning,
            )
        )
        db.refresh(source)
    except Exception as exc:
        db.rollback()
        persisted_source = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id == source_id,
                KnowledgeSource.organization_id == org_id,
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
        raise HTTPException(
            status_code=500,
            detail={
                "code": "INGESTION_STATE_FAILED",
                "message": str(exc),
            },
        ) from exc

    return {
        "source_id": source.id,
        "sync_status": sync_status,
        "ingestion_job_id": ingestion_job_id,
        "sync_error": source.sync_error,
        "warning": cleanup_warning,
    }


# ============================================================
# ROUTES — SOURCE FRESHNESS
# ============================================================


@router.get(
    "/api/knowledge-bases/"
    "{knowledge_base_id}/sources/"
    "{source_id}/freshness"
)
def get_source_freshness(
    knowledge_base_id: int,
    source_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.read")
    ),
    db: Session = Depends(get_db),
):
    org_id = membership.organization_id

    source = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.id == source_id,
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.organization_id == org_id,
        )
        .first()
    )

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found",
        )

    connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id == org_id,
        )
        .first()
    )

    freshness = _derive_freshness(source, connection)

    return {
        "source_id": source.id,
        "freshness": freshness,
        "last_synced_at": (
            source.last_synced_at.isoformat()
            if source.last_synced_at
            else None
        ),
        "external_modified_at": (
            source.external_modified_at.isoformat()
            if source.external_modified_at
            else None
        ),
        "sync_status": source.sync_status,
        "source_type": source.source_type,
    }
