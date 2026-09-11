"""Contract tests for the Knowledge S3 Vectors infrastructure boundary."""

from unittest.mock import MagicMock

import pytest

from app import bedrock_knowledge_base as facade
from app.knowledge_provisioning.errors import BedrockProvisioningError
from app.knowledge_provisioning.s3_vectors import S3VectorsAdapter, S3VectorsConfig


def _config() -> S3VectorsConfig:
    return S3VectorsConfig(
        vector_bucket_arn="arn:aws:s3vectors:us-east-2:123456789012:bucket/test",
        environment="production",
        vector_dimension=1024,
        vector_data_type="float32",
        vector_distance_metric="cosine",
        non_filterable_metadata_keys=(
            "AMAZON_BEDROCK_TEXT",
            "AMAZON_BEDROCK_METADATA",
        ),
        recovery_attempts=1,
        wait_attempts=1,
    )


def _adapter(*, client_factory=lambda: MagicMock()) -> S3VectorsAdapter:
    return S3VectorsAdapter(
        config=_config(),
        client_factory=client_factory,
        vector_index_arn=lambda kb_id: (
            "arn:aws:s3vectors:us-east-2:123456789012:bucket/test/"
            f"index/diaglob-prod-kb-{kb_id}"
        ),
        build_vector_index_name=lambda environment, kb_id: (
            f"diaglob-prod-kb-{kb_id}"
        ),
        make_tags=lambda org_id, kb_id: {
            "diaglob:managed-by": "diaglob-backend",
            "diaglob:environment": "production",
            "diaglob:organization_id": str(org_id),
            "diaglob:knowledge_base_id": str(kb_id),
        },
        tags_match=lambda actual, expected: all(
            actual.get(key) == value for key, value in expected.items()
        ),
        sleep_between_attempts=lambda attempt, attempts: None,
        validate_configuration=lambda: None,
        log_aws_error=lambda **kwargs: None,
    )


def test_facade_adapter_uses_current_runtime_configuration(monkeypatch):
    client = MagicMock()

    monkeypatch.setattr(facade, "ENVIRONMENT", "staging")
    monkeypatch.setattr(facade, "VECTOR_BUCKET_ARN", "vector-bucket")
    monkeypatch.setattr(facade, "RECOVERY_ATTEMPTS", 7)
    monkeypatch.setattr(facade, "WAIT_ATTEMPTS", 9)
    monkeypatch.setattr(facade, "_get_s3_vectors_client", lambda: client)

    adapter = facade._s3_vectors_adapter()

    assert isinstance(adapter, S3VectorsAdapter)
    assert adapter.config.environment == "staging"
    assert adapter.config.vector_bucket_arn == "vector-bucket"
    assert adapter.config.recovery_attempts == 7
    assert adapter.config.wait_attempts == 9
    assert adapter._client_factory() is client


def test_facade_read_wrappers_delegate_to_adapter(monkeypatch):
    adapter = MagicMock()
    adapter.get_index.return_value = {"indexArn": "index-arn"}
    adapter.get_tags.return_value = {"owner": "diaglob"}
    adapter.recover_index.return_value = {"indexArn": "recovered"}
    monkeypatch.setattr(facade, "_s3_vectors_adapter", lambda: adapter)

    assert facade.get_s3_vectors_index("index-arn") == {"indexArn": "index-arn"}
    assert facade._get_s3_vectors_tags("index-arn") == {"owner": "diaglob"}
    assert facade._recover_s3_vectors_index(4, 8) == {"indexArn": "recovered"}

    adapter.get_index.assert_called_once_with("index-arn")
    adapter.get_tags.assert_called_once_with("index-arn")
    adapter.recover_index.assert_called_once_with(4, 8)


def test_facade_write_wrappers_delegate_to_adapter(monkeypatch):
    adapter = MagicMock()
    adapter.create_index.return_value = {"indexArn": "created"}
    monkeypatch.setattr(facade, "_s3_vectors_adapter", lambda: adapter)

    result = facade.create_s3_vectors_index(2, 5)
    facade.delete_s3_vectors_index("created", 2, 5)

    assert result == {"indexArn": "created"}
    adapter.create_index.assert_called_once_with(2, 5)
    adapter.delete_index.assert_called_once_with("created", 2, 5)


def test_facade_validation_wrapper_delegates_to_adapter(monkeypatch):
    adapter = MagicMock()
    monkeypatch.setattr(facade, "_s3_vectors_adapter", lambda: adapter)
    index = {"indexArn": "index-arn"}
    tags = {"owner": "diaglob"}

    facade._validate_s3_vectors_index(index, tags, 3, 6)

    adapter.validate_index.assert_called_once_with(index, tags, 3, 6)


def test_adapter_rejects_resource_ownership_mismatch():
    adapter = _adapter()
    index = {
        "indexArn": "wrong-arn",
        "indexName": "diaglob-prod-kb-1",
        "dataType": "float32",
        "dimension": 1024,
        "distanceMetric": "cosine",
        "metadataConfiguration": {
            "nonFilterableMetadataKeys": [
                "AMAZON_BEDROCK_TEXT",
                "AMAZON_BEDROCK_METADATA",
            ]
        },
    }

    with pytest.raises(BedrockProvisioningError) as exc:
        adapter.validate_index(index, {}, 1, 1)

    assert exc.value.code == "resource_ownership_mismatch"
    assert exc.value.resource == "vector_index"


def test_adapter_rejects_vector_configuration_mismatch():
    adapter = _adapter()
    index = {
        "indexArn": (
            "arn:aws:s3vectors:us-east-2:123456789012:bucket/test/"
            "index/diaglob-prod-kb-1"
        ),
        "indexName": "diaglob-prod-kb-1",
        "dataType": "float32",
        "dimension": 1536,
        "distanceMetric": "cosine",
        "metadataConfiguration": {
            "nonFilterableMetadataKeys": [
                "AMAZON_BEDROCK_TEXT",
                "AMAZON_BEDROCK_METADATA",
            ]
        },
    }
    tags = {
        "diaglob:managed-by": "diaglob-backend",
        "diaglob:environment": "production",
        "diaglob:organization_id": "1",
        "diaglob:knowledge_base_id": "1",
    }

    with pytest.raises(BedrockProvisioningError) as exc:
        adapter.validate_index(index, tags, 1, 1)

    assert exc.value.code == "vector_index_configuration_mismatch"
    assert exc.value.resource == "vector_index"
