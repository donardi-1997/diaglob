"""Pure configuration and naming rules for Knowledge provisioning.

Runtime environment loading intentionally remains in the compatibility facade.
This module owns deterministic normalization, names, tags, prefixes, ARNs, and
configuration validation without reaching into process environment variables.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .errors import BedrockProvisioningError


CANONICAL_ENVIRONMENTS: dict[str, str] = {
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

VECTOR_DIMENSION = 1024
VECTOR_DATA_TYPE = "float32"
VECTOR_EMBEDDING_DATA_TYPE = "FLOAT32"
VECTOR_DISTANCE_METRIC = "cosine"
VECTOR_NON_FILTERABLE_METADATA_KEYS = (
    "AMAZON_BEDROCK_TEXT",
    "AMAZON_BEDROCK_METADATA",
)


@dataclass(frozen=True)
class KnowledgeProvisioningConfig:
    """Runtime values required to derive and validate AWS Knowledge resources."""

    environment: str
    vector_bucket_arn: str
    bedrock_service_role_arn: str
    embedding_model_arn: str
    knowledge_bucket: str


def normalize_environment(value: str | None) -> str:
    """Map an environment alias to the canonical Diaglob environment name."""
    if not value or not value.strip():
        raise BedrockProvisioningError(
            "invalid_environment",
            resource="configuration",
        )
    key = value.strip().lower()
    canonical = CANONICAL_ENVIRONMENTS.get(key)
    if canonical is None:
        raise BedrockProvisioningError(
            "invalid_environment",
            resource="configuration",
        )
    return canonical


def environment_slug(environment: str) -> str:
    """Return the stable short environment component used in AWS names."""
    slug_aliases = {
        "production": "prod",
        "development": "dev",
    }
    value = slug_aliases.get(
        environment.strip().lower(),
        environment.strip().lower(),
    )
    value = re.sub(r"[^a-z0-9-]+", "-", value).strip("-")
    if not value:
        raise BedrockProvisioningError(
            "invalid_environment",
            resource="configuration",
        )
    return value


def build_vector_index_name(environment: str, kb_id: int) -> str:
    """Build the deterministic, non-PII S3 Vectors index name."""
    name = f"diaglob-{environment_slug(environment)}-kb-{kb_id}"
    if len(name) > 63 or not re.fullmatch(
        r"[a-z0-9][a-z0-9.-]+[a-z0-9]",
        name,
    ):
        raise BedrockProvisioningError(
            "invalid_vector_index_name",
            resource="vector_index",
        )
    return name


def make_kb_name(environment: str, org_id: int, kb_id: int) -> str:
    return f"diaglob-{environment_slug(environment)}-org-{org_id}-kb-{kb_id}"


def make_ds_name(environment: str, kb_id: int) -> str:
    return f"diaglob-{environment_slug(environment)}-kb-{kb_id}-s3"


def make_client_token(
    environment: str,
    prefix: str,
    org_id: int,
    kb_id: int,
) -> str:
    source = f"diaglob:{environment}:{prefix}:{org_id}:{kb_id}"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"diaglob-{prefix}-{digest}"


def make_tags(environment: str, org_id: int, kb_id: int) -> dict[str, str]:
    return {
        "diaglob:managed-by": "diaglob-backend",
        "diaglob:environment": environment,
        "diaglob:organization_id": str(org_id),
        "diaglob:knowledge_base_id": str(kb_id),
    }


def get_s3_prefix(org_id: int, kb_id: int) -> str:
    return f"organizations/{org_id}/knowledge-bases/{kb_id}/documents/"


def vector_index_arn(
    vector_bucket_arn: str,
    environment: str,
    kb_id: int,
) -> str:
    if not vector_bucket_arn:
        raise BedrockProvisioningError(
            "vector_bucket_not_configured",
            resource="configuration",
        )
    return (
        f"{vector_bucket_arn}/index/"
        f"{build_vector_index_name(environment, kb_id)}"
    )


def missing_configuration(config: KnowledgeProvisioningConfig) -> tuple[str, ...]:
    """Return missing required environment variable names in stable order."""
    missing: list[str] = []
    if not config.environment:
        missing.append("DIAGLOB_ENVIRONMENT")
    if not config.vector_bucket_arn:
        missing.append("DIAGLOB_VECTOR_BUCKET_ARN")
    if not config.bedrock_service_role_arn:
        missing.append("BEDROCK_SERVICE_ROLE_ARN")
    if not config.knowledge_bucket:
        missing.append("DIAGLOB_KNOWLEDGE_BUCKET")
    return tuple(missing)


def validate_configuration(config: KnowledgeProvisioningConfig) -> None:
    """Fail fast if required Knowledge provisioning settings are absent."""
    if missing_configuration(config):
        raise BedrockProvisioningError(
            "provisioning_configuration_missing",
            resource="configuration",
        )
