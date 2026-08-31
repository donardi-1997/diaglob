"""
Bedrock Knowledge Base ingestion helpers.

Handles:
- Starting ingestion jobs
- Checking ingestion job status
- Mapping Bedrock statuses to internal statuses
"""

import logging
import os

import boto3

logger = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION", "us-east-2")

# Internal status mapping
STATUS_INDEXING = "indexing"
STATUS_SYNCED = "synced"
STATUS_FAILED = "failed"

# Bedrock ingestion job statuses
BEDROCK_COMPLETE = "COMPLETE"
BEDROCK_FAILED = "FAILED"
BEDROCK_IN_PROGRESS = "IN_PROGRESS"
BEDROCK_STARTING = "STARTING"


def _get_bedrock_agent_client():
    """Create a bedrock-agent (non-runtime) client."""
    return boto3.client(
        "bedrock-agent",
        region_name=AWS_REGION,
    )


def start_ingestion_job(
    knowledge_base_id: str,
    data_source_id: str,
) -> str | None:
    """Start a Bedrock ingestion job for a data source.

    Args:
        knowledge_base_id: The Bedrock KB ID
            (KnowledgeBase.external_id)
        data_source_id: The Bedrock data source ID
            (KnowledgeBase.external_data_source_id)

    Returns:
        The ingestion job ID, or None on failure.
    """
    if not knowledge_base_id or not data_source_id:
        logger.warning(
            "Cannot start ingestion: missing "
            "knowledge_base_id=%s or data_source_id=%s",
            knowledge_base_id,
            data_source_id,
        )
        return None

    try:
        client = _get_bedrock_agent_client()
        response = client.start_ingestion_job(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=data_source_id,
        )
        job = response.get("ingestionJob", {})
        job_id = job.get("ingestionJobId")
        status = job.get("status", "UNKNOWN")

        logger.info(
            "Started ingestion job %s for KB %s, "
            "status: %s",
            job_id,
            knowledge_base_id,
            status,
        )
        return job_id

    except Exception as exc:
        logger.error(
            "Failed to start ingestion job for "
            "KB %s: %s",
            knowledge_base_id,
            exc,
        )
        return None


def get_ingestion_status(
    knowledge_base_id: str,
    data_source_id: str,
    ingestion_job_id: str,
) -> str:
    """Check the status of a Bedrock ingestion job.

    Returns:
        Internal status string: "indexing", "synced",
        or "failed".
    """
    if (
        not knowledge_base_id
        or not data_source_id
        or not ingestion_job_id
    ):
        return STATUS_FAILED

    try:
        client = _get_bedrock_agent_client()
        response = client.get_ingestion_job(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=data_source_id,
            ingestionJobId=ingestion_job_id,
        )
        job = response.get("ingestionJob", {})
        bedrock_status = job.get("status", "UNKNOWN")

        if bedrock_status == BEDROCK_COMPLETE:
            return STATUS_SYNCED
        elif bedrock_status == BEDROCK_FAILED:
            stats = job.get("statistics", {})
            logger.warning(
                "Ingestion job %s failed. Stats: %s",
                ingestion_job_id,
                stats,
            )
            return STATUS_FAILED
        else:
            # STARTING, IN_PROGRESS, etc.
            return STATUS_INDEXING

    except Exception as exc:
        logger.error(
            "Failed to get ingestion status for "
            "job %s: %s",
            ingestion_job_id,
            exc,
        )
        return STATUS_FAILED


def map_google_api_error(
    status_code: int,
) -> tuple[str, str]:
    """Map Google API HTTP status to internal error.

    Returns:
        (error_code, user_message) tuple.
    """
    if status_code == 401:
        return (
            "reconnect_required",
            "Google connection expired. "
            "Please reconnect Google.",
        )
    elif status_code == 403:
        return (
            "permission_denied",
            "Access denied. Check Google account "
            "permissions.",
        )
    elif status_code == 404:
        return (
            "not_found",
            "Spreadsheet or tab not found.",
        )
    elif status_code == 429:
        return (
            "rate_limited",
            "Google API rate limited. "
            "Try again later.",
        )
    elif status_code >= 500:
        return (
            "provider_error",
            "Google service temporarily unavailable.",
        )
    else:
        return (
            "unknown_error",
            f"Google API error ({status_code}).",
        )
