"""Provision isolated Bedrock Knowledge Bases and S3 Vectors indexes."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from .bedrock_ingestion import AWS_REGION, _get_bedrock_agent_client
from .models import KnowledgeBase

logger = logging.getLogger(__name__)


class BedrockProvisioningError(Exception):
    """A safe, stable provisioning failure suitable for persistence."""

    def __init__(self, code: str, resource: str | None = None):
        self.code = code
        self.resource = resource
        super().__init__(code)


class ProvisioningInProgressError(BedrockProvisioningError):
    """Raised when another request already owns the provisioning attempt."""

    def __init__(self):
        super().__init__("provisioning_in_progress", resource="knowledge_base")


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

PROVISIONING_STATES = ("pending", "provisioning", "ready", "failed")
RECOVERY_ATTEMPTS = int(os.getenv("BEDROCK_RECOVERY_ATTEMPTS", "3"))
WAIT_ATTEMPTS = int(os.getenv("BEDROCK_WAIT_ATTEMPTS", "30"))
POLL_INTERVAL_SECONDS = float(os.getenv("BEDROCK_POLL_INTERVAL_SECONDS", "2"))


@dataclass
class CleanupResult:
    succeeded: bool
    bedrock_kb_id: str | None
    bedrock_ds_id: str | None


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


def _client_error_code(error: Exception) -> str | None:
    if isinstance(error, ClientError):
        return error.response.get("Error", {}).get("Code")
    return None


def _is_uncertain_create_error(error: Exception) -> bool:
    if isinstance(error, BotoCoreError):
        return True
    return _client_error_code(error) in {
        "ConflictException",
        "InternalServerException",
        "RequestTimeoutException",
        "ServiceUnavailableException",
        "ThrottlingException",
        "TooManyRequestsException",
    }


def _sleep_between_attempts(attempt: int, attempts: int) -> None:
    if attempt + 1 < attempts and POLL_INTERVAL_SECONDS > 0:
        time.sleep(POLL_INTERVAL_SECONDS)


def _tags_match(actual: dict[str, str], expected: dict[str, str]) -> bool:
    return all(actual.get(key) == value for key, value in expected.items())


def get_s3_vectors_index(index_arn: str) -> dict[str, Any] | None:
    """Return an S3 Vectors index, or None when it does not exist."""
    try:
        return _get_s3_vectors_client().get_index(indexArn=index_arn).get("index")
    except ClientError as error:
        if _client_error_code(error) == "NotFoundException":
            return None
        logger.exception("Failed to inspect managed S3 Vectors index")
        raise BedrockProvisioningError(
            "vector_index_get_failed", resource="vector_index"
        ) from error
    except BotoCoreError as error:
        logger.exception("Failed to inspect managed S3 Vectors index")
        raise BedrockProvisioningError(
            "vector_index_get_failed", resource="vector_index"
        ) from error


def _get_s3_vectors_tags(index_arn: str) -> dict[str, str]:
    try:
        return _get_s3_vectors_client().list_tags_for_resource(
            resourceArn=index_arn
        ).get("tags", {})
    except (BotoCoreError, ClientError) as error:
        logger.exception("Failed to inspect managed S3 Vectors index tags")
        raise BedrockProvisioningError(
            "vector_index_tags_get_failed", resource="vector_index"
        ) from error


def _validate_s3_vectors_index(
    index: dict[str, Any],
    tags: dict[str, str],
    org_id: int,
    kb_id: int,
) -> None:
    expected_arn = _vector_index_arn(kb_id)
    expected_name = build_vector_index_name(ENVIRONMENT, kb_id)
    if (
        index.get("indexArn") != expected_arn
        or index.get("indexName") != expected_name
        or not _tags_match(tags, _make_tags(org_id, kb_id))
    ):
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="vector_index"
        )

    metadata_keys = set(
        index.get("metadataConfiguration", {}).get(
            "nonFilterableMetadataKeys", []
        )
    )
    if (
        index.get("dataType") != VECTOR_DATA_TYPE
        or index.get("dimension") != VECTOR_DIMENSION
        or index.get("distanceMetric") != VECTOR_DISTANCE_METRIC
        or not set(VECTOR_NON_FILTERABLE_METADATA_KEYS).issubset(metadata_keys)
    ):
        raise BedrockProvisioningError(
            "vector_index_configuration_mismatch", resource="vector_index"
        )


def _recover_s3_vectors_index(org_id: int, kb_id: int) -> dict[str, Any] | None:
    index_arn = _vector_index_arn(kb_id)
    for attempt in range(RECOVERY_ATTEMPTS):
        index = get_s3_vectors_index(index_arn)
        if index:
            _validate_s3_vectors_index(
                index,
                _get_s3_vectors_tags(index_arn),
                org_id,
                kb_id,
            )
            return index
        _sleep_between_attempts(attempt, RECOVERY_ATTEMPTS)
    return None


def create_s3_vectors_index(org_id: int, kb_id: int) -> dict[str, Any]:
    """Create or safely recover the deterministic S3 Vectors index."""
    _validate_configuration()
    index_name = build_vector_index_name(ENVIRONMENT, kb_id)
    index_arn = _vector_index_arn(kb_id)
    try:
        response = _get_s3_vectors_client().create_index(
            vectorBucketArn=VECTOR_BUCKET_ARN,
            indexName=index_name,
            dataType=VECTOR_DATA_TYPE,
            dimension=VECTOR_DIMENSION,
            distanceMetric=VECTOR_DISTANCE_METRIC,
            metadataConfiguration={
                "nonFilterableMetadataKeys": list(
                    VECTOR_NON_FILTERABLE_METADATA_KEYS
                )
            },
            tags=_make_tags(org_id, kb_id),
        )
        if response.get("indexArn") != index_arn:
            raise BedrockProvisioningError(
                "vector_index_create_failed", resource="vector_index"
            )
    except BedrockProvisioningError:
        raise
    except (BotoCoreError, ClientError) as error:
        if not _is_uncertain_create_error(error):
            logger.exception("Failed to create managed S3 Vectors index")
            raise BedrockProvisioningError(
                "vector_index_create_failed", resource="vector_index"
            ) from error
        logger.warning(
            "S3 Vectors index create response was uncertain; attempting recovery",
            exc_info=True,
        )

    recovered = _recover_s3_vectors_index(org_id, kb_id)
    if not recovered:
        raise BedrockProvisioningError(
            "resource_recovery_failed", resource="vector_index"
        )
    return recovered


def delete_s3_vectors_index(index_arn: str, org_id: int, kb_id: int) -> None:
    """Delete only the owned deterministic index and confirm its absence."""
    if index_arn != _vector_index_arn(kb_id):
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="vector_index"
        )
    index = get_s3_vectors_index(index_arn)
    if not index:
        return
    _validate_s3_vectors_index(
        index,
        _get_s3_vectors_tags(index_arn),
        org_id,
        kb_id,
    )
    try:
        _get_s3_vectors_client().delete_index(indexArn=index_arn)
    except ClientError as error:
        if _client_error_code(error) == "NotFoundException":
            return
        logger.exception("Failed to delete managed S3 Vectors index")
        raise BedrockProvisioningError(
            "vector_index_delete_failed", resource="vector_index"
        ) from error
    except BotoCoreError as error:
        logger.exception("Failed to delete managed S3 Vectors index")
        raise BedrockProvisioningError(
            "vector_index_delete_failed", resource="vector_index"
        ) from error

    for attempt in range(WAIT_ATTEMPTS):
        if get_s3_vectors_index(index_arn) is None:
            return
        _sleep_between_attempts(attempt, WAIT_ATTEMPTS)
    raise BedrockProvisioningError(
        "vector_index_delete_unconfirmed", resource="vector_index"
    )


def get_bedrock_knowledge_base(bedrock_kb_id: str) -> dict[str, Any] | None:
    try:
        response = _get_bedrock_agent_client().get_knowledge_base(
            knowledgeBaseId=bedrock_kb_id
        )
        return response.get("knowledgeBase")
    except ClientError as error:
        if _client_error_code(error) == "ResourceNotFoundException":
            return None
        logger.exception("Failed to inspect Bedrock Knowledge Base")
        raise BedrockProvisioningError(
            "bedrock_kb_get_failed", resource="knowledge_base"
        ) from error
    except BotoCoreError as error:
        logger.exception("Failed to inspect Bedrock Knowledge Base")
        raise BedrockProvisioningError(
            "bedrock_kb_get_failed", resource="knowledge_base"
        ) from error


def _get_bedrock_tags(resource_arn: str) -> dict[str, str]:
    try:
        return _get_bedrock_agent_client().list_tags_for_resource(
            resourceArn=resource_arn
        ).get("tags", {})
    except (BotoCoreError, ClientError) as error:
        logger.exception("Failed to inspect Bedrock Knowledge Base tags")
        raise BedrockProvisioningError(
            "bedrock_kb_tags_get_failed", resource="knowledge_base"
        ) from error


def _validate_bedrock_knowledge_base(
    remote: dict[str, Any],
    org_id: int,
    kb_id: int,
    index_arn: str,
) -> None:
    if (
        remote.get("name") != _make_kb_name(org_id, kb_id)
        or remote.get("roleArn") != BEDROCK_SERVICE_ROLE_ARN
    ):
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="knowledge_base"
        )

    storage = remote.get("storageConfiguration", {})
    s3_vectors = storage.get("s3VectorsConfiguration", {})
    configuration = remote.get("knowledgeBaseConfiguration", {})
    vector_configuration = configuration.get("vectorKnowledgeBaseConfiguration", {})
    embedding_configuration = vector_configuration.get(
        "embeddingModelConfiguration", {}
    ).get("bedrockEmbeddingModelConfiguration", {})
    if (
        storage.get("type") != "S3_VECTORS"
        or s3_vectors.get("vectorBucketArn") != VECTOR_BUCKET_ARN
        or s3_vectors.get("indexArn") != index_arn
        or configuration.get("type") != "VECTOR"
        or vector_configuration.get("embeddingModelArn") != EMBEDDING_MODEL_ARN
        or embedding_configuration.get("dimensions") != VECTOR_DIMENSION
        or embedding_configuration.get("embeddingDataType")
        != VECTOR_EMBEDDING_DATA_TYPE
    ):
        raise BedrockProvisioningError(
            "bedrock_kb_configuration_mismatch", resource="knowledge_base"
        )

    resource_arn = remote.get("knowledgeBaseArn")
    if not resource_arn or not _tags_match(
        _get_bedrock_tags(resource_arn), _make_tags(org_id, kb_id)
    ):
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="knowledge_base"
        )


def _list_knowledge_bases_by_name(name: str) -> list[dict[str, Any]]:
    client = _get_bedrock_agent_client()
    candidates = []
    next_token = None
    try:
        while True:
            kwargs = {"maxResults": 1000}
            if next_token:
                kwargs["nextToken"] = next_token
            response = client.list_knowledge_bases(**kwargs)
            candidates.extend(
                item
                for item in response.get("knowledgeBaseSummaries", [])
                if item.get("name") == name
            )
            next_token = response.get("nextToken")
            if not next_token:
                return candidates
    except (BotoCoreError, ClientError) as error:
        logger.exception("Failed to discover Bedrock Knowledge Base")
        raise BedrockProvisioningError(
            "resource_recovery_failed", resource="knowledge_base"
        ) from error


def discover_bedrock_knowledge_base(
    org_id: int, kb_id: int, index_arn: str
) -> dict[str, Any] | None:
    expected_name = _make_kb_name(org_id, kb_id)
    for attempt in range(RECOVERY_ATTEMPTS):
        candidates = _list_knowledge_bases_by_name(expected_name)
        if len(candidates) > 1:
            raise BedrockProvisioningError(
                "resource_recovery_ambiguous", resource="knowledge_base"
            )
        if candidates:
            remote = get_bedrock_knowledge_base(candidates[0]["knowledgeBaseId"])
            if remote:
                _validate_bedrock_knowledge_base(remote, org_id, kb_id, index_arn)
                return remote
        _sleep_between_attempts(attempt, RECOVERY_ATTEMPTS)
    return None


def create_bedrock_knowledge_base(
    org_id: int,
    kb_id: int,
    index_arn: str,
    description: str | None = None,
) -> dict[str, Any]:
    """Create a Bedrock KB using the already-created vector index."""
    _validate_configuration()
    create_kwargs = {
        "name": _make_kb_name(org_id, kb_id),
        "description": description
        or f"Diaglob Knowledge Base for organization {org_id}, KB {kb_id}",
        "roleArn": BEDROCK_SERVICE_ROLE_ARN,
        "knowledgeBaseConfiguration": {
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": EMBEDDING_MODEL_ARN,
                "embeddingModelConfiguration": {
                    "bedrockEmbeddingModelConfiguration": {
                        "dimensions": VECTOR_DIMENSION,
                        "embeddingDataType": VECTOR_EMBEDDING_DATA_TYPE,
                    }
                },
            },
        },
        "storageConfiguration": {
            "type": "S3_VECTORS",
            "s3VectorsConfiguration": {
                "vectorBucketArn": VECTOR_BUCKET_ARN,
                "indexArn": index_arn,
            },
        },
        "clientToken": _make_client_token("kb", org_id, kb_id),
        "tags": _make_tags(org_id, kb_id),
    }
    try:
        remote = _get_bedrock_agent_client().create_knowledge_base(
            **create_kwargs
        ).get("knowledgeBase", {})
        if remote.get("knowledgeBaseId"):
            return remote
        logger.warning("Bedrock KB create response omitted the resource ID")
    except (BotoCoreError, ClientError) as error:
        if not _is_uncertain_create_error(error):
            logger.exception("Failed to create Bedrock Knowledge Base")
            raise BedrockProvisioningError(
                "bedrock_kb_create_failed", resource="knowledge_base"
            ) from error
        logger.warning(
            "Bedrock KB create response was uncertain; attempting recovery",
            exc_info=True,
        )

    recovered = discover_bedrock_knowledge_base(org_id, kb_id, index_arn)
    if not recovered:
        raise BedrockProvisioningError(
            "resource_recovery_failed", resource="knowledge_base"
        )
    return recovered


def wait_for_bedrock_knowledge_base(
    bedrock_kb_id: str, org_id: int, kb_id: int, index_arn: str
) -> dict[str, Any]:
    for attempt in range(WAIT_ATTEMPTS):
        remote = get_bedrock_knowledge_base(bedrock_kb_id)
        if remote:
            _validate_bedrock_knowledge_base(remote, org_id, kb_id, index_arn)
            status = remote.get("status")
            if status == "ACTIVE":
                return remote
            if status in {"FAILED", "DELETE_UNSUCCESSFUL"}:
                raise BedrockProvisioningError(
                    "bedrock_kb_not_active", resource="knowledge_base"
                )
        _sleep_between_attempts(attempt, WAIT_ATTEMPTS)
    raise BedrockProvisioningError(
        "bedrock_kb_activation_timeout", resource="knowledge_base"
    )


def get_bedrock_data_source(
    bedrock_kb_id: str, data_source_id: str
) -> dict[str, Any] | None:
    try:
        response = _get_bedrock_agent_client().get_data_source(
            knowledgeBaseId=bedrock_kb_id,
            dataSourceId=data_source_id,
        )
        return response.get("dataSource")
    except ClientError as error:
        if _client_error_code(error) == "ResourceNotFoundException":
            return None
        logger.exception("Failed to inspect Bedrock Data Source")
        raise BedrockProvisioningError(
            "bedrock_data_source_get_failed", resource="data_source"
        ) from error
    except BotoCoreError as error:
        logger.exception("Failed to inspect Bedrock Data Source")
        raise BedrockProvisioningError(
            "bedrock_data_source_get_failed", resource="data_source"
        ) from error


def _validate_bedrock_data_source(
    remote: dict[str, Any], bedrock_kb_id: str, org_id: int, kb_id: int
) -> None:
    s3_configuration = remote.get("dataSourceConfiguration", {}).get(
        "s3Configuration", {}
    )
    chunking = remote.get("vectorIngestionConfiguration", {}).get(
        "chunkingConfiguration", {}
    )
    fixed_size = chunking.get("fixedSizeChunkingConfiguration", {})
    if (
        remote.get("knowledgeBaseId") != bedrock_kb_id
        or remote.get("name") != _make_ds_name(kb_id)
        or remote.get("dataSourceConfiguration", {}).get("type") != "S3"
        or s3_configuration.get("bucketArn") != f"arn:aws:s3:::{KNOWLEDGE_BUCKET}"
        or s3_configuration.get("inclusionPrefixes")
        != [_get_s3_prefix(org_id, kb_id)]
        or remote.get("dataDeletionPolicy") != "DELETE"
        or chunking.get("chunkingStrategy") != "FIXED_SIZE"
        or fixed_size.get("maxTokens") != 300
        or fixed_size.get("overlapPercentage") != 20
    ):
        raise BedrockProvisioningError(
            "resource_ownership_mismatch", resource="data_source"
        )


def discover_bedrock_data_source(
    bedrock_kb_id: str, org_id: int, kb_id: int
) -> dict[str, Any] | None:
    expected_name = _make_ds_name(kb_id)
    for attempt in range(RECOVERY_ATTEMPTS):
        client = _get_bedrock_agent_client()
        candidates = []
        next_token = None
        try:
            while True:
                kwargs: dict[str, Any] = {
                    "knowledgeBaseId": bedrock_kb_id,
                    "maxResults": 1000,
                }
                if next_token:
                    kwargs["nextToken"] = next_token
                response = client.list_data_sources(**kwargs)
                candidates.extend(
                    item
                    for item in response.get("dataSourceSummaries", [])
                    if item.get("name") == expected_name
                )
                next_token = response.get("nextToken")
                if not next_token:
                    break
        except (BotoCoreError, ClientError) as error:
            logger.exception("Failed to discover Bedrock Data Source")
            raise BedrockProvisioningError(
                "resource_recovery_failed", resource="data_source"
            ) from error

        if len(candidates) > 1:
            raise BedrockProvisioningError(
                "resource_recovery_ambiguous", resource="data_source"
            )
        if candidates:
            remote = get_bedrock_data_source(
                bedrock_kb_id, candidates[0]["dataSourceId"]
            )
            if remote:
                _validate_bedrock_data_source(
                    remote, bedrock_kb_id, org_id, kb_id
                )
                return remote
        _sleep_between_attempts(attempt, RECOVERY_ATTEMPTS)
    return None


def create_bedrock_data_source(
    bedrock_kb_id: str,
    org_id: int,
    kb_id: int,
) -> dict[str, Any]:
    """Create or safely recover the single tenant-scoped S3 data source."""
    create_kwargs = {
        "knowledgeBaseId": bedrock_kb_id,
        "name": _make_ds_name(kb_id),
        "description": f"Diaglob S3 Data Source for org {org_id}, KB {kb_id}",
        "dataSourceConfiguration": {
            "type": "S3",
            "s3Configuration": {
                "bucketArn": f"arn:aws:s3:::{KNOWLEDGE_BUCKET}",
                "inclusionPrefixes": [_get_s3_prefix(org_id, kb_id)],
            },
        },
        "vectorIngestionConfiguration": {
            "chunkingConfiguration": {
                "chunkingStrategy": "FIXED_SIZE",
                "fixedSizeChunkingConfiguration": {
                    "maxTokens": 300,
                    "overlapPercentage": 20,
                },
            },
        },
        "dataDeletionPolicy": "DELETE",
        "clientToken": _make_client_token("ds", org_id, kb_id),
    }
    try:
        remote = _get_bedrock_agent_client().create_data_source(
            **create_kwargs
        ).get("dataSource", {})
        if remote.get("dataSourceId"):
            return remote
        logger.warning("Bedrock Data Source create response omitted the resource ID")
    except (BotoCoreError, ClientError) as error:
        if not _is_uncertain_create_error(error):
            logger.exception("Failed to create Bedrock Data Source")
            raise BedrockProvisioningError(
                "bedrock_data_source_create_failed", resource="data_source"
            ) from error
        logger.warning(
            "Bedrock Data Source create response was uncertain; attempting recovery",
            exc_info=True,
        )

    parent = get_bedrock_knowledge_base(bedrock_kb_id)
    if not parent:
        raise BedrockProvisioningError(
            "resource_recovery_failed", resource="data_source"
        )
    _validate_bedrock_knowledge_base(
        parent, org_id, kb_id, _vector_index_arn(kb_id)
    )
    if parent.get("status") != "ACTIVE":
        raise BedrockProvisioningError(
            "resource_recovery_failed", resource="data_source"
        )

    recovered = discover_bedrock_data_source(bedrock_kb_id, org_id, kb_id)
    if not recovered:
        raise BedrockProvisioningError(
            "resource_recovery_failed", resource="data_source"
        )
    return recovered


def wait_for_bedrock_data_source(
    bedrock_kb_id: str, data_source_id: str, org_id: int, kb_id: int
) -> dict[str, Any]:
    for attempt in range(WAIT_ATTEMPTS):
        remote = get_bedrock_data_source(bedrock_kb_id, data_source_id)
        if remote:
            _validate_bedrock_data_source(
                remote, bedrock_kb_id, org_id, kb_id
            )
            status = remote.get("status")
            if status == "AVAILABLE":
                return remote
            if status in {"FAILED", "DELETE_UNSUCCESSFUL"}:
                raise BedrockProvisioningError(
                    "bedrock_data_source_not_available", resource="data_source"
                )
        _sleep_between_attempts(attempt, WAIT_ATTEMPTS)
    raise BedrockProvisioningError(
        "bedrock_data_source_activation_timeout", resource="data_source"
    )


def delete_bedrock_data_source(
    bedrock_kb_id: str,
    data_source_id: str,
    org_id: int,
    kb_id: int,
    index_arn: str,
) -> None:
    parent = get_bedrock_knowledge_base(bedrock_kb_id)
    if not parent:
        return
    _validate_bedrock_knowledge_base(parent, org_id, kb_id, index_arn)
    remote = get_bedrock_data_source(bedrock_kb_id, data_source_id)
    if not remote:
        return
    _validate_bedrock_data_source(remote, bedrock_kb_id, org_id, kb_id)
    try:
        _get_bedrock_agent_client().delete_data_source(
            knowledgeBaseId=bedrock_kb_id,
            dataSourceId=data_source_id,
        )
    except ClientError as error:
        if _client_error_code(error) == "ResourceNotFoundException":
            return
        raise BedrockProvisioningError(
            "bedrock_data_source_delete_failed", resource="data_source"
        ) from error
    except BotoCoreError as error:
        raise BedrockProvisioningError(
            "bedrock_data_source_delete_failed", resource="data_source"
        ) from error

    for attempt in range(WAIT_ATTEMPTS):
        remote = get_bedrock_data_source(bedrock_kb_id, data_source_id)
        if remote is None:
            return
        if remote.get("status") == "DELETE_UNSUCCESSFUL":
            break
        _sleep_between_attempts(attempt, WAIT_ATTEMPTS)
    raise BedrockProvisioningError(
        "bedrock_data_source_delete_unconfirmed", resource="data_source"
    )


def delete_bedrock_knowledge_base(
    bedrock_kb_id: str, org_id: int, kb_id: int, index_arn: str
) -> None:
    remote = get_bedrock_knowledge_base(bedrock_kb_id)
    if not remote:
        return
    _validate_bedrock_knowledge_base(remote, org_id, kb_id, index_arn)
    try:
        _get_bedrock_agent_client().delete_knowledge_base(
            knowledgeBaseId=bedrock_kb_id
        )
    except ClientError as error:
        if _client_error_code(error) == "ResourceNotFoundException":
            return
        raise BedrockProvisioningError(
            "bedrock_kb_delete_failed", resource="knowledge_base"
        ) from error
    except BotoCoreError as error:
        raise BedrockProvisioningError(
            "bedrock_kb_delete_failed", resource="knowledge_base"
        ) from error

    for attempt in range(WAIT_ATTEMPTS):
        remote = get_bedrock_knowledge_base(bedrock_kb_id)
        if remote is None:
            return
        if remote.get("status") == "DELETE_UNSUCCESSFUL":
            break
        _sleep_between_attempts(attempt, WAIT_ATTEMPTS)
    raise BedrockProvisioningError(
        "bedrock_kb_delete_unconfirmed", resource="knowledge_base"
    )


def _commit_state(db: Session, error_code: str = "database_state_persist_failed") -> None:
    try:
        db.commit()
    except Exception as error:
        db.rollback()
        logger.exception("Failed to persist Knowledge Base provisioning state")
        raise BedrockProvisioningError(error_code, resource="database") from error


def _claim_provisioning(db: Session, knowledge_base: KnowledgeBase) -> None:
    updated = (
        db.query(KnowledgeBase)
        .filter(
            KnowledgeBase.id == knowledge_base.id,
            KnowledgeBase.organization_id == knowledge_base.organization_id,
            KnowledgeBase.external_status.in_(("pending", "failed")),
        )
        .update(
            {
                KnowledgeBase.external_status: "provisioning",
                KnowledgeBase.external_last_error: None,
            },
            synchronize_session=False,
        )
    )
    _commit_state(db)
    db.refresh(knowledge_base)
    if updated == 1:
        return
    if knowledge_base.external_status == "provisioning":
        raise ProvisioningInProgressError()
    raise BedrockProvisioningError(
        "invalid_provisioning_state", resource="knowledge_base"
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
        except Exception:
            logger.exception("Unable to confirm Bedrock Data Source cleanup")
            return CleanupResult(False, remaining_kb_id, remaining_ds_id)

    if remaining_kb_id and index_arn:
        try:
            delete_bedrock_knowledge_base(
                remaining_kb_id, org_id, kb_id, index_arn
            )
            remaining_kb_id = None
            remaining_ds_id = None
        except Exception:
            logger.exception("Unable to confirm Bedrock Knowledge Base cleanup")
            return CleanupResult(False, remaining_kb_id, remaining_ds_id)

    if index_arn:
        try:
            delete_s3_vectors_index(index_arn, org_id, kb_id)
        except Exception:
            logger.exception("Unable to confirm S3 Vectors index cleanup")
            return CleanupResult(False, remaining_kb_id, remaining_ds_id)

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
    index_arn: str | None = None
    bedrock_kb_id = knowledge_base.external_id
    bedrock_ds_id = knowledge_base.external_data_source_id
    failure: BedrockProvisioningError | None = None

    try:
        vector_index = create_s3_vectors_index(org_id, kb_id)
        index_arn = vector_index["indexArn"]

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

        knowledge_base.external_status = "ready"
        knowledge_base.external_last_error = None
        _commit_state(db)
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
    knowledge_base.external_last_error = (
        failure.code if cleanup.succeeded else "cleanup_failed"
    )
    _commit_state(db, "failure_state_persist_failed")
    raise BedrockProvisioningError(
        knowledge_base.external_last_error,
        resource=failure.resource,
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
