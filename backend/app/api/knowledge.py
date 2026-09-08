import logging
import re
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
from sqlalchemy.orm import Session

from ..bedrock_ingestion import (
    map_google_api_error,
)
from ..bedrock_knowledge_base import (
    BedrockProvisioningError,
)
from ..services.knowledge_bases import (
    KnowledgeBaseAccessError,
    KnowledgeBaseNotFoundError,
    InvalidKnowledgeBaseScopeError,
    InvalidStoreSelectionError,
    create_knowledge_base as svc_create_knowledge_base,
    delete_knowledge_base as svc_delete_knowledge_base,
    get_knowledge_base as svc_get_knowledge_base,
    list_knowledge_bases as svc_list_knowledge_bases,
    retry_knowledge_base_provisioning as svc_retry_knowledge_base_provisioning,
    update_knowledge_base as svc_update_knowledge_base,
)
from ..services.knowledge_ingestion import (
    SourceNotFoundError as IngestionSourceNotFoundError,
    refresh_source_ingestion_status as svc_refresh_source_ingestion_status,
    trigger_source_reindex as svc_trigger_source_reindex,
    is_source_sync_in_progress as svc_is_source_sync_in_progress,
)
from ..services.knowledge_provisioning import (
    run_knowledge_base_provisioning,
)
from ..services.knowledge_source_lifecycle import (
    SourceNotFoundError as SourceLifecycleNotFoundError,
    SourceDeletionError,
    list_knowledge_sources as svc_list_knowledge_sources,
    upload_source_file as svc_upload_source_file,
    collect_sources_to_delete as svc_collect_sources_to_delete,
    delete_source_artifacts as svc_delete_source_artifacts,
    deactivate_sources as svc_deactivate_sources,
)
from ..services.knowledge_sources import (
    _derive_freshness,
    _find_active_drive_source,
    _google_source_import_mode,
    _mark_drive_source_failed,
    add_google_drive_folder,
    sync_google_drive_folder,
)
from ..services.drive_file_sources import (
    add_google_doc,
    add_drive_file,
    sync_drive_file,
    _EmptyContentError,
    DriveSourceConflictError,
)
from ..services.google_sheet_sources import (
    add_google_sheet,
    sync_google_sheet,
)
from ..db import get_db
from ..google_drive_client import (
    GoogleDriveFileTooLarge,
    is_supported_mime_type,
)
from ..google_sheets_client import extract_spreadsheet_id
from ..models import (
    GoogleConnection,
    KnowledgeBase,
    KnowledgeSource,
    OrganizationMembership,
    Store,
)
from .deps import get_allowed_store_ids, require_permission
from .google import _get_valid_google_token, _require_drive_scope

router = APIRouter()

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTS
# ============================================================


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


# ============================================================
# HTTP-SPECIFIC HELPERS
# ============================================================


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
    knowledge_bases = svc_list_knowledge_bases(
        db, membership.organization_id,
    )

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
    try:
        knowledge_base = svc_get_knowledge_base(
            db,
            membership.organization_id,
            knowledge_base_id,
        )
    except KnowledgeBaseNotFoundError:
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
    def _resolve_stores(store_ids: list[int]):
        return resolve_member_stores(
            membership, store_ids, db,
        )

    try:
        knowledge_base = svc_create_knowledge_base(
            db,
            organization_id=membership.organization_id,
            name=payload.name,
            scope=payload.scope,
            active=payload.active,
            store_ids=payload.store_ids,
            is_owner=membership.role == "owner",
            all_stores=membership.all_stores,
            resolve_stores_fn=_resolve_stores,
        )
    except InvalidKnowledgeBaseScopeError as exc:
        status = 400
        if "require all-store access" in str(exc):
            status = 403
        raise HTTPException(
            status_code=status,
            detail=str(exc),
        ) from exc
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc
    except InvalidStoreSelectionError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

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
    try:
        knowledge_base = svc_get_knowledge_base(
            db,
            membership.organization_id,
            knowledge_base_id,
        )
    except KnowledgeBaseNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    def _resolve_stores(store_ids: list[int]):
        return resolve_member_stores(
            membership, store_ids, db,
        )

    try:
        knowledge_base = svc_update_knowledge_base(
            db,
            knowledge_base,
            name=payload.name,
            scope=payload.scope,
            active=payload.active,
            store_ids=payload.store_ids,
            is_owner=membership.role == "owner",
            all_stores=membership.all_stores,
            resolve_stores_fn=_resolve_stores,
        )
    except InvalidKnowledgeBaseScopeError as exc:
        status = 400
        if "require all-store access" in str(exc):
            status = 403
        raise HTTPException(
            status_code=status,
            detail=str(exc),
        ) from exc
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(
            status_code=403,
            detail=str(exc),
        ) from exc
    except InvalidStoreSelectionError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return serialize_knowledge_base(knowledge_base)


@router.delete("/api/knowledge-bases/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: int,
    membership: OrganizationMembership = Depends(
        require_permission("knowledge.write")
    ),
    db: Session = Depends(get_db),
):
    try:
        knowledge_base = svc_get_knowledge_base(
            db,
            membership.organization_id,
            knowledge_base_id,
        )
    except KnowledgeBaseNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )
    try:
        svc_delete_knowledge_base(db, knowledge_base)
    except BedrockProvisioningError as error:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "KNOWLEDGE_BASE_DELETION_FAILED",
                "message": "Knowledge Base deletion could not be completed.",
            },
        ) from error
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
    try:
        knowledge_base = svc_get_knowledge_base(
            db,
            membership.organization_id,
            knowledge_base_id,
        )
    except KnowledgeBaseNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Knowledge base not found",
        )

    try:
        knowledge_base = svc_retry_knowledge_base_provisioning(
            db, knowledge_base,
        )
    except InvalidKnowledgeBaseScopeError as exc:
        msg = str(exc)
        if "already in progress" in msg:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "PROVISIONING_IN_PROGRESS",
                    "message": msg,
                },
            ) from exc
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_PROVISIONING_STATE",
                "message": msg,
            },
        ) from exc
    except KnowledgeBaseAccessError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PROVISIONING_STATE_CHANGED",
                "message": str(exc),
            },
        ) from exc

    background_tasks.add_task(run_knowledge_base_provisioning, knowledge_base.id)

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
    try:
        knowledge_base, sources, google_connection = svc_list_knowledge_sources(
            db,
            organization_id=membership.organization_id,
            knowledge_base_id=knowledge_base_id,
        )
    except SourceLifecycleNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

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
        source = svc_upload_source_file(
            db,
            organization_id=membership.organization_id,
            knowledge_base=knowledge_base,
            filename=filename,
            content=content,
            content_type=file.content_type,
        )
    except SourceDeletionError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

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

    sources_to_delete = svc_collect_sources_to_delete(
        db,
        organization_id=membership.organization_id,
        knowledge_base_id=knowledge_base_id,
        source=source,
    )

    try:
        svc_delete_source_artifacts(sources_to_delete)
    except SourceDeletionError as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    svc_deactivate_sources(db, sources_to_delete)

    ingestion_job_id, reindex_status = svc_trigger_source_reindex(kb)

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
        return await add_google_sheet(
            db=db,
            org_id=org_id,
            kb=kb,
            sheet_id=sheet_id,
            import_mode=payload.import_mode,
            sheet_name=source_sheet_name,
            spreadsheet_title=spreadsheet_title,
            access_token=access_token,
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
    if svc_is_source_sync_in_progress(source):
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

    try:
        return await sync_google_sheet(
            db=db,
            org_id=org_id,
            kb=kb,
            source=source,
            access_token=access_token,
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
    try:
        return svc_refresh_source_ingestion_status(
            db,
            organization_id=membership.organization_id,
            knowledge_base_id=knowledge_base_id,
            source_id=source_id,
        )
    except IngestionSourceNotFoundError as exc:
        detail = str(exc)
        if "Knowledge Base" in detail:
            detail = "Knowledge Base not found"
        else:
            detail = "Source not found"
        raise HTTPException(
            status_code=404,
            detail=detail,
        ) from exc


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

    try:
        result = await add_google_doc(
            db, org_id, kb, access_token,
            request.file_id, request.file_name,
        )
    except _EmptyContentError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except DriveSourceConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DRIVE_SOURCE_CONFLICT",
                "message": str(exc),
            },
        ) from exc
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

    return result


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

    try:
        result = await add_drive_file(
            db, org_id, kb, access_token,
            request.file_id, request.file_name, request.mime_type,
        )
    except _EmptyContentError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except DriveSourceConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DRIVE_SOURCE_CONFLICT",
                "message": str(exc),
            },
        ) from exc
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

    return result


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
        result = await add_google_drive_folder(
            db, org_id, kb, access_token, request.folder_id, request.folder_name,
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
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "FOLDER_FINALIZATION_FAILED",
                "message": str(exc),
            },
        ) from exc

    if result.get("duplicate"):
        return {
            "source_id": result["source_id"],
            "name": result["name"],
            "sync_status": result["sync_status"],
            "message": result["message"],
        }

    return result


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
    if svc_is_source_sync_in_progress(source):
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

    try:
        result = await sync_google_drive_folder(
            db, org_id, kb, source, access_token,
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
            detail={
                "code": "SYNC_LIMIT_EXCEEDED",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "GOOGLE_FOLDER_LIST_FAILED",
                "message": str(exc),
            },
        ) from exc

    return result


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
    if svc_is_source_sync_in_progress(source):
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

    try:
        result = await sync_drive_file(
            db, org_id, kb, source, access_token,
        )
    except _EmptyContentError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
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
        error = str(exc)
        if "DB persistence failed" in error:
            _mark_drive_source_failed(db, source, error)
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "SOURCE_PERSISTENCE_FAILED",
                    "message": error,
                },
            ) from exc
        if "Ingestion state persistence failed" in error:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "INGESTION_STATE_FAILED",
                    "message": error,
                },
            ) from exc
        _mark_drive_source_failed(db, source, error)
        raise HTTPException(
            status_code=500,
            detail=error,
        ) from exc

    return result


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
