"""Boundary tests for deterministic Knowledge provisioning configuration rules."""

import pytest

from app import bedrock_knowledge_base as facade
from app.knowledge_provisioning.configuration import (
    KnowledgeProvisioningConfig,
    VECTOR_DATA_TYPE,
    VECTOR_DIMENSION,
    VECTOR_DISTANCE_METRIC,
    VECTOR_EMBEDDING_DATA_TYPE,
    VECTOR_NON_FILTERABLE_METADATA_KEYS,
    build_vector_index_name,
    get_s3_prefix,
    make_client_token,
    make_ds_name,
    make_kb_name,
    make_tags,
    missing_configuration,
    normalize_environment,
    validate_configuration,
    vector_index_arn,
)
from app.knowledge_provisioning.errors import BedrockProvisioningError


VECTOR_BUCKET_ARN = (
    "arn:aws:s3vectors:us-east-2:123456789012:bucket/diaglob-vectors-test"
)
ROLE_ARN = "arn:aws:iam::123456789012:role/DiaglobBedrockKnowledgeBaseRole"
MODEL_ARN = (
    "arn:aws:bedrock:us-east-2::foundation-model/"
    "amazon.titan-embed-text-v2:0"
)
KNOWLEDGE_BUCKET = "diaglob-knowledge-test"


@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("prod", "production"),
        ("production", "production"),
        ("stage", "staging"),
        ("staging", "staging"),
        ("dev", "development"),
        ("development", "development"),
        ("local", "development"),
        ("test", "test"),
        ("testing", "test"),
        ("  DEV  ", "development"),
    ],
)
def test_normalize_environment_aliases(raw, canonical):
    assert normalize_environment(raw) == canonical


@pytest.mark.parametrize("raw", [None, "", "   ", "banana", "productionn"])
def test_normalize_environment_rejects_invalid_values(raw):
    with pytest.raises(BedrockProvisioningError) as exc:
        normalize_environment(raw)
    assert exc.value.code == "invalid_environment"


def test_naming_rules_are_deterministic_and_non_pii():
    assert build_vector_index_name("production", 42) == "diaglob-prod-kb-42"
    assert make_kb_name("production", 7, 42) == "diaglob-prod-org-7-kb-42"
    assert make_ds_name("production", 42) == "diaglob-prod-kb-42-s3"
    assert get_s3_prefix(7, 42) == (
        "organizations/7/knowledge-bases/42/documents/"
    )
    assert vector_index_arn(VECTOR_BUCKET_ARN, "production", 42) == (
        f"{VECTOR_BUCKET_ARN}/index/diaglob-prod-kb-42"
    )


def test_tags_and_client_tokens_preserve_existing_shape():
    tags = make_tags("production", 7, 42)
    assert tags == {
        "diaglob:managed-by": "diaglob-backend",
        "diaglob:environment": "production",
        "diaglob:organization_id": "7",
        "diaglob:knowledge_base_id": "42",
    }

    first = make_client_token("production", "kb", 7, 42)
    second = make_client_token("production", "kb", 7, 42)
    other = make_client_token("production", "ds", 7, 42)
    assert first == second
    assert first != other
    assert first.startswith("diaglob-kb-")
    assert 33 <= len(first) <= 256
    assert first[0].isalnum() and first[-1].isalnum()


def test_vector_contract_constants_are_preserved():
    assert VECTOR_DIMENSION == 1024
    assert VECTOR_DATA_TYPE == "float32"
    assert VECTOR_EMBEDDING_DATA_TYPE == "FLOAT32"
    assert VECTOR_DISTANCE_METRIC == "cosine"
    assert VECTOR_NON_FILTERABLE_METADATA_KEYS == (
        "AMAZON_BEDROCK_TEXT",
        "AMAZON_BEDROCK_METADATA",
    )


def test_vector_index_arn_requires_bucket_configuration():
    with pytest.raises(BedrockProvisioningError) as exc:
        vector_index_arn("", "production", 42)
    assert exc.value.code == "vector_bucket_not_configured"


def test_missing_configuration_order_matches_existing_diagnostics():
    config = KnowledgeProvisioningConfig(
        environment="",
        vector_bucket_arn="",
        bedrock_service_role_arn="",
        embedding_model_arn="",
        knowledge_bucket="",
    )
    assert missing_configuration(config) == (
        "DIAGLOB_ENVIRONMENT",
        "DIAGLOB_VECTOR_BUCKET_ARN",
        "BEDROCK_SERVICE_ROLE_ARN",
        "DIAGLOB_KNOWLEDGE_BUCKET",
    )
    with pytest.raises(BedrockProvisioningError) as exc:
        validate_configuration(config)
    assert exc.value.code == "provisioning_configuration_missing"


def test_embedding_model_remains_optional_in_required_config_validation():
    config = KnowledgeProvisioningConfig(
        environment="production",
        vector_bucket_arn=VECTOR_BUCKET_ARN,
        bedrock_service_role_arn=ROLE_ARN,
        embedding_model_arn="",
        knowledge_bucket=KNOWLEDGE_BUCKET,
    )
    assert missing_configuration(config) == ()
    validate_configuration(config)


def test_facade_uses_current_runtime_values_at_call_time(monkeypatch):
    monkeypatch.setattr(facade, "ENVIRONMENT", "staging")
    monkeypatch.setattr(facade, "VECTOR_BUCKET_ARN", VECTOR_BUCKET_ARN)
    monkeypatch.setattr(facade, "BEDROCK_SERVICE_ROLE_ARN", ROLE_ARN)
    monkeypatch.setattr(facade, "EMBEDDING_MODEL_ARN", MODEL_ARN)
    monkeypatch.setattr(facade, "KNOWLEDGE_BUCKET", KNOWLEDGE_BUCKET)

    assert facade.build_vector_index_name("production", 9) == "diaglob-prod-kb-9"
    assert facade._make_kb_name(3, 9) == "diaglob-staging-org-3-kb-9"
    assert facade._make_ds_name(9) == "diaglob-staging-kb-9-s3"
    assert facade._get_s3_prefix(3, 9) == (
        "organizations/3/knowledge-bases/9/documents/"
    )
    assert facade._vector_index_arn(9) == (
        f"{VECTOR_BUCKET_ARN}/index/diaglob-staging-kb-9"
    )
    assert facade._make_tags(3, 9)["diaglob:environment"] == "staging"

    config = facade._current_provisioning_config()
    assert config.environment == "staging"
    assert config.vector_bucket_arn == VECTOR_BUCKET_ARN
    assert config.bedrock_service_role_arn == ROLE_ARN
    assert config.embedding_model_arn == MODEL_ARN
    assert config.knowledge_bucket == KNOWLEDGE_BUCKET


def test_facade_validation_observes_monkeypatched_missing_value(monkeypatch):
    monkeypatch.setattr(facade, "ENVIRONMENT", "production")
    monkeypatch.setattr(facade, "VECTOR_BUCKET_ARN", VECTOR_BUCKET_ARN)
    monkeypatch.setattr(facade, "BEDROCK_SERVICE_ROLE_ARN", "")
    monkeypatch.setattr(facade, "EMBEDDING_MODEL_ARN", MODEL_ARN)
    monkeypatch.setattr(facade, "KNOWLEDGE_BUCKET", KNOWLEDGE_BUCKET)

    with pytest.raises(BedrockProvisioningError) as exc:
        facade._validate_configuration()
    assert exc.value.code == "provisioning_configuration_missing"
