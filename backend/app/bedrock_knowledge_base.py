"""Provision isolated Bedrock Knowledge Bases and S3 Vectors indexes."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from .bedrock_ingestion import AWS_REGION, _get_bedrock_agent_client
from .models import KnowledgeBase, KnowledgeSource
from .knowledge_storage import delete_knowledge_prefix
from .knowledge_provisioning.errors import (
    BedrockProvisioningError,
    ProvisioningErrorClassification,
    ProvisioningInProgressError,
    _aws_provisioning_error,
    _client_error_code,
    _client_error_message,
    _client_error_request_id,
    _is_uncertain_create_error,
    classify_provisioning_aws_error,
)
from .knowledge_provisioning.s3_vectors import (
    S3VectorsAdapter,
    S3VectorsConfig,
)
from .knowledge_provisioning.bedrock_resources import (
    BedrockResourcesAdapter,
    BedrockResourcesConfig,
)
from .knowledge_provisioning.lifecycle import (
    _as_utc,
    _claim_provisioning,
    _commit_state,
    _set_provisioning_stage,
)

logger = logging.getLogger(__name__)










_CANONICAL_ENVIRONMENTS = {
    "production": "production",
    "prod": "production",
    "staging": "staging",
    "stage": "staging",
    "development": "development",
    "dev": "development",
    "local": "development",
    "test": "test",
    "testing": "test",
}


def normalize_environment(value: str | None) -> str:
    """Map a DIAGLOB_ENVIRONMENT value to a canonical form.

    Canonical values: production, staging, development, test.

    Raises BedrockProvisioningError on None, empty, or unknown values
    so that misconfigurations fail fast rather than silently creating
    non-deterministic IAM tags.
    """
    if not value or not value.strip():
        raise BedrockProvisioningError(
            "invalid_environment",
            resource="configuration",
        )
    key = value.strip().lower()
    canonical = _CANONICAL_ENVIRONMENTS.get(key)
    if canonical is None:
        raise BedrockProvisioningError(
            "invalid_environment",
            resource="configuration",
        )
    return canonical


_RAW_ENVIRONMENT = os.getenv("DIAGLOB_ENVIRONMENT")


def _resolve_environment(raw: str | None) -> str:
    """Resolve and canonicalize the environment at provisioning time.

    Called lazily (not at import time) so that tests can monkeypatch
    ENVIRONMENT before provisioning functions execute.
    """
    return normalize_environment(raw)


ENVIRONMENT: str = (
    _resolve_environment(_RAW_ENVIRONMENT) if _RAW_ENVIRONMENT else ""
)
VECTOR_BUCKET_ARN = os.getenv("DIAGLOB_VECTOR_BUCKET_ARN", "").strip()
BEDROCK_SERVICE_ROLE_ARN = os.getenv("BEDROCK_SERVICE_ROLE_ARN", "").strip()
EMBEDDING_MODEL_ARN = os.getenv(
    "BEDROCK_EMBEDDING_MODEL_ARN",
    f"arn:aws:bedrock:{AWS_REGION}::foundation-model/amazon.titan-embed-text-v2:0",
).strip()
KNOWLEDGE_BUCKET = os.getenv("DIAGLOB_KNOWLEDGE_BUCKET", "").strip()

VECTOR_DIMENSION = 1024
VECTOR_DATA_TYPE = "float32"
VECTOR_EMBEDDING_DATA_TYPE = "FLOAT32"
VECTOR_DISTANCE_METRIC = "cosine"
VECTOR_NON_FILTERABLE_METADATA_KEYS = (
    "AMAZON_BEDROCK_TEXT",
    "AMAZON_BEDROCK_METADATA",
)


LEGACY_KNOWLEDGE_INFRASTRUCTURE = {
    "bedrock_kb_id": "RDAQY1JNQ8",
    "bedrock_kb_name": "diaglob-knowledge-main",
    "vector_index_name": "diaglob-knowledge-v1",
}

PROVISIONING_STATES = ("pending", "provisioning", "retrying", "ready", "failed", "deleting")
PROVISIONING_STAGES = (
    "queued", "creating_vector_index", "creating_knowledge_base",
    "creating_data_source", "finalizing", "retrying", "ready", "failed", "deleting",
)
RECOVERY_ATTEMPTS = int(os.getenv("BEDROCK_RECOVERY_ATTEMPTS", "3"))
WAIT_ATTEMPTS = int(os.getenv("BEDROCK_WAIT_ATTEMPTS", "30"))
POLL_INTERVAL_SECONDS = float(os.getenv("BEDROCK_POLL_INTERVAL_SECONDS", "2"))


@dataclass
class CleanupResult:
    succeeded: bool
    bedrock_kb_id: str | None
    bedrock_ds_id: str | None
    error: Exception | None = None


def _get_s3_vectors_client():
    return boto3.client("s3vectors", region_name=AWS_REGION)


def _environment_slug(environment: str) -> str:
    slug_aliases = {
        "production": "prod",
        "development": "dev",
    }
    value = slug_aliases.get(
        environment.strip().lower(), environment.strip().lower()
    )
    value = re.sub(r"[^a-z0-9-]+", "-", value).strip("-")
    if not value:
        raise BedrockProvisioningError(
            "invalid_environment", resource="configuration"
        )
    return value


def build_vector_index_name(environment: str, kb_id: int) -> str:
    """Build a deterministic, non-PII S3 Vectors index name."""
    name = f"diaglob-{_environment_slug(environment)}-kb-{kb_id}"
    if len(name) > 63 or not re.fullmatch(r"[a-z0-9][a-z0-9.-]+[a-z0-9]", name):
        raise BedrockProvisioningError("invalid_vector_index_name", resource="vector_index")
    return name


def _make_kb_name(org_id: int, kb_id: int) -> str:
    return f"diaglob-{_environment_slug(ENVIRONMENT)}-org-{org_id}-kb-{kb_id}"


def _make_ds_name(kb_id: int) -> str:
    return f"diaglob-{_environment_slug(ENVIRONMENT)}-kb-{kb_id}-s3"


def _make_client_token(prefix: str, org_id: int, kb_id: int) -> str:
    source = f"diaglob:{ENVIRONMENT}:{prefix}:{org_id}:{kb_id}"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"diaglob-{prefix}-{digest}"


def _make_tags(org_id: int, kb_id: int) -> dict[str, str]:
    return {
        "diaglob:managed-by": "diaglob-backend",
        "diaglob:environment": ENVIRONMENT,
        "diaglob:organization_id": str(org_id),
        "diaglob:knowledge_base_id": str(kb_id),
    }


def _get_s3_prefix(org_id: int, kb_id: int) -> str:
    return f"organizations/{org_id}/knowledge-bases/{kb_id}/documents/"


def _vector_index_arn(kb_id: int) -> str:
    if not VECTOR_BUCKET_ARN:
        raise BedrockProvisioningError(
            "vector_bucket_not_configured", resource="configuration"
        )
    return f"{VECTOR_BUCKET_ARN}/index/{build_vector_index_name(ENVIRONMENT, kb_id)}"


def _validate_configuration() -> None:
    missing = []
    if not ENVIRONMENT:
        missing.append("DIAGLOB_ENVIRONMENT")
    if not VECTOR_BUCKET_ARN:
        missing.append("DIAGLOB_VECTOR_BUCKET_ARN")
    if not BEDROCK_SERVICE_ROLE_ARN:
        missing.append("BEDROCK_SERVICE_ROLE_ARN")
    if not KNOWLEDGE_BUCKET:
        missing.append("DIAGLOB_KNOWLEDGE_BUCKET")
    if missing:
        logger.error("Missing Bedrock provisioning configuration: %s", ", ".join(missing))
        raise BedrockProvisioningError(
            "provisioning_configuration_missing", resource="configuration"
        )












def _log_provisioning_aws_error(
    *,
    operation: str,
    aws_service: str,
    stage: str,
    org_id: int,
    kb_id: int,
    error: Exception,
    vector_index_arn: str | None = None,
    bedrock_kb_id: str | None = None,
    bedrock_data_source_id: str | None = None,
) -> None:
    logger.error(
        "knowledge_base_aws_operation_failed operation=%s aws_service=%s "
        "organization_id=%s knowledge_base_id=%s provisioning_stage=%s "
        "aws_error_code=%s aws_error_message=%s aws_request_id=%s "
        "vector_bucket_arn=%s vector_index_arn=%s bedrock_kb_id=%s "
        "bedrock_data_source_id=%s bedrock_role_arn=%s embedding_model_arn=%s "
        "knowledge_bucket=%s",
        operation,
        aws_service,
        org_id,
        kb_id,
        stage,
        _client_error_code(error),
        _client_error_message(error),
        _client_error_request_id(error),
        VECTOR_BUCKET_ARN,
        vector_index_arn,
        bedrock_kb_id,
        bedrock_data_source_id,
        BEDROCK_SERVICE_ROLE_ARN,
        EMBEDDING_MODEL_ARN,
        KNOWLEDGE_BUCKET,
        exc_info=(type(error), error, error.__traceback__),
    )




def _sleep_between_attempts(attempt: int, attempts: int) -> None:
    if attempt + 1 < attempts and POLL_INTERVAL_SECONDS > 0:
        time.sleep(POLL_INTERVAL_SECONDS)


def _tags_match(actual: dict[str, str], expected: dict[str, str]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def is_verified_legacy_parent(bedrock_kb_id: str) -> bool:
    """Check if a Bedrock KB ID belongs to the known legacy infrastructure."""
    return bedrock_kb_id == LEGACY_KNOWLEDGE_INFRASTRUCTURE["bedrock_kb_id"]


def _legacy_vector_index_arn() -> str:
    """Build the ARN for the legacy shared vector index."""
    if not VECTOR_BUCKET_ARN:
        raise BedrockProvisioningError(
            "vector_bucket_not_configured", resource="configuration"
        )
    return f"{VECTOR_BUCKET_ARN}/index/{LEGACY_KNOWLEDGE_INFRASTRUCTURE['vector_index_name']}"


def validate_legacy_data_source_ownership(
    remote_ds: dict[str, Any],
    remote_kb: dict[str, Any],
    org_id: int,
    kb_id: int,
) -> None:
    """Verify a legacy Data Source is safe to delete.

    Raises BedrockProvisioningError if any invariant fails.
    """
    if remote_kb.get("knowledgeBaseId") != LEGACY_KNOWLEDGE_INFRASTRUCTURE["bedrock_kb_id"]:
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="data_source"
        )

    if remote_ds.get("knowledgeBaseId") != LEGACY_KNOWLEDGE_INFRASTRUCTURE["bedrock_kb_id"]:
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="data_source"
        )

    ds_config = remote_ds.get("dataSourceConfiguration", {})
    if ds_config.get("type") != "S3":
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="data_source"
        )

    s3_config = ds_config.get("s3Configuration", {})
    expected_bucket_arn = f"arn:aws:s3:::{KNOWLEDGE_BUCKET}"
    if s3_config.get("bucketArn") != expected_bucket_arn:
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="data_source"
        )

    expected_prefix = _get_s3_prefix(org_id, kb_id)
    prefixes = s3_config.get("inclusionPrefixes", [])
    if prefixes != [expected_prefix]:
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="data_source"
        )


def cleanup_verified_legacy_resources(
    db: Session,
    knowledge_base: KnowledgeBase,
) -> None:
    """Delete only the verified legacy Data Source and local resources.

    Preserves the legacy parent Bedrock KB and shared vector index.
    """
    org_id = knowledge_base.organization_id
    kb_id = knowledge_base.id
    bedrock_kb_id = knowledge_base.external_id
    bedrock_ds_id = knowledge_base.external_data_source_id

    logger.info(
        "knowledge_base_deletion_mode=legacy organization_id=%s knowledge_base_id=%s "
        "bedrock_kb_id=%s bedrock_ds_id=%s legacy_parent_name=%s",
        org_id, kb_id, bedrock_kb_id, bedrock_ds_id,
        LEGACY_KNOWLEDGE_INFRASTRUCTURE["bedrock_kb_name"],
    )

    remote_kb = get_bedrock_knowledge_base(bedrock_kb_id)
    if not remote_kb:
        logger.warning(
            "legacy_parent_absent organization_id=%s knowledge_base_id=%s bedrock_kb_id=%s",
            org_id, kb_id, bedrock_kb_id,
        )
    else:
        logger.info("legacy_parent_verified organization_id=%s knowledge_base_id=%s", org_id, kb_id)

    if bedrock_ds_id and remote_kb:
        remote_ds = get_bedrock_data_source(bedrock_kb_id, bedrock_ds_id)
        if remote_ds:
            validate_legacy_data_source_ownership(
                remote_ds, remote_kb, org_id, kb_id
            )
            logger.info(
                "legacy_data_source_verified organization_id=%s knowledge_base_id=%s bedrock_ds_id=%s",
                org_id, kb_id, bedrock_ds_id,
            )
            try:
                _get_bedrock_agent_client().delete_data_source(
                    knowledgeBaseId=bedrock_kb_id,
                    dataSourceId=bedrock_ds_id,
                )
            except (BotoCoreError, ClientError) as error:
                if _client_error_code(error) != "ResourceNotFoundException":
                    _log_provisioning_aws_error(
                        operation="DeleteDataSource",
                        aws_service="bedrock-agent",
                        stage="legacy_deleting",
                        org_id=org_id,
                        kb_id=kb_id,
                        error=error,
                        bedrock_kb_id=bedrock_kb_id,
                        bedrock_data_source_id=bedrock_ds_id,
                    )
                    raise _aws_provisioning_error(
                        "bedrock_data_source_delete_failed",
                        "data_source",
                        error,
                        aws_service="bedrock-agent",
                        aws_operation="DeleteDataSource",
                    ) from error

            for attempt in range(WAIT_ATTEMPTS):
                remote_ds = get_bedrock_data_source(bedrock_kb_id, bedrock_ds_id)
                if remote_ds is None:
                    break
                if remote_ds.get("status") == "DELETE_UNSUCCESSFUL":
                    raise BedrockProvisioningError(
                        "bedrock_data_source_delete_unconfirmed", resource="data_source"
                    )
                _sleep_between_attempts(attempt, WAIT_ATTEMPTS)
            else:
                raise BedrockProvisioningError(
                    "bedrock_data_source_delete_unconfirmed", resource="data_source"
                )
            logger.info("legacy_data_source_deleted organization_id=%s knowledge_base_id=%s", org_id, kb_id)
        else:
            logger.info(
                "legacy_data_source_already_absent organization_id=%s knowledge_base_id=%s bedrock_ds_id=%s",
                org_id, kb_id, bedrock_ds_id,
            )

    logger.info("legacy_parent_preserved organization_id=%s knowledge_base_id=%s", org_id, kb_id)
    logger.info("legacy_vector_index_preserved organization_id=%s knowledge_base_id=%s", org_id, kb_id)

    delete_knowledge_prefix(org_id, kb_id)
    logger.info("s3_prefix_deleted organization_id=%s knowledge_base_id=%s", org_id, kb_id)

    db.query(KnowledgeSource).filter(
        KnowledgeSource.organization_id == org_id,
        KnowledgeSource.knowledge_base_id == kb_id,
    ).delete(synchronize_session=False)
    db.delete(knowledge_base)
    _commit_state(db, "deletion_state_persist_failed")
    logger.info("database_deleted organization_id=%s knowledge_base_id=%s", org_id, kb_id)


def _s3_vectors_adapter() -> S3VectorsAdapter:
    """Build the S3 Vectors adapter from the current facade configuration.

    Construction is intentionally lazy so existing tests and operational code that
    patch the legacy module's configuration/client factory keep working unchanged.
    """
    return S3VectorsAdapter(
        config=S3VectorsConfig(
            vector_bucket_arn=VECTOR_BUCKET_ARN,
            environment=ENVIRONMENT,
            vector_dimension=VECTOR_DIMENSION,
            vector_data_type=VECTOR_DATA_TYPE,
            vector_distance_metric=VECTOR_DISTANCE_METRIC,
            non_filterable_metadata_keys=VECTOR_NON_FILTERABLE_METADATA_KEYS,
            recovery_attempts=RECOVERY_ATTEMPTS,
            wait_attempts=WAIT_ATTEMPTS,
        ),
        client_factory=_get_s3_vectors_client,
        vector_index_arn=_vector_index_arn,
        build_vector_index_name=build_vector_index_name,
        make_tags=_make_tags,
        tags_match=_tags_match,
        sleep_between_attempts=_sleep_between_attempts,
        validate_configuration=_validate_configuration,
        log_aws_error=_log_provisioning_aws_error,
    )


def get_s3_vectors_index(index_arn: str) -> dict[str, Any] | None:
    return _s3_vectors_adapter().get_index(index_arn)


def _get_s3_vectors_tags(index_arn: str) -> dict[str, str]:
    return _s3_vectors_adapter().get_tags(index_arn)


def _validate_s3_vectors_index(
    index: dict[str, Any],
    tags: dict[str, str],
    org_id: int,
    kb_id: int,
) -> None:
    _s3_vectors_adapter().validate_index(index, tags, org_id, kb_id)


def _recover_s3_vectors_index(org_id: int, kb_id: int) -> dict[str, Any] | None:
    return _s3_vectors_adapter().recover_index(org_id, kb_id)


def create_s3_vectors_index(org_id: int, kb_id: int) -> dict[str, Any]:
    return _s3_vectors_adapter().create_index(org_id, kb_id)


def delete_s3_vectors_index(index_arn: str, org_id: int, kb_id: int) -> None:
    _s3_vectors_adapter().delete_index(index_arn, org_id, kb_id)














def _bedrock_resources_adapter() -> BedrockResourcesAdapter:
    """Build the modern Bedrock adapter from current facade configuration."""
    return BedrockResourcesAdapter(
        config=BedrockResourcesConfig(
            vector_bucket_arn=VECTOR_BUCKET_ARN,
            bedrock_service_role_arn=BEDROCK_SERVICE_ROLE_ARN,
            embedding_model_arn=EMBEDDING_MODEL_ARN,
            knowledge_bucket=KNOWLEDGE_BUCKET,
            vector_dimension=VECTOR_DIMENSION,
            vector_embedding_data_type=VECTOR_EMBEDDING_DATA_TYPE,
            recovery_attempts=RECOVERY_ATTEMPTS,
            wait_attempts=WAIT_ATTEMPTS,
        ),
        client_factory=_get_bedrock_agent_client,
        make_kb_name=_make_kb_name,
        make_ds_name=_make_ds_name,
        make_client_token=_make_client_token,
        make_tags=_make_tags,
        tags_match=_tags_match,
        get_s3_prefix=_get_s3_prefix,
        vector_index_arn=_vector_index_arn,
        validate_configuration=_validate_configuration,
        sleep_between_attempts=_sleep_between_attempts,
        log_aws_error=_log_provisioning_aws_error,
    )


def get_bedrock_knowledge_base(bedrock_kb_id: str) -> dict[str, Any] | None:
    return _bedrock_resources_adapter().get_knowledge_base(bedrock_kb_id)


def _get_bedrock_tags(resource_arn: str) -> dict[str, str]:
    return _bedrock_resources_adapter().get_tags(resource_arn)


def _validate_bedrock_knowledge_base(
    remote: dict[str, Any], org_id: int, kb_id: int, index_arn: str
) -> None:
    _bedrock_resources_adapter().validate_knowledge_base(
        remote, org_id, kb_id, index_arn
    )


def _list_knowledge_bases_by_name(name: str) -> list[dict[str, Any]]:
    return _bedrock_resources_adapter()._list_knowledge_bases_by_name(name)


def discover_bedrock_knowledge_base(
    org_id: int, kb_id: int, index_arn: str
) -> dict[str, Any] | None:
    return _bedrock_resources_adapter().discover_knowledge_base(
        org_id, kb_id, index_arn
    )


def create_bedrock_knowledge_base(
    org_id: int,
    kb_id: int,
    index_arn: str,
    description: str | None = None,
) -> dict[str, Any]:
    return _bedrock_resources_adapter().create_knowledge_base(
        org_id, kb_id, index_arn, description
    )


def wait_for_bedrock_knowledge_base(
    bedrock_kb_id: str, org_id: int, kb_id: int, index_arn: str
) -> dict[str, Any]:
    return _bedrock_resources_adapter().wait_for_knowledge_base(
        bedrock_kb_id, org_id, kb_id, index_arn
    )


def get_bedrock_data_source(
    bedrock_kb_id: str, data_source_id: str
) -> dict[str, Any] | None:
    return _bedrock_resources_adapter().get_data_source(
        bedrock_kb_id, data_source_id
    )


def _validate_bedrock_data_source(
    remote: dict[str, Any], bedrock_kb_id: str, org_id: int, kb_id: int
) -> None:
    _bedrock_resources_adapter().validate_data_source(
        remote, bedrock_kb_id, org_id, kb_id
    )


def discover_bedrock_data_source(
    bedrock_kb_id: str, org_id: int, kb_id: int
) -> dict[str, Any] | None:
    return _bedrock_resources_adapter().discover_data_source(
        bedrock_kb_id, org_id, kb_id
    )


def create_bedrock_data_source(
    bedrock_kb_id: str, org_id: int, kb_id: int
) -> dict[str, Any]:
    return _bedrock_resources_adapter().create_data_source(
        bedrock_kb_id, org_id, kb_id
    )


def wait_for_bedrock_data_source(
    bedrock_kb_id: str, data_source_id: str, org_id: int, kb_id: int
) -> dict[str, Any]:
    return _bedrock_resources_adapter().wait_for_data_source(
        bedrock_kb_id, data_source_id, org_id, kb_id
    )


def delete_bedrock_data_source(
    bedrock_kb_id: str,
    data_source_id: str,
    org_id: int,
    kb_id: int,
    index_arn: str,
) -> None:
    _bedrock_resources_adapter().delete_data_source(
        bedrock_kb_id, data_source_id, org_id, kb_id, index_arn
    )


def delete_bedrock_knowledge_base(
    bedrock_kb_id: str, org_id: int, kb_id: int, index_arn: str
) -> None:
    _bedrock_resources_adapter().delete_knowledge_base(
        bedrock_kb_id, org_id, kb_id, index_arn
    )






































def _cleanup_remote_resources(
    org_id: int,
    kb_id: int,
    index_arn: str | None,
    bedrock_kb_id: str | None,
    bedrock_ds_id: str | None,
) -> CleanupResult:
    remaining_kb_id = bedrock_kb_id
    remaining_ds_id = bedrock_ds_id

    if remaining_ds_id and remaining_kb_id:
        try:
            delete_bedrock_data_source(
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
            delete_bedrock_knowledge_base(
                remaining_kb_id, org_id, kb_id, index_arn
            )
            remaining_kb_id = None
            remaining_ds_id = None
        except Exception as error:
            logger.exception("Unable to confirm Bedrock Knowledge Base cleanup")
            return CleanupResult(False, remaining_kb_id, remaining_ds_id, error)

    if index_arn:
        try:
            delete_s3_vectors_index(index_arn, org_id, kb_id)
        except Exception as error:
            logger.exception("Unable to confirm S3 Vectors index cleanup")
            return CleanupResult(False, remaining_kb_id, remaining_ds_id, error)

    return CleanupResult(True, remaining_kb_id, remaining_ds_id)


def provision_diaglob_knowledge_base(
    db: Session, knowledge_base: KnowledgeBase
) -> tuple[str, str]:
    """Provision one isolated index, Bedrock KB, and Data Source."""
    if knowledge_base.external_status == "ready":
        if knowledge_base.external_id and knowledge_base.external_data_source_id:
            return knowledge_base.external_id, knowledge_base.external_data_source_id
        raise BedrockProvisioningError(
            "ready_resource_ids_missing", resource="knowledge_base"
        )

    _claim_provisioning(db, knowledge_base)
    org_id = knowledge_base.organization_id
    kb_id = knowledge_base.id
    logger.info(
        "knowledge_base_provisioning_started organization_id=%s knowledge_base_id=%s stage=%s",
        org_id,
        kb_id,
        knowledge_base.provisioning_stage,
    )
    index_arn: str | None = None
    bedrock_kb_id = knowledge_base.external_id
    bedrock_ds_id = knowledge_base.external_data_source_id
    failure: BedrockProvisioningError | None = None

    try:
        vector_index = create_s3_vectors_index(org_id, kb_id)
        index_arn = vector_index["indexArn"]

        _set_provisioning_stage(db, knowledge_base, "creating_knowledge_base")
        if bedrock_kb_id:
            remote_kb = get_bedrock_knowledge_base(bedrock_kb_id)
            if remote_kb is None:
                bedrock_kb_id = None
                bedrock_ds_id = None
                knowledge_base.external_id = None
                knowledge_base.external_data_source_id = None
                _commit_state(db)
            else:
                wait_for_bedrock_knowledge_base(
                    bedrock_kb_id, org_id, kb_id, index_arn
                )

        if not bedrock_kb_id:
            remote_kb = create_bedrock_knowledge_base(
                org_id=org_id,
                kb_id=kb_id,
                index_arn=index_arn,
            )
            bedrock_kb_id = remote_kb.get("knowledgeBaseId")
            if not bedrock_kb_id:
                raise BedrockProvisioningError(
                    "bedrock_kb_create_failed", resource="knowledge_base"
                )
            knowledge_base.external_id = bedrock_kb_id
            _commit_state(db)
            wait_for_bedrock_knowledge_base(
                bedrock_kb_id, org_id, kb_id, index_arn
            )

        _set_provisioning_stage(db, knowledge_base, "creating_data_source")
        if bedrock_ds_id:
            remote_ds = get_bedrock_data_source(bedrock_kb_id, bedrock_ds_id)
            if remote_ds is None:
                bedrock_ds_id = None
                knowledge_base.external_data_source_id = None
                _commit_state(db)
            else:
                wait_for_bedrock_data_source(
                    bedrock_kb_id, bedrock_ds_id, org_id, kb_id
                )

        if not bedrock_ds_id:
            remote_ds = create_bedrock_data_source(
                bedrock_kb_id=bedrock_kb_id,
                org_id=org_id,
                kb_id=kb_id,
            )
            bedrock_ds_id = remote_ds.get("dataSourceId")
            if not bedrock_ds_id:
                raise BedrockProvisioningError(
                    "bedrock_data_source_create_failed", resource="data_source"
                )
            knowledge_base.external_data_source_id = bedrock_ds_id
            _commit_state(db)
            wait_for_bedrock_data_source(
                bedrock_kb_id, bedrock_ds_id, org_id, kb_id
            )

        _set_provisioning_stage(db, knowledge_base, "finalizing")
        knowledge_base.external_status = "ready"
        knowledge_base.external_last_error = None
        knowledge_base.provisioning_stage = "ready"
        knowledge_base.provisioning_stage_started_at = datetime.now(timezone.utc)
        _commit_state(db)
        logger.info(
            "knowledge_base_provisioning_completed organization_id=%s knowledge_base_id=%s total_duration_seconds=%s",
            org_id,
            kb_id,
            round(
                (datetime.now(timezone.utc) - _as_utc(knowledge_base.provisioning_started_at)).total_seconds(),
                3,
            ) if knowledge_base.provisioning_started_at else None,
        )
        return bedrock_kb_id, bedrock_ds_id
    except BedrockProvisioningError as error:
        failure = error
    except Exception as error:
        logger.exception("Unexpected Bedrock provisioning failure")
        failure = BedrockProvisioningError("provisioning_failed")

    db.rollback()
    cleanup = _cleanup_remote_resources(
        org_id,
        kb_id,
        index_arn,
        bedrock_kb_id,
        bedrock_ds_id,
    )
    knowledge_base.external_id = cleanup.bedrock_kb_id
    knowledge_base.external_data_source_id = cleanup.bedrock_ds_id
    knowledge_base.external_status = "failed"
    knowledge_base.provisioning_stage = "failed"
    knowledge_base.provisioning_stage_started_at = datetime.now(timezone.utc)
    knowledge_base.external_last_error = (
        failure.persistence_code if cleanup.succeeded else "cleanup_failed"
    )
    _commit_state(db, "failure_state_persist_failed")
    logger.error(
        "knowledge_base_provisioning_failed organization_id=%s knowledge_base_id=%s error_code=%s stage=%s classification=%s cleanup_succeeded=%s",
        org_id,
        kb_id,
        knowledge_base.external_last_error,
        failure.resource,
        failure.classification,
        cleanup.succeeded,
    )
    raise BedrockProvisioningError(
        failure.code if cleanup.succeeded else "cleanup_failed",
        resource=failure.resource,
        classification=failure.classification,
        aws_service=failure.aws_service if cleanup.succeeded else None,
        aws_operation=failure.aws_operation if cleanup.succeeded else None,
        aws_error_code=failure.aws_error_code if cleanup.succeeded else None,
        aws_request_id=failure.aws_request_id if cleanup.succeeded else None,
    ) from failure


def cleanup_bedrock_resources(db: Session, knowledge_base: KnowledgeBase) -> None:
    """Safely clean owned resources without losing ambiguous remote IDs."""
    try:
        index_arn = _vector_index_arn(knowledge_base.id)
    except BedrockProvisioningError:
        index_arn = None
    result = _cleanup_remote_resources(
        knowledge_base.organization_id,
        knowledge_base.id,
        index_arn,
        knowledge_base.external_id,
        knowledge_base.external_data_source_id,
    )
    knowledge_base.external_id = result.bedrock_kb_id
    knowledge_base.external_data_source_id = result.bedrock_ds_id
    knowledge_base.external_status = "failed"
    knowledge_base.external_last_error = (
        "resources_cleaned" if result.succeeded else "cleanup_failed"
    )
    _commit_state(db, "failure_state_persist_failed")

def delete_diaglob_knowledge_base(db: Session, knowledge_base: KnowledgeBase) -> None:
    """Delete one KB and only its verified remote resources and S3 prefix."""
    claimed = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base.id,
            KnowledgeBase.organization_id == knowledge_base.organization_id,
            KnowledgeBase.external_status != "deleting",
        )
        .update(
            {
                KnowledgeBase.external_status: "deleting",
                KnowledgeBase.external_last_error: None,
                KnowledgeBase.provisioning_stage: "deleting",
                KnowledgeBase.provisioning_stage_started_at: datetime.now(timezone.utc),
            },
            synchronize_session=False,
        )
    )
    _commit_state(db)
    db.refresh(knowledge_base)

    if not claimed and knowledge_base.external_status != "deleting":
        raise BedrockProvisioningError("invalid_deletion_state", resource="knowledge_base")

    org_id = knowledge_base.organization_id
    kb_id = knowledge_base.id

    if is_verified_legacy_parent(knowledge_base.external_id or ""):
        logger.info(
            "knowledge_base_deletion_routing organization_id=%s knowledge_base_id=%s deletion_mode=legacy",
            org_id, kb_id,
        )
        try:
            cleanup_verified_legacy_resources(db, knowledge_base)
            return
        except Exception as error:
            db.rollback()
            current = db.get(KnowledgeBase, kb_id)
            original_error_code = (
                error.code
                if isinstance(error, BedrockProvisioningError)
                else type(error).__name__
            )
            if current:
                current.external_status = "deleting"
                current.external_last_error = f"deletion_failed:{original_error_code}"
                current.provisioning_stage = "deleting"
                current.provisioning_stage_started_at = datetime.now(timezone.utc)
                _commit_state(db, "deletion_state_persist_failed")
            logger.exception(
                "knowledge_base_deletion_failed deletion_mode=legacy "
                "organization_id=%s knowledge_base_id=%s error_code=%s",
                org_id, kb_id, original_error_code,
            )
            if isinstance(error, BedrockProvisioningError):
                raise
            raise BedrockProvisioningError("deletion_failed", resource="knowledge_base") from error

    logger.info(
        "knowledge_base_deletion_routing organization_id=%s knowledge_base_id=%s deletion_mode=modern",
        org_id, kb_id,
    )
    index_arn: str | None = None
    try:
        index_arn = _vector_index_arn(kb_id)
        cleanup = _cleanup_remote_resources(
            org_id,
            kb_id,
            index_arn,
            knowledge_base.external_id,
            knowledge_base.external_data_source_id,
        )
        if not cleanup.succeeded:
            if isinstance(cleanup.error, BedrockProvisioningError):
                raise cleanup.error
            raise BedrockProvisioningError(
                "deletion_cleanup_failed", resource="knowledge_base"
            ) from cleanup.error
        delete_knowledge_prefix(org_id, kb_id)
        db.query(KnowledgeSource).filter(
            KnowledgeSource.organization_id == org_id,
            KnowledgeSource.knowledge_base_id == kb_id,
        ).delete(synchronize_session=False)
        db.delete(knowledge_base)
        _commit_state(db, "deletion_state_persist_failed")
    except Exception as error:
        db.rollback()
        current = db.get(KnowledgeBase, kb_id)
        original_error_code = (
            error.code
            if isinstance(error, BedrockProvisioningError)
            else type(error).__name__
        )
        if current:
            current.external_status = "deleting"
            current.external_last_error = f"deletion_failed:{original_error_code}"
            current.provisioning_stage = "deleting"
            current.provisioning_stage_started_at = datetime.now(timezone.utc)
            _commit_state(db, "deletion_state_persist_failed")
        logger.exception(
            "knowledge_base_deletion_failed deletion_mode=modern "
            "organization_id=%s knowledge_base_id=%s provisioning_stage=deleting "
            "error_code=%s aws_error_code=%s aws_error_message=%s "
            "aws_request_id=%s vector_index_arn=%s bedrock_kb_id=%s "
            "bedrock_data_source_id=%s",
            org_id,
            kb_id,
            original_error_code,
            _client_error_code(error),
            _client_error_message(error),
            _client_error_request_id(error),
            index_arn,
            knowledge_base.external_id,
            knowledge_base.external_data_source_id,
        )
        if isinstance(error, BedrockProvisioningError):
            raise
        raise BedrockProvisioningError("deletion_failed", resource="knowledge_base") from error
