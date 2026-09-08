"""Knowledge Source CRUD lifecycle service.

Source listing, file upload, source deletion, and cleanup orchestration.
"""

import logging

from sqlalchemy.orm import Session

from ..knowledge_storage import delete_knowledge_file, upload_knowledge_file
from ..models import GoogleConnection, KnowledgeBase, KnowledgeSource

logger = logging.getLogger(__name__)


# ============================================================
# DOMAIN EXCEPTIONS
# ============================================================


class SourceNotFoundError(Exception):
    """Source not found within the given KB and organization."""


class KnowledgeBaseNotReadyError(Exception):
    """Knowledge Base provisioning is not ready for source operations."""


class SourceDeletionError(Exception):
    """S3 artifact deletion failed."""


# ============================================================
# SOURCE LISTING
# ============================================================


def list_knowledge_sources(
    db: Session,
    *,
    organization_id: int,
    knowledge_base_id: int,
) -> tuple[KnowledgeBase, list[KnowledgeSource], GoogleConnection | None]:
    """List active sources for a knowledge base.

    Returns (knowledge_base, sources, google_connection).
    Raises SourceNotFoundError if KB not found.
    """
    knowledge_base = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.organization_id == organization_id,
        )
        .first()
    )
    if not knowledge_base:
        raise SourceNotFoundError("Knowledge base not found")

    sources = (
        db.query(KnowledgeSource)
        .filter(
            KnowledgeSource.organization_id == organization_id,
            KnowledgeSource.knowledge_base_id == knowledge_base_id,
            KnowledgeSource.active.is_(True),
        )
        .order_by(KnowledgeSource.created_at.desc())
        .all()
    )

    google_connection = (
        db.query(GoogleConnection)
        .filter(
            GoogleConnection.organization_id == organization_id,
        )
        .first()
    )

    return knowledge_base, sources, google_connection


# ============================================================
# FILE UPLOAD
# ============================================================


def upload_source_file(
    db: Session,
    *,
    organization_id: int,
    knowledge_base: KnowledgeBase,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> KnowledgeSource:
    """Upload a file source to S3 and create the KnowledgeSource record.

    Raises SourceDeletionError on S3 failure.
    """
    try:
        uploaded = upload_knowledge_file(
            organization_id=organization_id,
            knowledge_base_id=knowledge_base.id,
            filename=filename,
            content=content,
            content_type=content_type,
        )
    except Exception as exc:
        raise SourceDeletionError(
            "Unable to upload knowledge document",
        ) from exc

    source = KnowledgeSource(
        organization_id=organization_id,
        knowledge_base_id=knowledge_base.id,
        name=filename,
        source_type="file",
        content_type=content_type,
        s3_bucket=uploaded["bucket"],
        s3_key=uploaded["key"],
        size_bytes=len(content),
        status="uploaded",
        active=True,
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return source


# ============================================================
# SOURCE DELETION
# ============================================================


def collect_sources_to_delete(
    db: Session,
    *,
    organization_id: int,
    knowledge_base_id: int,
    source: KnowledgeSource,
) -> list[KnowledgeSource]:
    """Collect source and its folder children for deletion.

    A folder is metadata only; its children own the S3 artifacts.
    """
    sources_to_delete = [source]
    if source.source_type == "google_drive_folder":
        sources_to_delete.extend(
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.parent_source_id == source.id,
                KnowledgeSource.organization_id == organization_id,
                KnowledgeSource.knowledge_base_id == knowledge_base_id,
                KnowledgeSource.active.is_(True),
            )
            .all()
        )
    return sources_to_delete


def delete_source_artifacts(
    sources_to_delete: list[KnowledgeSource],
) -> None:
    """Delete S3 artifacts for the given sources.

    Raises SourceDeletionError on failure.
    """
    try:
        for item in sources_to_delete:
            if item.s3_bucket and item.s3_key:
                delete_knowledge_file(
                    item.s3_bucket, item.s3_key,
                )
    except Exception as exc:
        raise SourceDeletionError(
            "Unable to delete knowledge document",
        ) from exc


def deactivate_sources(
    db: Session,
    sources_to_delete: list[KnowledgeSource],
) -> None:
    """Mark sources as inactive and deleted, then flush."""
    for item in sources_to_delete:
        item.active = False
        item.status = "deleted"
    db.flush()
