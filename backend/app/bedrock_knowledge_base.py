"""Provision isolated Bedrock Knowledge Bases and S3 Vectors indexes."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import boto3
from sqlalchemy.orm import Session

from .bedrock_ingestion import AWS_REGION, _get_bedrock_agent_client
from .models import KnowledgeBase
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
from .knowledge_provisioning.cleanup import (
    CleanupResult,
    cleanup_remote_resources,
)
from .knowledge_provisioning.orchestrator import (
    ProvisioningOperations,
    provision_knowledge_base,
)
from .knowledge_provisioning.deletion import (
    DeletionOperations,
    cleanup_owned_resources,
    delete_knowledge_base,
)
from .knowledge_provisioning.legacy import (
    LEGACY_KNOWLEDGE_INFRASTRUCTURE,
    LegacyCleanupOperations,
    cleanup_verified_legacy_resources as cleanup_legacy_resources,
    is_verified_legacy_parent as legacy_parent_matches,
    legacy_vector_index_arn,
    validate_legacy_data_source_ownership as validate_legacy_ownership,
)
from .knowledge_provisioning.configuration import (
    KnowledgeProvisioningConfig,
    VECTOR_DATA_TYPE,
    VECTOR_DIMENSION,
    VECTOR_DISTANCE_METRIC,
    VECTOR_EMBEDDING_DATA_TYPE,
    VECTOR_NON_FILTERABLE_METADATA_KEYS,
    build_vector_index_name as config_build_vector_index_name,
    environment_slug as config_environment_slug,
    get_s3_prefix as config_get_s3_prefix,
    make_client_token as config_make_client_token,
    make_ds_name as config_make_ds_name,
    make_kb_name as config_make_kb_name,
    make_tags as config_make_tags,
    missing_configuration,
    normalize_environment as config_normalize_environment,
    validate_configuration as config_validate_configuration,
    vector_index_arn as config_vector_index_arn,
)

logger = logging.getLogger(__name__)










def normalize_environment(value: str | None) -> str:
    """Map a DIAGLOB_ENVIRONMENT value to a canonical form."""
    return config_normalize_environment(value)


_RAW_ENVIRONMENT = os.getenv("DIAGLOB_ENVIRONMENT")


def _resolve_environment(raw: str | None) -> str:
    """Resolve and canonicalize the environment at provisioning time."""
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


PROVISIONING_STATES = ("pending", "provisioning", "retrying", "ready", "failed", "deleting")
PROVISIONING_STAGES = (
    "queued", "creating_vector_index", "creating_knowledge_base",
    "creating_data_source", "finalizing", "retrying", "ready", "failed", "deleting",
)
RECOVERY_ATTEMPTS = int(os.getenv("BEDROCK_RECOVERY_ATTEMPTS", "3"))
WAIT_ATTEMPTS = int(os.getenv("BEDROCK_WAIT_ATTEMPTS", "30"))
POLL_INTERVAL_SECONDS = float(os.getenv("BEDROCK_POLL_INTERVAL_SECONDS", "2"))



def _get_s3_vectors_client():
    return boto3.client("s3vectors", region_name=AWS_REGION)


def _environment_slug(environment: str) -> str:
    return config_environment_slug(environment)


def build_vector_index_name(environment: str, kb_id: int) -> str:
    """Build a deterministic, non-PII S3 Vectors index name."""
    return config_build_vector_index_name(environment, kb_id)


def _make_kb_name(org_id: int, kb_id: int) -> str:
    return config_make_kb_name(ENVIRONMENT, org_id, kb_id)


def _make_ds_name(kb_id: int) -> str:
    return config_make_ds_name(ENVIRONMENT, kb_id)


def _make_client_token(prefix: str, org_id: int, kb_id: int) -> str:
    return config_make_client_token(ENVIRONMENT, prefix, org_id, kb_id)


def _make_tags(org_id: int, kb_id: int) -> dict[str, str]:
    return config_make_tags(ENVIRONMENT, org_id, kb_id)


def _get_s3_prefix(org_id: int, kb_id: int) -> str:
    return config_get_s3_prefix(org_id, kb_id)


def _vector_index_arn(kb_id: int) -> str:
    return config_vector_index_arn(VECTOR_BUCKET_ARN, ENVIRONMENT, kb_id)


def _current_provisioning_config() -> KnowledgeProvisioningConfig:
    """Capture current facade settings so monkeypatched runtime values remain live."""
    return KnowledgeProvisioningConfig(
        environment=ENVIRONMENT,
        vector_bucket_arn=VECTOR_BUCKET_ARN,
        bedrock_service_role_arn=BEDROCK_SERVICE_ROLE_ARN,
        embedding_model_arn=EMBEDDING_MODEL_ARN,
        knowledge_bucket=KNOWLEDGE_BUCKET,
    )


def _validate_configuration() -> None:
    config = _current_provisioning_config()
    missing = missing_configuration(config)
    if missing:
        logger.error(
            "Missing Bedrock provisioning configuration: %s",
            ", ".join(missing),
        )
    config_validate_configuration(config)


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
    return legacy_parent_matches(
        bedrock_kb_id,
        infrastructure=LEGACY_KNOWLEDGE_INFRASTRUCTURE,
    )


def _legacy_vector_index_arn() -> str:
    """Build the ARN for the legacy shared vector index."""
    return legacy_vector_index_arn(
        VECTOR_BUCKET_ARN,
        infrastructure=LEGACY_KNOWLEDGE_INFRASTRUCTURE,
    )


def validate_legacy_data_source_ownership(
    remote_ds: dict[str, Any],
    remote_kb: dict[str, Any],
    org_id: int,
    kb_id: int,
) -> None:
    """Verify a legacy Data Source is safe to delete."""
    validate_legacy_ownership(
        remote_ds,
        remote_kb,
        org_id,
        kb_id,
        legacy_kb_id=LEGACY_KNOWLEDGE_INFRASTRUCTURE["bedrock_kb_id"],
        knowledge_bucket=KNOWLEDGE_BUCKET,
        expected_prefix=_get_s3_prefix(org_id, kb_id),
    )


def _delete_legacy_data_source(
    bedrock_kb_id: str,
    bedrock_ds_id: str,
) -> Any:
    return _get_bedrock_agent_client().delete_data_source(
        knowledgeBaseId=bedrock_kb_id,
        dataSourceId=bedrock_ds_id,
    )


def _legacy_cleanup_operations() -> LegacyCleanupOperations:
    """Capture the facade's current legacy cleanup dependencies at call time."""
    return LegacyCleanupOperations(
        get_knowledge_base=get_bedrock_knowledge_base,
        get_data_source=get_bedrock_data_source,
        delete_data_source=_delete_legacy_data_source,
        validate_data_source_ownership=validate_legacy_data_source_ownership,
        delete_knowledge_prefix=delete_knowledge_prefix,
        commit_state=_commit_state,
        sleep_between_attempts=_sleep_between_attempts,
        client_error_code=_client_error_code,
        log_aws_error=_log_provisioning_aws_error,
        aws_provisioning_error=_aws_provisioning_error,
    )


def cleanup_verified_legacy_resources(
    db: Session,
    knowledge_base: KnowledgeBase,
) -> None:
    """Delete only the verified legacy Data Source and local resources."""
    cleanup_legacy_resources(
        db,
        knowledge_base,
        infrastructure=LEGACY_KNOWLEDGE_INFRASTRUCTURE,
        wait_attempts=WAIT_ATTEMPTS,
        operations=_legacy_cleanup_operations(),
    )


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
    return cleanup_remote_resources(
        org_id,
        kb_id,
        index_arn,
        bedrock_kb_id,
        bedrock_ds_id,
        delete_data_source=delete_bedrock_data_source,
        delete_knowledge_base=delete_bedrock_knowledge_base,
        delete_vector_index=delete_s3_vectors_index,
    )




def _provisioning_operations() -> ProvisioningOperations:
    """Capture the facade's current provisioning callables at invocation time."""
    return ProvisioningOperations(
        claim_provisioning=_claim_provisioning,
        create_vector_index=create_s3_vectors_index,
        set_stage=_set_provisioning_stage,
        get_knowledge_base=get_bedrock_knowledge_base,
        wait_for_knowledge_base=wait_for_bedrock_knowledge_base,
        create_knowledge_base=create_bedrock_knowledge_base,
        commit_state=_commit_state,
        get_data_source=get_bedrock_data_source,
        wait_for_data_source=wait_for_bedrock_data_source,
        create_data_source=create_bedrock_data_source,
        cleanup_remote_resources=_cleanup_remote_resources,
        as_utc=_as_utc,
    )


def provision_diaglob_knowledge_base(
    db: Session, knowledge_base: KnowledgeBase
) -> tuple[str, str]:
    """Provision one isolated index, Bedrock KB, and Data Source."""
    return provision_knowledge_base(
        db,
        knowledge_base,
        operations=_provisioning_operations(),
    )

def _deletion_operations() -> DeletionOperations:
    """Capture the facade's current deletion callables at invocation time."""
    return DeletionOperations(
        vector_index_arn=_vector_index_arn,
        cleanup_remote_resources=_cleanup_remote_resources,
        commit_state=_commit_state,
        is_verified_legacy_parent=is_verified_legacy_parent,
        cleanup_verified_legacy_resources=cleanup_verified_legacy_resources,
        delete_knowledge_prefix=delete_knowledge_prefix,
        client_error_code=_client_error_code,
        client_error_message=_client_error_message,
        client_error_request_id=_client_error_request_id,
    )


def cleanup_bedrock_resources(
    db: Session, knowledge_base: KnowledgeBase
) -> None:
    """Safely clean owned resources without losing ambiguous remote IDs."""
    cleanup_owned_resources(
        db,
        knowledge_base,
        operations=_deletion_operations(),
    )


def delete_diaglob_knowledge_base(
    db: Session, knowledge_base: KnowledgeBase
) -> None:
    """Delete one KB and only its verified remote resources and S3 prefix."""
    delete_knowledge_base(
        db,
        knowledge_base,
        operations=_deletion_operations(),
    )

