"""Contract tests for the modern Bedrock resource infrastructure boundary."""

from unittest.mock import MagicMock

import pytest

from app import bedrock_knowledge_base as facade
from app.knowledge_provisioning.bedrock_resources import (
    BedrockResourcesAdapter,
    BedrockResourcesConfig,
)
from app.knowledge_provisioning.errors import BedrockProvisioningError


def test_facade_builds_adapter_from_current_runtime_configuration(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(facade, "VECTOR_BUCKET_ARN", "vector-bucket")
    monkeypatch.setattr(facade, "BEDROCK_SERVICE_ROLE_ARN", "role-arn")
    monkeypatch.setattr(facade, "EMBEDDING_MODEL_ARN", "model-arn")
    monkeypatch.setattr(facade, "KNOWLEDGE_BUCKET", "knowledge-bucket")
    monkeypatch.setattr(facade, "VECTOR_DIMENSION", 2048)
    monkeypatch.setattr(facade, "VECTOR_EMBEDDING_DATA_TYPE", "FLOAT32")
    monkeypatch.setattr(facade, "RECOVERY_ATTEMPTS", 4)
    monkeypatch.setattr(facade, "WAIT_ATTEMPTS", 6)
    monkeypatch.setattr(facade, "_get_bedrock_agent_client", lambda: client)

    adapter = facade._bedrock_resources_adapter()

    assert isinstance(adapter, BedrockResourcesAdapter)
    assert adapter.config.vector_bucket_arn == "vector-bucket"
    assert adapter.config.bedrock_service_role_arn == "role-arn"
    assert adapter.config.embedding_model_arn == "model-arn"
    assert adapter.config.knowledge_bucket == "knowledge-bucket"
    assert adapter.config.vector_dimension == 2048
    assert adapter.config.recovery_attempts == 4
    assert adapter.config.wait_attempts == 6
    assert adapter._client_factory() is client


def test_knowledge_base_facade_wrappers_delegate(monkeypatch):
    adapter = MagicMock()
    adapter.get_knowledge_base.return_value = {"knowledgeBaseId": "KB1"}
    adapter.discover_knowledge_base.return_value = {"knowledgeBaseId": "KB2"}
    adapter.create_knowledge_base.return_value = {"knowledgeBaseId": "KB3"}
    adapter.wait_for_knowledge_base.return_value = {"status": "ACTIVE"}
    monkeypatch.setattr(facade, "_bedrock_resources_adapter", lambda: adapter)

    remote = {"knowledgeBaseId": "KB1"}
    assert facade.get_bedrock_knowledge_base("KB1") == remote
    facade._validate_bedrock_knowledge_base(remote, 1, 2, "index-arn")
    assert facade.discover_bedrock_knowledge_base(1, 2, "index-arn") == {
        "knowledgeBaseId": "KB2"
    }
    assert facade.create_bedrock_knowledge_base(
        1, 2, "index-arn", "description"
    ) == {"knowledgeBaseId": "KB3"}
    assert facade.wait_for_bedrock_knowledge_base(
        "KB3", 1, 2, "index-arn"
    ) == {"status": "ACTIVE"}
    facade.delete_bedrock_knowledge_base("KB3", 1, 2, "index-arn")

    adapter.get_knowledge_base.assert_called_once_with("KB1")
    adapter.validate_knowledge_base.assert_called_once_with(
        remote, 1, 2, "index-arn"
    )
    adapter.discover_knowledge_base.assert_called_once_with(1, 2, "index-arn")
    adapter.create_knowledge_base.assert_called_once_with(
        1, 2, "index-arn", "description"
    )
    adapter.wait_for_knowledge_base.assert_called_once_with(
        "KB3", 1, 2, "index-arn"
    )
    adapter.delete_knowledge_base.assert_called_once_with(
        "KB3", 1, 2, "index-arn"
    )


def test_data_source_facade_wrappers_delegate(monkeypatch):
    adapter = MagicMock()
    adapter.get_data_source.return_value = {"dataSourceId": "DS1"}
    adapter.discover_data_source.return_value = {"dataSourceId": "DS2"}
    adapter.create_data_source.return_value = {"dataSourceId": "DS3"}
    adapter.wait_for_data_source.return_value = {"status": "AVAILABLE"}
    monkeypatch.setattr(facade, "_bedrock_resources_adapter", lambda: adapter)

    remote = {"dataSourceId": "DS1"}
    assert facade.get_bedrock_data_source("KB1", "DS1") == remote
    facade._validate_bedrock_data_source(remote, "KB1", 1, 2)
    assert facade.discover_bedrock_data_source("KB1", 1, 2) == {
        "dataSourceId": "DS2"
    }
    assert facade.create_bedrock_data_source("KB1", 1, 2) == {
        "dataSourceId": "DS3"
    }
    assert facade.wait_for_bedrock_data_source("KB1", "DS3", 1, 2) == {
        "status": "AVAILABLE"
    }
    facade.delete_bedrock_data_source("KB1", "DS3", 1, 2, "index-arn")

    adapter.get_data_source.assert_called_once_with("KB1", "DS1")
    adapter.validate_data_source.assert_called_once_with(remote, "KB1", 1, 2)
    adapter.discover_data_source.assert_called_once_with("KB1", 1, 2)
    adapter.create_data_source.assert_called_once_with("KB1", 1, 2)
    adapter.wait_for_data_source.assert_called_once_with("KB1", "DS3", 1, 2)
    adapter.delete_data_source.assert_called_once_with(
        "KB1", "DS3", 1, 2, "index-arn"
    )


def _adapter() -> BedrockResourcesAdapter:
    config = BedrockResourcesConfig(
        vector_bucket_arn="vector-bucket",
        bedrock_service_role_arn="role-arn",
        embedding_model_arn="model-arn",
        knowledge_bucket="knowledge-bucket",
        vector_dimension=1024,
        vector_embedding_data_type="FLOAT32",
        recovery_attempts=1,
        wait_attempts=1,
    )
    return BedrockResourcesAdapter(
        config=config,
        client_factory=lambda: MagicMock(),
        make_kb_name=lambda org_id, kb_id: f"org-{org_id}-kb-{kb_id}",
        make_ds_name=lambda kb_id: f"kb-{kb_id}-s3",
        make_client_token=lambda prefix, org_id, kb_id: "token",
        make_tags=lambda org_id, kb_id: {"org": str(org_id), "kb": str(kb_id)},
        tags_match=lambda actual, expected: actual == expected,
        get_s3_prefix=lambda org_id, kb_id: f"organizations/{org_id}/kb/{kb_id}/",
        vector_index_arn=lambda kb_id: f"index-{kb_id}",
        validate_configuration=lambda: None,
        sleep_between_attempts=lambda attempt, attempts: None,
        log_aws_error=lambda **kwargs: None,
    )


def test_adapter_rejects_knowledge_base_ownership_mismatch():
    adapter = _adapter()
    with pytest.raises(BedrockProvisioningError) as exc:
        adapter.validate_knowledge_base(
            {"name": "wrong", "roleArn": "role-arn"}, 1, 2, "index-2"
        )
    assert exc.value.code == "resource_ownership_mismatch"
    assert exc.value.resource == "knowledge_base"


def test_adapter_rejects_data_source_scope_mismatch():
    adapter = _adapter()
    remote = {
        "knowledgeBaseId": "KB1",
        "name": "kb-2-s3",
        "dataSourceConfiguration": {
            "type": "S3",
            "s3Configuration": {
                "bucketArn": "arn:aws:s3:::knowledge-bucket",
                "inclusionPrefixes": ["organizations/OTHER/kb/2/"],
            },
        },
        "dataDeletionPolicy": "DELETE",
        "vectorIngestionConfiguration": {
            "chunkingConfiguration": {
                "chunkingStrategy": "FIXED_SIZE",
                "fixedSizeChunkingConfiguration": {
                    "maxTokens": 300,
                    "overlapPercentage": 20,
                },
            }
        },
    }
    with pytest.raises(BedrockProvisioningError) as exc:
        adapter.validate_data_source(remote, "KB1", 1, 2)
    assert exc.value.code == "resource_ownership_mismatch"
    assert exc.value.resource == "data_source"
